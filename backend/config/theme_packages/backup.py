"""Consistent snapshots and validated theme restore, including owner overrides."""

from __future__ import annotations

import shutil
import time
import uuid
import zipfile
from pathlib import Path

from .archive import content_digest, inspect_theme
from .models import PackageError
from .paths import atomic_bytes, confined, registry_lock
from .registry import read_registry, write_registry

BACKUP_PREFIX = "config/themes/"


def snapshot_themes(source: Path, target: Path) -> bool:
    source = source.expanduser()
    if not source.is_dir():
        return False
    with registry_lock(source):
        for path in source.rglob("*"):
            relative = path.relative_to(source)
            if (
                relative.parts[0] in {"_imports", "_restore"}
                or relative.as_posix() == "_registry/lock"
            ):
                continue
            if path.is_symlink():
                raise PackageError("unsafe_theme_backup", relative.as_posix())
            if path.is_file() and not path.name.endswith(".tmp"):
                destination = confined(target, relative.as_posix())
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
    return True


def prepare_restore(archive: zipfile.ZipFile, temporary: Path) -> Path | None:
    members = [
        item
        for item in archive.infolist()
        if item.filename.startswith(BACKUP_PREFIX) and not item.is_dir()
    ]
    if not members:
        return None
    if len(members) > 20_000 or sum(item.file_size for item in members) > 1024 * 1024 * 1024:
        raise PackageError("theme_storage_full")
    target = temporary / "restored-themes"
    target.mkdir()
    for member in members:
        relative = member.filename[len(BACKUP_PREFIX) :]
        if relative.startswith("_imports/") or relative == "_registry/lock":
            raise PackageError("invalid_theme_backup")
        destination = confined(target, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output, length=64 * 1024)
    state = read_registry(target)
    for key, entry in state.entries.items():
        for version in [entry, *entry.history]:
            folder = confined(target, f"_packages/{version.digest}")
            candidate = inspect_theme(folder, key)
            if candidate.error or candidate.key != key or content_digest(folder) != version.digest:
                raise PackageError("invalid_theme_backup", key)
    return target


def restore_themes(prepared: Path, target: Path) -> None:
    """Restore packages first; atomically publish the catalogue last."""
    with registry_lock(target):
        current = read_registry(target)
        incoming = read_registry(prepared)
        # Preserve a complete local rescue snapshot before changing legacy files.
        rescue = target / "_restore"
        rescue.mkdir(exist_ok=True)
        previous = rescue / uuid.uuid4().hex
        previous.mkdir()
        for path in target.iterdir():
            if path.name.startswith("_"):
                continue
            if path.is_dir():
                shutil.copytree(path, previous / path.name)
        atomic_bytes(previous / "registry.json", current.model_dump_json().encode())
        for path in prepared.rglob("*"):
            relative = path.relative_to(prepared)
            if relative.parts[0] == "_registry" or not path.is_file():
                continue
            atomic_bytes(confined(target, relative.as_posix()), path.read_bytes())
        for key, entry in current.entries.items():
            incoming.retired.setdefault(key, {}).update(
                {version.digest: time.time() + 7 * 86400 for version in [entry, *entry.history]}
            )
        restored_keys = {path.parent.name for path in prepared.glob("*/theme.json")}
        restored_keys.update(incoming.entries)
        old_keys = {path.parent.name for path in target.glob("*/theme.json")}
        incoming.removed = sorted(set(incoming.removed) | (old_keys - restored_keys))
        incoming.generation = max(current.generation, incoming.generation)
        incoming.completed.clear()
        write_registry(target, incoming)
