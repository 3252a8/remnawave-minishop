from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest

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


@pytest.fixture(scope="module")
def backend_importers() -> dict[str, dict[str, set[str]]]:
    """Scan once per module, retaining small indexes rather than every AST."""
    facade_modules = {
        "admin_api": "bot.app.web.admin_api",
        "subscription_webapp": "bot.app.web.subscription_webapp",
        "subscription_service": "bot.services.subscription_service",
    }
    runtime_modules = {
        "admin_api_impl_runtime": "bot.app.web.admin_api_impl._runtime",
        "subscription_service_impl_runtime": "bot.services.subscription_service_impl._runtime",
        "webapp_runtime": "bot.app.web.webapp._runtime",
    }
    facade_importers: dict[str, set[str]] = {name: set() for name in facade_modules}
    runtime_importers: dict[str, set[str]] = {name: set() for name in runtime_modules}
    for file in (_project_root() / "backend").rglob("*.py"):
        if "tests" in file.parts:
            continue
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        relative = file.relative_to(_project_root()).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for name, facade in facade_modules.items():
                    if module == facade or module.startswith(f"{facade}."):
                        facade_importers[name].add(relative)
                for name, runtime in runtime_modules.items():
                    package_path = "backend/" + runtime.rsplit(".", 1)[0].replace(".", "/")
                    if module == runtime or (
                        node.level
                        and module == "_runtime"
                        and relative.startswith(package_path + "/")
                    ):
                        runtime_importers[name].add(relative)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for name, facade in facade_modules.items():
                        imported = alias.name
                        if imported == facade or imported.startswith(f"{facade}."):
                            facade_importers[name].add(relative)

    return {"facades": facade_importers, "runtimes": runtime_importers}


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


def test_facade_imports_are_explicit_and_frozen(
    backend_importers: dict[str, dict[str, set[str]]],
) -> None:
    _, expected_importers, _expected_runtime_importers = _load_baseline()
    actual_importers = backend_importers["facades"]

    for facade_name, expected in expected_importers.items():
        normalized_expected = sorted(Path(p).as_posix() for p in expected)
        assert sorted(actual_importers[facade_name]) == normalized_expected


def test_facade_imports_growth_is_forbidden(
    backend_importers: dict[str, dict[str, set[str]]],
) -> None:
    _, expected_importers, _ = _load_baseline()
    actual_importers = backend_importers["facades"]
    legacy_importers = {
        "admin_api": {"backend/bot/app/web/admin_api.py"},
        "subscription_webapp": {
            "backend/bot/app/web/subscription_webapp.py",
            "backend/bot/app/web/web_server.py",
        },
        "subscription_service": set(),
    }

    for facade_name, expected in expected_importers.items():
        expected_importers_set = {Path(p).as_posix() for p in expected}
        allowed_importers = expected_importers_set | legacy_importers[facade_name]
        assert actual_importers[facade_name].issubset(allowed_importers), (
            f"compatibility facade imports grew for {facade_name}: "
            f"{sorted(actual_importers[facade_name] - expected_importers_set)}. "
            f"Import concrete implementation modules instead."
        )


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
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_patch_call = False
            if (
                (isinstance(func, ast.Name) and func.id == "patch")
                or (isinstance(func, ast.Attribute) and func.attr == "patch")
                or (
                    isinstance(func, ast.Attribute)
                    and func.attr == "setattr"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "monkeypatch"
                )
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


def test_runtime_imports_are_frozen(backend_importers: dict[str, dict[str, set[str]]]) -> None:
    _, _, expected_runtime_importers = _load_baseline()
    actual_runtime_importers = backend_importers["runtimes"]

    for runtime_name, expected in expected_runtime_importers.items():
        normalized_expected = sorted(Path(p).as_posix() for p in expected)
        assert sorted(actual_runtime_importers[runtime_name]) == normalized_expected
