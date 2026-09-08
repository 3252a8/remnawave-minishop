"""Portable paths and crash-safe registry writes."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from .models import PackageError

_LOCK = threading.RLock()
RESERVED = re.compile(r"^(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)", re.I)


def relative_path(value: str, *, allow_dot: bool = False, max_length: int = 220) -> str:
    if allow_dot and value in ("", "."):
        return "."
    if (
        not value
        or len(value) > max_length
        or "\\" in value
        or "\x00" in value
        or value.startswith("/")
        or any(ord(ch) < 32 for ch in value)
    ):
        raise PackageError("unsafe_path", value[:220])
    parts = value.split("/")
    if any(
        part in ("", ".", "..")
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", part)
        or part.endswith((".", " "))
        or RESERVED.match(part)
        for part in parts
    ):
        raise PackageError("unsafe_path", value)
    return PurePosixPath(*parts).as_posix()


def confined(root: Path, value: str) -> Path:
    relative = relative_path(value, allow_dot=True, max_length=512)
    path = root / relative
    base = root.resolve()
    for item in (path, *path.parents):
        if item == root.parent:
            break
        if item.is_symlink():
            raise PackageError("unsafe_path", value)
    if not path.resolve().is_relative_to(base):
        raise PackageError("unsafe_path", value)
    return path


def atomic_model(path: Path, model: BaseModel) -> None:
    atomic_bytes(path, (model.model_dump_json(indent=2) + "\n").encode("utf-8"))


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        if sys.platform != "win32":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        tmp.unlink(missing_ok=True)


@contextlib.contextmanager
def registry_lock(root: Path) -> Iterator[None]:
    """One lock for all threads/processes sharing the same persistent volume."""
    root.mkdir(parents=True, exist_ok=True)
    state_dir = confined(root, "_registry")
    state_dir.mkdir(exist_ok=True)
    with _LOCK, (state_dir / "lock").open("a+b") as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + 10
        while True:
            stream.seek(0)
            try:
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise PackageError("themes_busy", status=409) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_json(path: Path) -> object:
    if path.stat().st_size > 1024 * 1024:
        raise PackageError("manifest_too_large", path.name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise PackageError("invalid_json", path.name) from exc
