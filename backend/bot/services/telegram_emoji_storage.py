"""Rebuildable metadata/media and bot-scoped capability cache, without tokens."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from bot.services.telegram_emoji_schemas import (
    CachedEmojiItem,
    CachedEmojiSet,
    EmojiCapabilities,
    EmojiCapability,
)
from config.telegram_menu import CUSTOM_EMOJI_ID_RE

ROOT = Path(__file__).resolve().parents[3] / "data" / "telegram-emoji"
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_CACHE_BYTES = 128 * 1024 * 1024
_CACHE_LOCK = threading.RLock()


class CacheFullError(OSError):
    """Pinned entries leave no room for another catalog or preview."""


def media_version(item: CachedEmojiItem) -> str:
    identity = item.thumbnail_unique_id or item.file_unique_id or item.file_id
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def media_path(bot_id: int, item: CachedEmojiItem) -> Path:
    item_path(bot_id, item.id)  # Validate before constructing a filesystem path.
    return ROOT / str(bot_id) / "media" / f"{item.id}-{media_version(item)}.bin"


@contextmanager
def _locked_cache(bot_id: int) -> Iterator[None]:
    """Protect capacity accounting on the shared backend/worker volume."""
    root = ROOT / str(bot_id)
    root.mkdir(parents=True, exist_ok=True)
    with _CACHE_LOCK, (root / ".lock").open("a+b") as stream:
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
                    raise OSError("emoji cache is busy") from None
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


def pin_library(bot_id: int, sets: list[CachedEmojiSet], manual: list[CachedEmojiItem]) -> None:
    """Active sets stay resident; removed sets remain available until space is needed."""
    paths: set[str] = set()
    for cached in sets:
        paths.add(f"sets/{cached.name.casefold()}.json")
    for item in [item for cached in sets for item in cached.items] + manual:
        paths.add(f"items/{item.id}.json")
        paths.add(f"media/{media_path(bot_id, item).name}")
    with _locked_cache(bot_id):
        atomic_bytes(ROOT / str(bot_id) / "pins.json", json.dumps(sorted(paths)).encode())


def _prune(bot_id: int, *, reserve: int = 0, replacing: set[Path] | None = None) -> bool:
    root = ROOT / str(bot_id)
    try:
        protected = set(json.loads(_read(root / "pins.json", 32 * 1024 * 1024)))
    except (OSError, ValueError):
        protected = set()
    files = []
    for directory in ("media", "items", "sets"):
        for path in (root / directory).glob("*"):
            if (
                path not in (replacing or set())
                and path.is_file()
                and path.suffix in {".bin", ".json"}
            ):
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                files.append((stat.st_mtime, stat.st_size, path))
    size = sum(item[1] for item in files) + reserve
    for _modified, length, path in sorted(files):
        if size <= MAX_CACHE_BYTES:
            return True
        if path.relative_to(root).as_posix() in protected:
            continue
        path.unlink(missing_ok=True)
        size -= length
    return size <= MAX_CACHE_BYTES


def prune_cache(bot_id: int) -> None:
    with _locked_cache(bot_id):
        _prune(bot_id)


def save_media(bot_id: int, item: CachedEmojiItem, content: bytes) -> bool:
    path = media_path(bot_id, item)
    with _locked_cache(bot_id):
        if not _prune(bot_id, reserve=len(content), replacing={path}):
            return False
        atomic_bytes(path, content)
    return True


def read_media(bot_id: int, item: CachedEmojiItem, maximum: int) -> bytes | None:
    path = media_path(bot_id, item)
    try:
        if not 0 < path.stat().st_size <= maximum:
            return None
        content = path.read_bytes()
        # Avoid writing on every view while making eviction favor recently used media.
        if time.time() - path.stat().st_mtime > 3600:
            path.touch()
        return content
    except OSError:
        return None


def media_header(bot_id: int, item: CachedEmojiItem, maximum: int) -> bytes | None:
    path = media_path(bot_id, item)
    try:
        if not 0 < path.stat().st_size <= maximum:
            return None
        with path.open("rb") as stream:
            return stream.read(16)
    except OSError:
        return None


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".emoji-", delete=False) as file:
            temporary = file.name
            file.write(content)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _read(path: Path, maximum: int = MAX_METADATA_BYTES) -> str:
    if path.stat().st_size > maximum:
        raise ValueError("emoji metadata is too large")
    return path.read_text(encoding="utf-8")


def item_path(bot_id: int, emoji_id: str) -> Path:
    if not CUSTOM_EMOJI_ID_RE.fullmatch(emoji_id):
        raise ValueError("invalid custom emoji ID")
    return ROOT / str(bot_id) / "items" / f"{emoji_id}.json"


def read_item(bot_id: int, emoji_id: str) -> CachedEmojiItem | None:
    try:
        return CachedEmojiItem.model_validate_json(_read(item_path(bot_id, emoji_id)))
    except (OSError, ValueError, ValidationError):
        return None


def save_item(bot_id: int, item: CachedEmojiItem) -> None:
    files = [(item_path(bot_id, item.id), item.model_dump_json().encode("utf-8"))]
    # A manually refreshed ID can also belong to an imported set. Keep its manifest
    # consistent so warming never keeps requesting an obsolete media version.
    cached = read_set(bot_id, item.set_name) if item.set_name else None
    if cached and any(previous.id == item.id and previous != item for previous in cached.items):
        cached.items = [item if previous.id == item.id else previous for previous in cached.items]
        path = ROOT / str(bot_id) / "sets" / f"{cached.name.casefold()}.json"
        files.append((path, cached.model_dump_json().encode("utf-8")))
    _save_metadata(bot_id, files)


def _save_metadata(bot_id: int, files: list[tuple[Path, bytes]]) -> None:
    if any(len(content) > MAX_METADATA_BYTES for _path, content in files):
        raise ValueError("emoji metadata is too large")
    with _locked_cache(bot_id):
        if not _prune(
            bot_id,
            reserve=sum(len(content) for _path, content in files),
            replacing={path for path, _content in files},
        ):
            raise CacheFullError("emoji cache is full")
        for path, content in files:
            atomic_bytes(path, content)


def read_set(bot_id: int, name: str) -> CachedEmojiSet | None:
    from config.telegram_menu import emoji_source

    kind, normalized = emoji_source(name)
    if kind != "set":
        return None
    try:
        path = ROOT / str(bot_id) / "sets" / f"{normalized.casefold()}.json"
        return CachedEmojiSet.model_validate_json(_read(path))
    except (OSError, ValueError, ValidationError):
        return None


def save_set(bot_id: int, cached: CachedEmojiSet) -> None:
    from config.telegram_menu import emoji_source

    _kind, name = emoji_source(cached.name)
    path = ROOT / str(bot_id) / "sets" / f"{name.casefold()}.json"
    files = [
        (item_path(bot_id, item.id), item.model_dump_json().encode("utf-8"))
        for item in cached.items
    ]
    files.append((path, cached.model_dump_json().encode("utf-8")))
    _save_metadata(bot_id, files)


def capabilities(bot_id: int) -> EmojiCapabilities:
    current = EmojiCapabilities()
    for feature in ("icon", "text"):
        try:
            path = ROOT / str(bot_id) / f"capability-{feature}.json"
            setattr(current, feature, EmojiCapability.model_validate_json(_read(path)))
        except (OSError, ValueError, ValidationError):
            pass
    return current


def record_capability(
    bot_id: int,
    feature: Literal["icon", "text"],
    supported: bool,
) -> EmojiCapabilities:
    current_value = EmojiCapability(
        state="supported" if supported else "unavailable",
        tested_at=datetime.now(UTC).isoformat(),
    )
    path = ROOT / str(bot_id) / f"capability-{feature}.json"
    atomic_bytes(path, current_value.model_dump_json().encode("utf-8"))
    return capabilities(bot_id)


def observe_capability(
    bot_id: int, feature: Literal["icon", "text"], supported: bool
) -> EmojiCapabilities:
    try:
        return record_capability(bot_id, feature, supported)
    except OSError:
        # Rebuildable cache failures must not fail an already delivered message.
        current = capabilities(bot_id)
        setattr(
            current,
            feature,
            EmojiCapability(
                state="supported" if supported else "unavailable",
                tested_at=datetime.now(UTC).isoformat(),
            ),
        )
        return current
