"""Inspect application data mounts in a Docker Compose source file.

The runtime image intentionally does not depend on a YAML parser.  This
module therefore reads only the small, stable subset needed by the admin
health check: service blocks and their ``volumes`` entries.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_DATA_TARGET = "/app/data"
APP_DATA_SERVICES = ("migrate", "backend", "worker")
COMPOSE_FILE_NAMES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)

_SERVICE_HEADER_RE = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s*[&#].*)?$")
_SHORT_VOLUME_RE = re.compile(r"^(?P<source>.+):(?P<target>/[^:]+)(?::[^:]+)?$")
_VARIABLE_DEFAULT_RE = re.compile(r"^\$\{[^}:]+:-([^}]+)\}$")


def find_compose_file(source_dir: Path) -> Path | None:
    for name in COMPOSE_FILE_NAMES:
        candidate = source_dir / name
        if candidate.is_file():
            return candidate
    return None


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _yaml_scalar(value: str) -> str:
    scalar = value.strip()
    if " #" in scalar:
        scalar = scalar.split(" #", 1)[0].rstrip()
    if len(scalar) >= 2 and scalar[0] == scalar[-1] and scalar[0] in {'"', "'"}:
        scalar = scalar[1:-1]
    return scalar.strip()


def _service_blocks(text: str) -> dict[str, list[str]]:
    lines = text.splitlines()
    services_index: int | None = None
    services_indent = 0
    for index, line in enumerate(lines):
        if line.strip() == "services:":
            services_index = index
            services_indent = _indent(line)
            break
    if services_index is None:
        return {}

    blocks: dict[str, list[str]] = {}
    service_indent: int | None = None
    current: str | None = None
    for line in lines[services_index + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if current is not None:
                blocks[current].append(line)
            continue
        indent = _indent(line)
        if indent <= services_indent:
            break
        match = _SERVICE_HEADER_RE.fullmatch(stripped)
        if match and (service_indent is None or indent == service_indent):
            service_indent = indent
            current = match.group(1)
            blocks[current] = []
            continue
        if current is not None:
            blocks[current].append(line)
    return blocks


def _short_volume_source(value: str) -> str | None:
    scalar = _yaml_scalar(value)
    if scalar == APP_DATA_TARGET:
        return "<anonymous>"
    match = _SHORT_VOLUME_RE.fullmatch(scalar)
    if match and _yaml_scalar(match.group("target")) == APP_DATA_TARGET:
        return _yaml_scalar(match.group("source"))
    return None


def _long_volume_field(value: str) -> tuple[str, str] | None:
    if ":" not in value:
        return None
    key, raw = value.split(":", 1)
    key = key.strip()
    if key not in {"source", "target"}:
        return None
    return key, _yaml_scalar(raw)


def _data_mount_source(block: list[str]) -> str | None:
    volumes_index: int | None = None
    volumes_indent = 0
    for index, line in enumerate(block):
        if line.strip() == "volumes:":
            volumes_index = index
            volumes_indent = _indent(line)
            break
    if volumes_index is None:
        return None

    long_entry: dict[str, str] = {}

    def resolved_long_entry() -> str | None:
        if long_entry.get("target") != APP_DATA_TARGET:
            return None
        return long_entry.get("source") or "<anonymous>"

    for line in block[volumes_index + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _indent(line) <= volumes_indent:
            break
        if stripped.startswith("- "):
            resolved = resolved_long_entry()
            if resolved is not None:
                return resolved
            long_entry = {}
            item = stripped[2:].strip()
            short_source = _short_volume_source(item)
            if short_source is not None:
                return short_source
            field = _long_volume_field(item)
            if field is not None:
                long_entry[field[0]] = field[1]
            continue
        field = _long_volume_field(stripped)
        if field is not None:
            long_entry[field[0]] = field[1]
    return resolved_long_entry()


def compose_app_data_mounts(text: str) -> dict[str, str | None]:
    blocks = _service_blocks(text)
    return {
        service: _data_mount_source(blocks[service])
        for service in APP_DATA_SERVICES
        if service in blocks
    }


def normalized_mount_source(source: str | None) -> str | None:
    if source is None:
        return None
    normalized = source.strip()
    default_match = _VARIABLE_DEFAULT_RE.fullmatch(normalized)
    if default_match:
        normalized = default_match.group(1).strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/") or "."


def app_data_mounts_are_aligned(mounts: dict[str, str | None]) -> bool:
    if len(mounts) < 2:
        return True
    return len({normalized_mount_source(source) for source in mounts.values()}) == 1
