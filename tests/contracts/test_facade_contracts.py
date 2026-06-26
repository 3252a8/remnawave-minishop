from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping

import bot.app.web.admin_api
import bot.app.web.subscription_webapp
import bot.services.subscription_service


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_baseline() -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    scripts_dir = _project_root() / "scripts"
    exports_path = scripts_dir / "facade_exports_baseline.json"
    imports_path = scripts_dir / "facade_import_baseline.json"
    runtime_imports_path = scripts_dir / "runtime_import_baseline.json"

    return (
        __import__("json").loads(exports_path.read_text(encoding="utf-8")),
        __import__("json").loads(imports_path.read_text(encoding="utf-8")),
        __import__("json").loads(runtime_imports_path.read_text(encoding="utf-8")),
    )


def test_facade_public_exports_are_frozen() -> None:
    expected_exports, _, _ = _load_baseline()
    actual_exports = {
        "backend/bot/app/web/admin_api.py": bot.app.web.admin_api.__all__,
        "backend/bot/app/web/subscription_webapp.py": bot.app.web.subscription_webapp.__all__,
        "backend/bot/services/subscription_service.py": bot.services.subscription_service.__all__,
    }
    for file, expected in expected_exports.items():
        assert sorted(actual_exports[file]) == expected


def _collect_facade_importers() -> dict[str, set[str]]:
    facade_modules = {
        "admin_api": "bot.app.web.admin_api",
        "subscription_webapp": "bot.app.web.subscription_webapp",
        "subscription_service": "bot.services.subscription_service",
    }
    results: dict[str, set[str]] = {name: set() for name in facade_modules}
    backend_root = _project_root() / "backend"

    for file in backend_root.rglob("*.py"):
        if "tests" in file.parts:
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
        except Exception:
            continue

        relative = file.relative_to(_project_root()).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for name, facade in facade_modules.items():
                    if module == facade or module.startswith(f"{facade}."):
                        results[name].add(relative)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for name, facade in facade_modules.items():
                        imported = alias.name
                        if imported == facade or imported.startswith(f"{facade}."):
                            results[name].add(relative)

    return results


def _module_import_aliases(tree: ast.AST) -> dict[str, str]:
    alias_to_module: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                alias_to_module[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                alias_to_module[alias.asname or alias.name] = (
                    f"{module}.{alias.name}" if module else alias.name
                )

    return alias_to_module


def _resolve_module_expression(expr: ast.AST, aliases: Mapping[str, str]) -> str | None:
    if isinstance(expr, ast.Name):
        return aliases.get(expr.id)

    if isinstance(expr, ast.Attribute):
        parts: list[str] = []
        current: ast.AST = expr
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            root = aliases.get(current.id, current.id)
            parts.append(root)
            return ".".join(reversed(parts))

    return None


def test_facade_imports_are_explicit_and_frozen() -> None:
    _, expected_importers, expected_runtime_importers = _load_baseline()
    actual_importers = _collect_facade_importers()

    for facade_name, expected in expected_importers.items():
        normalized_expected = sorted(Path(p).as_posix() for p in expected)
        assert sorted(actual_importers[facade_name]) == normalized_expected


def test_facade_imports_growth_is_forbidden() -> None:
    _, expected_importers, _ = _load_baseline()
    actual_importers = _collect_facade_importers()
    legacy_importers = {
        "admin_api": {"backend/bot/app/web/admin_api.py"},
        "subscription_webapp": {
            "backend/bot/app/web/subscription_webapp.py",
            "backend/bot/app/web/web_server.py",
        },
        "subscription_service": set(),
    }

    for facade_name, expected in expected_importers.items():
        expected_importers_set = set(Path(p).as_posix() for p in expected)
        allowed_importers = expected_importers_set | legacy_importers[facade_name]
        assert actual_importers[facade_name].issubset(allowed_importers), (
            f"compatibility facade imports grew for {facade_name}: "
            f"{sorted(actual_importers[facade_name] - expected_importers_set)}. "
            f"Import concrete implementation modules instead."
        )


def _collect_runtime_importers() -> dict[str, set[str]]:
    runtime_importers = {
        "admin_api_impl_runtime": set[str](),
        "subscription_service_impl_runtime": set[str](),
        "webapp_runtime": set[str](),
    }
    backend_root = _project_root() / "backend"

    for file in backend_root.rglob("*.py"):
        if "tests" in file.parts:
            continue

        relative = file.relative_to(_project_root()).as_posix()
        is_admin_api_impl = "backend/bot/app/web/admin_api_impl" in file.as_posix()
        is_subscription_service_impl = (
            "backend/bot/services/subscription_service_impl/" in file.as_posix()
        )
        is_webapp_package = "backend/bot/app/web/webapp/" in file.as_posix()

        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue

            module = node.module or ""
            if node.level and module == "_runtime":
                if is_admin_api_impl:
                    runtime_importers["admin_api_impl_runtime"].add(relative)
                if is_subscription_service_impl:
                    runtime_importers["subscription_service_impl_runtime"].add(relative)
                if is_webapp_package:
                    runtime_importers["webapp_runtime"].add(relative)
                continue

            if module == "bot.app.web.admin_api_impl._runtime":
                runtime_importers["admin_api_impl_runtime"].add(relative)
            elif module == "bot.services.subscription_service_impl._runtime":
                runtime_importers["subscription_service_impl_runtime"].add(relative)
            elif module == "bot.app.web.webapp._runtime":
                runtime_importers["webapp_runtime"].add(relative)

    return runtime_importers


def test_monkeypatch_targets_avoid_facade_imports() -> None:
    facade_modules = (
        "bot.services.subscription_service",
        "bot.app.web.admin_api",
        "bot.app.web.subscription_webapp",
    )
    offenders: dict[str, set[str]] = {}

    tests_root = _project_root() / "tests"

    for file in tests_root.rglob("*.py"):
        if "contracts" in file.parts:
            continue

        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
        except Exception:
            continue

        relative = file.relative_to(_project_root()).as_posix()
        import_aliases = _module_import_aliases(tree)

        for node in ast.walk(tree):
            is_patch_call = False
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "patch":
                    is_patch_call = True
                elif isinstance(func, ast.Attribute) and func.attr == "patch":
                    is_patch_call = True
                elif (
                    isinstance(func, ast.Attribute)
                    and func.attr == "setattr"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "monkeypatch"
                ):
                    is_patch_call = True

            if not is_patch_call:
                continue

            if not node.args:
                continue

            target = node.args[0]
            if isinstance(target, ast.Constant) and isinstance(target.value, str):
                target_text = target.value
            else:
                target_text = _resolve_module_expression(target, import_aliases) or ""
                if not target_text:
                    continue
            if target_text.startswith("bot.services.subscription_service_impl"):
                continue

            for facade in facade_modules:
                if target_text == facade or target_text.startswith(f"{facade}."):
                    offenders.setdefault(relative, set()).add(target_text)
                    break

    assert not offenders, (
        "tests must patch concrete implementation modules, not compatibility facades: "
        + "; ".join(f"{file}: {sorted(targets)}" for file, targets in sorted(offenders.items()))
    )


def test_runtime_imports_are_frozen() -> None:
    _, _, expected_runtime_importers = _load_baseline()
    actual_runtime_importers = _collect_runtime_importers()

    for runtime_name, expected in expected_runtime_importers.items():
        normalized_expected = sorted(Path(p).as_posix() for p in expected)
        assert sorted(actual_runtime_importers[runtime_name]) == normalized_expected
