from __future__ import annotations

import ast
from pathlib import Path

import bot.app.web.admin_api
import bot.app.web.subscription_webapp
import bot.services.subscription_service


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_baseline() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    scripts_dir = _project_root() / "scripts"
    exports_path = scripts_dir / "facade_exports_baseline.json"
    imports_path = scripts_dir / "facade_import_baseline.json"

    return (
        __import__("json").loads(exports_path.read_text(encoding="utf-8")),
        __import__("json").loads(imports_path.read_text(encoding="utf-8")),
    )


def test_facade_public_exports_are_frozen() -> None:
    expected_exports, _ = _load_baseline()
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


def test_facade_imports_are_explicit_and_frozen() -> None:
    _, expected_importers = _load_baseline()
    actual_importers = _collect_facade_importers()

    for facade_name, expected in expected_importers.items():
        normalized_expected = sorted(Path(p).as_posix() for p in expected)
        assert sorted(actual_importers[facade_name]) == normalized_expected
