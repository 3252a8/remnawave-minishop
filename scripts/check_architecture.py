#!/usr/bin/env python3

from __future__ import annotations

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
    return [
        file for file in base.rglob("*") if file.is_file() and file.suffix.lower() in extensions
    ]


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

    pattern = re.compile(
        r"\b(?:as\s+any|Record<\s*string\s*,\s*any\s*>|\bAnyRecord\b)"
    )
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


def main() -> int:
    config = _load_config()
    issues: list[str] = []

    _check_module_size(config, issues)
    _check_type_ignores(config, issues)
    _check_raw_json_response(config, issues)
    _check_frontend_weak_typing(config, issues)

    if issues:
        print("Architecture checks failed:")
        for item in issues:
            print(f"  - {item}")
        return 1

    print("Architecture checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
