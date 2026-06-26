#!/usr/bin/env python3

from __future__ import annotations

import ast
import fnmatch
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "scripts" / "architecture_gates.json"


def _load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _to_posix(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_allowed(path: str, allowlist: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in allowlist)


def _iter_text_files(scope: str, extensions: set[str]):
    base = ROOT / scope
    if not base.exists():
        return []
    if base.is_file():
        return [base] if base.suffix.lower() in extensions else []

    return [
        file for file in base.rglob("*") if file.is_file() and file.suffix.lower() in extensions
    ]


def _string_value(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_call_to_register_contract(node: ast.Call) -> bool:
    return isinstance(node.func, (ast.Name, ast.Attribute)) and (
        (isinstance(node.func, ast.Name) and node.func.id == "register_contract")
        or (isinstance(node.func, ast.Attribute) and node.func.attr == "register_contract")
    )


def _is_contract_dict_name(name: str) -> bool:
    return name.endswith("ROUTE_CONTRACTS") or name.lower() == "route_contracts"


def _collect_contract_names(cfg: dict, issues: list[str]) -> set[str]:
    checks = cfg.get("route_contracts")
    if not checks:
        return set()

    contract_names: set[str] = set()

    for scope in checks.get("contract_scopes", []):
        for file in _iter_text_files(scope, {".py"}):
            try:
                tree = ast.parse(file.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                issues.append(
                    f"[route-contracts] Failed to parse contract file {file.relative_to(ROOT)} for "
                    "contract collection."
                )
                continue

            dict_assignments: dict[str, set[str]] = {}
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue

                target_name = None
                value = None

                if isinstance(node, ast.Assign):
                    if len(node.targets) != 1:
                        continue
                    value = node.value
                    if isinstance(node.targets[0], ast.Name):
                        target_name = node.targets[0].id
                else:
                    value = node.value
                    if value is None:
                        continue
                    if isinstance(node.target, ast.Name):
                        target_name = node.target.id

                if target_name is None or not _is_contract_dict_name(target_name):
                    continue
                if not isinstance(value, ast.Dict):
                    continue
                assigned_keys = {
                    key
                    for key in (
                        _string_value(key_node) for key_node in value.keys if key_node is not None
                    )
                    if key is not None
                }
                if assigned_keys:
                    dict_assignments[target_name] = assigned_keys
                    contract_names.update(assigned_keys)

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not _is_call_to_register_contract(node):
                    continue
                handler_name = _string_value(node.args[0] if node.args else None)
                if handler_name:
                    contract_names.add(handler_name)
                else:
                    handler_name_expr = node.args[0] if node.args else None
                    if (
                        isinstance(handler_name_expr, ast.Name)
                        and handler_name_expr.id in dict_assignments
                    ):
                        contract_names.update(dict_assignments[handler_name_expr.id])

            for node in ast.walk(tree):
                if not isinstance(node, ast.For):
                    continue
                target_name = None
                if isinstance(node.target, ast.Name):
                    target_name = node.target.id
                elif isinstance(node.target, ast.Tuple) and node.target.elts:
                    first = node.target.elts[0]
                    if isinstance(first, ast.Name):
                        target_name = first.id

                if target_name is None:
                    continue
                loop_iter_name = _iter_over_dict_name(node.iter)
                if not loop_iter_name:
                    continue
                if loop_iter_name not in dict_assignments:
                    continue

                for body_node in node.body:
                    for call_node in ast.walk(body_node):
                        if not isinstance(call_node, ast.Call) or not _is_call_to_register_contract(
                            call_node
                        ):
                            continue
                        arg_name = _string_value(call_node.args[0] if call_node.args else None)
                        if arg_name != target_name:
                            continue
                        contract_names.update(dict_assignments[loop_iter_name])

    return contract_names


def _iter_over_dict_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != "items":
        return None
    if isinstance(node.func.value, ast.Name):
        return node.func.value.id
    return None


def _collect_api_routes(cfg: dict, issues: list[str]) -> list[tuple[str, str]]:
    checks = cfg.get("route_contracts")
    if not checks:
        return []

    route_names: list[tuple[str, str]] = []
    method_calls = {"add_get", "add_post", "add_put", "add_patch", "add_delete", "add_head"}

    for scope in checks.get("route_setup_scopes", []):
        for file in _iter_text_files(scope, {".py"}):
            rel = _to_posix(file)
            try:
                tree = ast.parse(file.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                issues.append(
                    f"[route-contracts] Failed to parse route file {rel} for route-contract check."
                )
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                method = node.func.attr
                if method not in method_calls:
                    continue

                handler_arg_index = 1
                if len(node.args) <= handler_arg_index:
                    continue

                path = _string_value(node.args[0])
                if path is None:
                    continue
                if not path.startswith("/api/"):
                    continue

                handler_name: str | None = None
                if isinstance(node.args[handler_arg_index], ast.Name):
                    handler_name = node.args[1].id
                else:
                    handler_name = _string_value(node.args[handler_arg_index])
                if handler_name is None:
                    continue

                path_allowlist = checks.get("path_allowlist", [])
                if _is_allowed(path, path_allowlist):
                    continue

                route_names.append((path, handler_name))

    return route_names


def _check_route_contract_coverage(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("route_contracts")
    if not checks:
        return

    contract_names = _collect_contract_names(cfg, issues)
    for path, handler_name in _collect_api_routes(cfg, issues):
        if handler_name not in contract_names:
            issues.append(
                f"[route-contracts] Route {path} -> {handler_name} has no registered route contract"
            )


def _check_type_ignores(cfg: dict, issues: list[str]) -> None:
    scope_dirs = cfg["type_ignore"]["scopes"]
    allowlist = cfg["type_ignore"]["allowlist"]
    pattern = re.compile(r"#\s*type:\s*ignore(\[[^\]]+\])?")

    for scope in scope_dirs:
        for file in _iter_text_files(scope, {".py"}):
            rel = _to_posix(file)
            count = 0
            for line in file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if pattern.search(line):
                    count += 1

            allowed = allowlist.get(rel, 0)
            if count > allowed:
                issues.append(f"[type-ignore] {rel}: found {count} occurrences, allowed {allowed}")


def _check_module_size(cfg: dict, issues: list[str]) -> None:
    max_lines = int(cfg["module_size"]["max_lines"])
    extensions = set(cfg["module_size"]["extensions"])
    allowlist = cfg["module_size"]["allowlist"]

    for scope in cfg["module_size"]["scopes"]:
        for file in _iter_text_files(scope, extensions):
            rel = _to_posix(file)
            lines = sum(1 for _ in file.open(encoding="utf-8", errors="ignore"))
            if lines <= max_lines:
                continue
            if _is_allowed(rel, allowlist):
                continue

            issues.append(
                f"[module-size] {rel}: {lines} lines, max is {max_lines} "
                "(add to allowlist if intentional)"
            )


def _check_raw_json_response(cfg: dict, issues: list[str]) -> None:
    pattern = re.compile(r"\bweb\.json_response\s*\(")
    allowlist = set(cfg["raw_json_response"]["allowlist"])

    for scope in cfg["raw_json_response"]["scopes"]:
        for file in _iter_text_files(scope, {".py"}):
            rel = _to_posix(file)
            if rel in allowlist:
                continue

            content = file.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(content):
                issues.append(f"[raw-json-response] {rel}: uses web.json_response directly")


def _check_frontend_weak_typing(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("frontend_weak_typing")
    if not checks:
        return

    pattern = re.compile(r"\b(?:as\s+any|Record<\s*string\s*,\s*any\s*>|\bAnyRecord\b)")
    extensions = set(checks["extensions"])
    allowlist = list(checks.get("allowlist", []))

    for scope in checks["scopes"]:
        for file in _iter_text_files(scope, extensions):
            rel = _to_posix(file)
            if _is_allowed(rel, allowlist):
                continue

            content = file.read_text(encoding="utf-8", errors="ignore")
            if pattern.search(content):
                issues.append(
                    f"[frontend-weak-typing] {rel}: uses forbidden weak typing patterns (as any / "
                    "Record<string, any> / AnyRecord)"
                )


def _check_frontend_api_calls(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("frontend_api_calls")
    if not checks:
        return

    allowed_calls = set(checks.get("allowed_calls", ["apiUnchecked"]))
    api_call_re = re.compile(
        r"(?<![\w$])(?P<call>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*"
        r"\(\s*(?P<quote>[\"'`])(?P<path>/api/[^\"'`\n)]*)"
    )
    allowlist = set(checks.get("allowlist_paths", []))

    for scope in checks.get("scopes", []):
        for file in _iter_text_files(scope, {".ts", ".svelte", ".js"}):
            rel = _to_posix(file)
            if _is_allowed(rel, list(allowlist)):
                continue

            file_lines = file.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line_num, line in enumerate(file_lines, 1):
                for match in api_call_re.finditer(line):
                    comment_pos = line.find("//")
                    if comment_pos != -1 and comment_pos < match.start():
                        continue
                    call_name = match.group("call").split(".")[-1]
                    if call_name != "api" and call_name not in allowed_calls:
                        continue
                    issues.append(
                        f"[frontend-api-path] {rel}:{line_num}: direct "
                        f"{match.group('call')}('/api/...') call is forbidden "
                        "without a typed path builder"
                    )


def _check_runtime_all_exports(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("runtime_all_exports")
    if not checks:
        return

    pattern = re.compile(
        r"__all__\s*=\s*\[name for name in globals\(\) if not name\\.startswith\(\"__\"\)\]"
    )
    for rel in checks["paths"]:
        file = ROOT / rel
        if not file.exists():
            issues.append(f"[runtime-all-exports] Missing path in config: {rel}")
            continue

        text = file.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            issues.append(
                f"[runtime-all-exports] {rel}: dynamic __all__ export list still used; "
                "replace with explicit exports."
            )


def _collect_facade_importers(facade_modules: set[str], file: Path) -> set[str]:
    imports: set[str] = set()
    try:
        tree = ast.parse(file.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for facade in facade_modules:
                    if alias.name == facade or alias.name.startswith(f"{facade}."):
                        imports.add(facade)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            aliases = [alias.name for alias in node.names]
            for facade in facade_modules:
                if module == facade or module.startswith(f"{facade}."):
                    imports.add(facade)
                    continue
                for alias in aliases:
                    imported_path = f"{module}.{alias}"
                    if imported_path == facade or imported_path.startswith(f"{facade}."):
                        imports.add(facade)
                        break

    return imports


def _collect_runtime_importers_with_aliases(
    runtime_modules: dict[str, str], file: Path
) -> set[str]:
    imported_aliases: set[str] = set()
    alias_to_module: dict[str, str] = runtime_modules
    module_to_alias = {module: alias for alias, module in alias_to_module.items()}
    expected_modules = set(alias_to_module.values())
    file_path = file.as_posix()

    try:
        tree = ast.parse(file.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return imported_aliases

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for module in expected_modules:
                    if alias.name == module or alias.name.startswith(f"{module}."):
                        imported_aliases.add(module_to_alias[module])
            continue

        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        if node.level and module == "_runtime":
            has_admin_runtime_alias = "admin_api_impl_runtime" in runtime_modules
            has_webapp_runtime_alias = "webapp_runtime" in runtime_modules
            if "backend/bot/app/web/admin_api_impl/" in file_path and has_admin_runtime_alias:
                imported_aliases.add("admin_api_impl_runtime")
            elif "backend/bot/app/web/webapp/" in file_path and has_webapp_runtime_alias:
                imported_aliases.add("webapp_runtime")
            continue

        if module in expected_modules:
            imported_aliases.add(module_to_alias[module])

    return imported_aliases


def _check_runtime_import_contract(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("runtime_imports")
    if not checks:
        return

    runtime_modules = checks.get("runtime_modules", {})
    expected_importer_path = checks.get("baseline_path")
    if not expected_importer_path:
        return

    expected_path = ROOT / expected_importer_path
    if not expected_path.exists():
        issues.append(
            f"[runtime-imports] Missing baseline path in config: {expected_importer_path}"
        )
        return

    expected = __import__("json").loads(expected_path.read_text(encoding="utf-8"))
    path_allowlist = checks.get("allowlist_paths", [])
    actual: dict[str, set[str]] = {name: set() for name in runtime_modules}

    for scope in checks.get("scopes", []):
        base = ROOT / scope
        if not base.exists():
            continue

        for file in base.rglob("*.py"):
            if "tests" in file.parts:
                continue

            rel = _to_posix(file)
            if _is_allowed(rel, path_allowlist):
                continue

            imported_aliases = _collect_runtime_importers_with_aliases(runtime_modules, file)
            for alias in imported_aliases:
                if alias in actual:
                    actual[alias].add(rel)

    for alias, expected_paths in expected.items():
        allowed = {Path(p).as_posix() for p in expected_paths}
        unexpected = sorted(actual.get(alias, set()) - allowed)
        if unexpected:
            module = runtime_modules.get(alias, alias)
            issues.append(
                f"[runtime-imports] Unexpected importers of {module}: {', '.join(unexpected)}"
            )


def _check_facade_import_contract(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("facade_imports")
    if not checks:
        return

    facades = checks.get("facades", {})
    allowed_importers = {k: set(v) for k, v in checks.get("allowed_importers", {}).items()}
    path_allowlist = checks.get("allowlist_paths", [])

    actual: dict[str, set[str]] = {name: set() for name in facades}
    for scope in checks.get("scopes", []):
        base = ROOT / scope
        if not base.exists():
            continue

        for file in base.rglob("*.py"):
            if "tests" in file.parts:
                continue
            rel = _to_posix(file)
            imported = _collect_facade_importers(set(facades.values()), file)
            if not imported:
                continue
            if _is_allowed(rel, path_allowlist):
                continue

            for facade_name, module in facades.items():
                if module not in imported:
                    continue
                actual[facade_name].add(rel)

    for facade_name, expected_paths in allowed_importers.items():
        allowed = {Path(p).as_posix() for p in expected_paths}
        unexpected = sorted(actual.get(facade_name, set()) - allowed)
        if unexpected:
            issues.append(
                f"[facade-imports] Unexpected {facade_name} importers: {', '.join(unexpected)}"
            )


def main() -> int:
    config = _load_config()
    issues: list[str] = []

    _check_module_size(config, issues)
    _check_type_ignores(config, issues)
    _check_raw_json_response(config, issues)
    _check_frontend_weak_typing(config, issues)
    _check_frontend_api_calls(config, issues)
    _check_runtime_all_exports(config, issues)
    _check_runtime_import_contract(config, issues)
    _check_facade_import_contract(config, issues)
    _check_route_contract_coverage(config, issues)

    if issues:
        print("Architecture checks failed:")
        for item in issues:
            print(f"  - {item}")
        return 1

    print("Architecture checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
