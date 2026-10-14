"""Traverse first-party sources without descending into installed toolchains."""

from collections.abc import Iterator
from pathlib import Path


def iter_source_files(base: Path, extensions: set[str]) -> Iterator[Path]:
    if not base.exists():
        return
    if base.is_file():
        if base.suffix.lower() in extensions:
            yield base
        return
    for directory, directories, names in base.walk():
        directories[:] = [
            name
            for name in directories
            if name not in {"node_modules", ".git", "__pycache__", "graphify-out"}
            and not name.startswith((".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache"))
        ]
        for name in names:
            if Path(name).suffix.lower() in extensions:
                yield directory / name
