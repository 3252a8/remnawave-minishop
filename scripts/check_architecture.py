#!/usr/bin/env python3

from __future__ import annotations

import ast
import fnmatch
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "scripts" / "architecture_gates.json"
CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
TRANSLATION_CALL_RE = re.compile(r"(?<![\w$])(t|at)\s*\(")


def _load_config() -> dict:
    config: dict = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return config


def _to_posix(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_allowed(path: str, allowlist: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in allowlist)


def _iter_text_files(scope: str, extensions: set[str]) -> list[Path]:
    base = ROOT / scope
    if not base.exists():
        return []
    if base.is_file():
        return [base] if base.suffix.lower() in extensions else []

    return [
        file for file in base.rglob("*") if file.is_file() and file.suffix.lower() in extensions
    ]


def _find_call_end(text: str, opening_parenthesis: int) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening_parenthesis

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 1
        elif quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char == "/" and next_char == "/":
            line_comment = True
            index += 1
        elif char == "/" and next_char == "*":
            block_comment = True
            index += 1
        elif char in {'"', "'", "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index

        index += 1

    return None


def _split_top_level_arguments(text: str) -> list[str]:
    arguments: list[str] = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0}
    closing_to_opening = {")": "(", "]": "[", "}": "{"}
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = 0

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 1
        elif quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char == "/" and next_char == "/":
            line_comment = True
            index += 1
        elif char == "/" and next_char == "*":
            block_comment = True
            index += 1
        elif char in {'"', "'", "`"}:
            quote = char
        elif char in depths:
            depths[char] += 1
        elif char in closing_to_opening:
            depths[closing_to_opening[char]] -= 1
        elif char == "," and not any(depths.values()):
            arguments.append(text[start:index].strip())
            start = index + 1

        index += 1

    arguments.append(text[start:].strip())
    return arguments


def _frontend_cyrillic_fallbacks(text: str) -> list[int]:
    lines: list[int] = []
    for match in TRANSLATION_CALL_RE.finditer(text):
        opening_parenthesis = match.end() - 1
        call_end = _find_call_end(text, opening_parenthesis)
        if call_end is None:
            continue
        arguments = _split_top_level_arguments(text[opening_parenthesis + 1 : call_end])
        if len(arguments) >= 3 and CYRILLIC_RE.search(arguments[2]):
            lines.append(text.count("\n", 0, match.start()) + 1)
    return lines


def _python_cyrillic_literals(text: str) -> list[int]:
    tree = ast.parse(text)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and CYRILLIC_RE.search(node.value)
    )


def _cyrillic_source_lines(text: str) -> list[int]:
    return [
        line_number
        for line_number, line in enumerate(text.splitlines(), start=1)
        if CYRILLIC_RE.search(line)
    ]


def _check_cyrillic_fallbacks(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("cyrillic_fallbacks")
    if not checks:
        return

    scanners = {
        "frontend_translation_calls": (
            _frontend_cyrillic_fallbacks,
            set(checks.get("frontend_translation_calls", {}).get("extensions", [])),
        ),
        "frontend_webapp_translation_calls": (
            _frontend_cyrillic_fallbacks,
            set(checks.get("frontend_webapp_translation_calls", {}).get("extensions", [])),
        ),
        "frontend_admin_payments_translation_calls": (
            _frontend_cyrillic_fallbacks,
            set(checks.get("frontend_admin_payments_translation_calls", {}).get("extensions", [])),
        ),
        "frontend_source_lines": (
            _cyrillic_source_lines,
            set(checks.get("frontend_source_lines", {}).get("extensions", [])),
        ),
        "python_literals": (_python_cyrillic_literals, {".py"}),
        "python_webapp_literals": (_python_cyrillic_literals, {".py"}),
        "python_literal_exceptions": (_python_cyrillic_literals, {".py"}),
        "python_source_lines": (_cyrillic_source_lines, {".py"}),
        "python_source_exceptions": (_cyrillic_source_lines, {".py"}),
    }

    for name, (scanner, extensions) in scanners.items():
        rule = checks.get(name)
        if not rule:
            continue

        findings: list[str] = []
        for scope in rule.get("scopes", []):
            for file in _iter_text_files(scope, extensions):
                relative = _to_posix(file)
                if _is_allowed(relative, rule.get("allowlist", [])):
                    continue
                try:
                    lines = scanner(file.read_text(encoding="utf-8", errors="ignore"))
                except SyntaxError as exc:
                    issues.append(f"[cyrillic-fallbacks] Failed to parse {relative}: {exc}")
                    continue
                findings.extend(f"{relative}:{line}" for line in lines)

        expected_count = int(rule.get("allowed_count", 0))
        actual_count = len(findings)
        if actual_count == expected_count:
            continue

        direction = "increased" if actual_count > expected_count else "decreased"
        samples = ", ".join(findings[:5]) or "none"
        issues.append(
            f"[cyrillic-fallbacks] {name} count {direction}: expected {expected_count}, "
            f"found {actual_count}. Keep fallbacks in English and Russian text in locales; "
            f"update the ratchet after intentional cleanup. Samples: {samples}"
        )


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

                handler_node = node.args[handler_arg_index]
                handler_name: str | None = None
                if isinstance(handler_node, ast.Name):
                    handler_name = handler_node.id
                else:
                    handler_name = _string_value(handler_node)
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
            with file.open(encoding="utf-8", errors="ignore") as handle:
                lines = sum(1 for _ in handle)
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


def _check_loose_schemas(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("loose_schemas")
    if not checks:
        return

    pattern = re.compile(r"\b(?P<helper>loose_(?:object|array)_schema)\s*\(")
    allowlist = checks.get("allowlist", {})
    allowed_counts: dict[str, dict[str, int]] = {}

    for rel, helper_entries in allowlist.items():
        if not isinstance(helper_entries, dict):
            issues.append(f"[loose-schema] {rel}: allowlist entry must map helper names to reasons")
            continue

        allowed_counts[rel] = {}
        for helper_name, reasons in helper_entries.items():
            if helper_name not in {"loose_object_schema", "loose_array_schema"}:
                issues.append(f"[loose-schema] {rel}: unknown helper {helper_name}")
                continue
            if not isinstance(reasons, list) or not reasons:
                issues.append(f"[loose-schema] {rel}: {helper_name} allowlist must include reasons")
                continue
            for idx, reason in enumerate(reasons, 1):
                if not isinstance(reason, str) or not reason.strip():
                    issues.append(f"[loose-schema] {rel}: {helper_name} reason #{idx} is empty")
            allowed_counts[rel][helper_name] = len(reasons)

    actual_counts: dict[str, dict[str, int]] = {}
    for scope in checks.get("scopes", []):
        for file in _iter_text_files(scope, {".py"}):
            rel = _to_posix(file)
            content = file.read_text(encoding="utf-8", errors="ignore")
            for match in pattern.finditer(content):
                helper_name = match.group("helper")
                actual_counts.setdefault(rel, {}).setdefault(helper_name, 0)
                actual_counts[rel][helper_name] += 1

    for rel, helper_counts in sorted(actual_counts.items()):
        for helper_name, actual in sorted(helper_counts.items()):
            allowed = allowed_counts.get(rel, {}).get(helper_name, 0)
            if actual > allowed:
                issues.append(
                    f"[loose-schema] {rel}: found {actual} {helper_name} calls, "
                    f"allowed {allowed}; add typed schema or an allowlist reason"
                )
            elif actual < allowed:
                issues.append(
                    f"[loose-schema] {rel}: allowlist permits {allowed} {helper_name} calls, "
                    f"but only {actual} remain"
                )

    for rel, helper_counts in sorted(allowed_counts.items()):
        actual_helpers = actual_counts.get(rel, {})
        for helper_name, allowed in sorted(helper_counts.items()):
            if actual_helpers.get(helper_name, 0) == 0 and allowed:
                issues.append(f"[loose-schema] {rel}: allowlist entry for {helper_name} is stale")


def _check_frontend_weak_typing(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("frontend_weak_typing")
    if not checks:
        return

    pattern = re.compile(
        r"\b(?:as\s+any|Record<\s*string\s*,\s*any\s*>|\bAnyRecord\b)"
        r"|\(\s*\.\.\.[A-Za-z_$][\w$]*\s*:\s*any\[\]\s*\)\s*=>\s*any\b"
        r"|:\s*any\b"
    )
    extensions = set(checks["extensions"])
    allowlist = list(checks.get("allowlist", []))
    allowed_counts = checks.get("allowed_counts", {})

    if not isinstance(allowed_counts, dict):
        issues.append("[frontend-weak-typing] allowed_counts must be an object")
        return

    parsed_allowed_counts: dict[str, int] = {}
    for rel, allowed in allowed_counts.items():
        if not isinstance(rel, str):
            issues.append("[frontend-weak-typing] allowed_counts keys must be paths")
            continue
        if not isinstance(allowed, int) or allowed < 0:
            issues.append(
                f"[frontend-weak-typing] {rel}: allowed_counts value must be a non-negative integer"
            )
            continue
        parsed_allowed_counts[rel] = allowed

    actual_counts: dict[str, int] = {}

    for scope in checks["scopes"]:
        for file in _iter_text_files(scope, extensions):
            rel = _to_posix(file)
            if _is_allowed(rel, allowlist):
                continue

            content = file.read_text(encoding="utf-8", errors="ignore")
            count = len(pattern.findall(content))
            if count == 0:
                continue

            actual_counts[rel] = count
            allowed = parsed_allowed_counts.get(rel, 0)
            if count > allowed:
                issues.append(
                    f"[frontend-weak-typing] {rel}: found {count} weak typing patterns, "
                    f"allowed {allowed} (as any / Record<string, any> / AnyRecord / "
                    "callback any / : any)"
                )
            elif count < allowed:
                issues.append(
                    f"[frontend-weak-typing] {rel}: allowed_counts permits {allowed} weak typing "
                    f"patterns, but only {count} remain"
                )

    for rel, allowed in sorted(parsed_allowed_counts.items()):
        if allowed and rel not in actual_counts:
            issues.append(
                f"[frontend-weak-typing] {rel}: allowed_counts entry permits {allowed} weak typing "
                "patterns, but none remain"
            )


def _check_first_party_js(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("first_party_js")
    if not checks:
        return

    allowlist = set(checks.get("allowlist", []))
    actual_js: set[str] = set()

    for scope in checks.get("scopes", []):
        for file in _iter_text_files(scope, {".js"}):
            rel = _to_posix(file)
            actual_js.add(rel)
            if rel not in allowlist:
                issues.append(
                    f"[first-party-js] {rel}: first-party JS is forbidden; write TypeScript "
                    "(only generated artifacts may stay .js)"
                )

    issues.extend(
        f"[first-party-js] {rel}: allowlist entry is stale"
        for rel in sorted(allowlist)
        if rel not in actual_js
    )


def _check_svelte_lang_ts(cfg: dict, issues: list[str]) -> None:
    checks = cfg.get("svelte_lang_ts")
    if not checks:
        return

    allowlist = set(checks.get("allowlist", []))
    script_lang_ts = re.compile(r"<script\b[^>]*\blang\s*=\s*([\"'])ts\1")
    actual_untyped: set[str] = set()

    for scope in checks.get("scopes", []):
        for file in _iter_text_files(scope, {".svelte"}):
            rel = _to_posix(file)
            content = file.read_text(encoding="utf-8", errors="ignore")
            if script_lang_ts.search(content):
                continue

            actual_untyped.add(rel)
            if rel not in allowlist:
                issues.append(f'[svelte-lang-ts] {rel}: missing <script lang="ts">')

    issues.extend(
        f"[svelte-lang-ts] {rel}: allowlist entry is stale"
        for rel in sorted(allowlist)
        if rel not in actual_untyped
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
                for alias_name in aliases:
                    imported_path = f"{module}.{alias_name}"
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
    _check_cyrillic_fallbacks(config, issues)
    _check_type_ignores(config, issues)
    _check_raw_json_response(config, issues)
    _check_loose_schemas(config, issues)
    _check_frontend_weak_typing(config, issues)
    _check_first_party_js(config, issues)
    _check_svelte_lang_ts(config, issues)
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
