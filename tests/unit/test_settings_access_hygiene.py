from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = PROJECT_ROOT / "backend" / "config" / "settings.py"
SETTINGS_MIXINS_PATH = PROJECT_ROOT / "backend" / "config" / "settings_mixins.py"

INTENTIONAL_ABSENT_SETTINGS_NAMES = {
    "DEFAULT_CURRENCY",
    "PANEL_EXTERNAL_SQUADS_CACHE_TTL_SECONDS",
    "SUBSCRIPTION_PAGE_CONFIG_UUID",
    "YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING",
}


def _module_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_def(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} class not found")


def _defined_settings_attrs() -> set[str]:
    settings_class = _class_def(_module_tree(SETTINGS_PATH), "Settings")
    mixin_class = _class_def(_module_tree(SETTINGS_MIXINS_PATH), "SettingsComputedMixin")

    attrs = {
        item.target.id
        for item in settings_class.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    }
    attrs.update(
        item.name
        for item in mixin_class.body
        if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
    )
    return attrs


def _settings_literal_getattrs(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "settings"
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            continue
        matches.append((node.lineno, node.args[1].value))
    return matches


def test_defined_settings_attrs_are_accessed_directly() -> None:
    defined_attrs = _defined_settings_attrs()
    violations: list[str] = []

    for path in sorted((PROJECT_ROOT / "backend").rglob("*.py")):
        for line, attr_name in _settings_literal_getattrs(path):
            if attr_name not in defined_attrs or attr_name in INTENTIONAL_ABSENT_SETTINGS_NAMES:
                continue
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            violations.append(f"{relative}:{line}: settings.{attr_name}")

    assert not violations, (
        "Use direct settings.<name> access for declared Settings attributes:\n"
        + "\n".join(violations)
    )
