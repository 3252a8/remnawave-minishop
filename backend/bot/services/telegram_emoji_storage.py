"""Rebuildable metadata/media and bot-scoped capability cache, without tokens."""

from __future__ import annotations

import os
import tempfile
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


def prune_cache(bot_id: int) -> None:
    """Discard oldest rebuildable entries; retain permission observations."""
    files = []
    for directory in ("media", "items", "sets"):
        for path in (ROOT / str(bot_id) / directory).glob("*"):
            if path.is_file() and path.suffix in {".bin", ".json"}:
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                files.append((stat.st_mtime, stat.st_size, path))
    size = sum(item[1] for item in files)
    for _modified, length, path in sorted(files):
        if size <= MAX_CACHE_BYTES:
            break
        path.unlink(missing_ok=True)
        size -= length


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


def _read(path: Path) -> str:
    if path.stat().st_size > MAX_METADATA_BYTES:
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
    atomic_bytes(item_path(bot_id, item.id), item.model_dump_json().encode("utf-8"))


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
    atomic_bytes(path, cached.model_dump_json().encode("utf-8"))
    for item in cached.items:
        save_item(bot_id, item)


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
