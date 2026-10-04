"""Bot API catalog access with bounded local preview media and reusable metadata."""

from __future__ import annotations

import asyncio
import io
import time
from collections.abc import Awaitable, Buffer, Callable
from functools import partial

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Sticker
from aiohttp import ClientError

from bot.services import telegram_emoji_storage as storage
from bot.services.telegram_emoji_schemas import (
    CachedEmojiItem,
    CachedEmojiSet,
    EmojiCatalogOut,
    EmojiItem,
    EmojiSetInfo,
)
from bot.utils.custom_emoji import valid_emoji_fallback
from config.telegram_menu import CUSTOM_EMOJI_ID_RE, TelegramEmojiLibrary, emoji_source

CATALOG_TTL_SECONDS = 3600
MAX_MEDIA_BYTES = 2 * 1024 * 1024
_FORMAT_MIME = {"png": "image/png", "webp": "image/webp", "jpeg": "image/jpeg", "gif": "image/gif"}


class _PreviewBuffer(io.BytesIO):
    def write(self, value: Buffer, /) -> int:
        if self.tell() + memoryview(value).nbytes > MAX_MEDIA_BYTES:
            raise TelegramEmojiError("telegram_emoji_preview_too_large", 413)
        return super().write(value)


class TelegramEmojiError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _public(item: CachedEmojiItem) -> EmojiItem:
    return EmojiItem.model_validate(item.model_dump(include=set(EmojiItem.model_fields)))


def _item(sticker: Sticker) -> CachedEmojiItem:
    identifier = sticker.custom_emoji_id or ""
    if not CUSTOM_EMOJI_ID_RE.fullmatch(identifier):
        raise TelegramEmojiError("telegram_emoji_not_custom")
    fallback = sticker.emoji or "🙂"
    if not valid_emoji_fallback(fallback):
        fallback = "🙂"
    format_name = "animated" if sticker.is_animated else "video" if sticker.is_video else "static"
    thumbnail_file_id = sticker.thumbnail.file_id if sticker.thumbnail else None
    can_preview = bool(thumbnail_file_id) or format_name == "static"
    return CachedEmojiItem(
        id=identifier,
        fallback=fallback,
        set_name=sticker.set_name,
        thumbnail_url=f"/api/admin/telegram-emoji/media/{identifier}" if can_preview else None,
        format=format_name,
        file_id=sticker.file_id,
        file_unique_id=sticker.file_unique_id,
        thumbnail_file_id=thumbnail_file_id,
    )


async def _api[T](operation: Callable[[], Awaitable[T]]) -> T:
    try:
        return await asyncio.wait_for(operation(), timeout=15)
    except TelegramBadRequest as exc:
        raise TelegramEmojiError("telegram_emoji_invalid_source") from exc
    except (TelegramAPIError, TimeoutError, OSError, ClientError) as exc:
        raise TelegramEmojiError("telegram_emoji_unavailable", 503) from exc


async def load_set(bot: Bot, name: str, *, refresh: bool = False) -> CachedEmojiSet:
    kind, normalized = emoji_source(name)
    if kind != "set":
        raise TelegramEmojiError("telegram_emoji_invalid_source")
    cached = await asyncio.to_thread(storage.read_set, bot.id, normalized)
    if cached and not refresh and time.time() - cached.saved_at < CATALOG_TTL_SECONDS:
        return cached
    result = await _api(lambda: bot.get_sticker_set(normalized))
    if result.sticker_type != "custom_emoji":
        raise TelegramEmojiError("telegram_emoji_not_custom")
    if len(result.stickers) > 10000:
        raise TelegramEmojiError("telegram_emoji_set_too_large")
    cached = CachedEmojiSet(
        name=result.name,
        title=result.title,
        saved_at=time.time(),
        items=[_item(sticker) for sticker in result.stickers],
    )
    await asyncio.to_thread(storage.save_set, bot.id, cached)
    await asyncio.to_thread(storage.prune_cache, bot.id)
    return cached


async def resolve_ids(
    bot: Bot, identifiers: list[str], *, refresh: bool = False
) -> list[CachedEmojiItem]:
    unique = list(dict.fromkeys(identifiers))
    if len(unique) > 500 or any(not CUSTOM_EMOJI_ID_RE.fullmatch(item) for item in unique):
        raise TelegramEmojiError("telegram_emoji_invalid_id")
    items: dict[str, CachedEmojiItem] = {}
    missing: list[str] = []
    for identifier in unique:
        cached = await asyncio.to_thread(storage.read_item, bot.id, identifier)
        if cached and not refresh:
            items[identifier] = cached
        else:
            missing.append(identifier)
    for offset in range(0, len(missing), 200):
        batch = missing[offset : offset + 200]
        stickers = await _api(partial(bot.get_custom_emoji_stickers, custom_emoji_ids=batch))
        for sticker in stickers:
            item = _item(sticker)
            if item.id not in batch:
                continue
            items[item.id] = item
            await asyncio.to_thread(storage.save_item, bot.id, item)
    if any(identifier not in items for identifier in unique):
        raise TelegramEmojiError("telegram_emoji_not_found")
    if missing:
        await asyncio.to_thread(storage.prune_cache, bot.id)
    return [items[identifier] for identifier in unique]


async def library_sets(bot: Bot, library: TelegramEmojiLibrary) -> list[EmojiSetInfo]:
    sets: list[EmojiSetInfo] = []
    for name in library.sets:
        cached = await asyncio.to_thread(storage.read_set, bot.id, name)
        sets.append(
            EmojiSetInfo(
                name=name,
                title=cached.title if cached else name,
                count=len(cached.items) if cached else 0,
                state="ready" if cached else "unknown",
            )
        )
    return sets


async def catalog(
    bot: Bot,
    library: TelegramEmojiLibrary,
    *,
    set_name: str = "",
    query: str = "",
    offset: int = 0,
    limit: int = 60,
    identifiers: list[str] | None = None,
) -> EmojiCatalogOut:
    if offset < 0 or not 1 <= limit <= 60 or len(query) > 128:
        raise TelegramEmojiError("telegram_emoji_invalid_query")
    items: dict[str, CachedEmojiItem] = {}
    if identifiers:
        for item in await resolve_ids(bot, identifiers):
            items[item.id] = item
    else:
        selected = library.sets
        if set_name:
            selected = [name for name in selected if name.casefold() == set_name.casefold()]
            if not selected:
                raise TelegramEmojiError("telegram_emoji_unknown_set")
        for name in selected:
            cached = await load_set(bot, name)
            for item in cached.items:
                items.setdefault(item.id, item)
        if not set_name:
            for item in await resolve_ids(bot, library.manual_ids):
                items.setdefault(item.id, item)
    search = query.strip().casefold()
    filtered = [
        item
        for item in items.values()
        if not search
        or search in item.id
        or search in item.fallback.casefold()
        or search in (item.set_name or "").casefold()
    ]
    return EmojiCatalogOut(
        items=[_public(item) for item in filtered[offset : offset + limit]],
        total=len(filtered),
        offset=offset,
        limit=limit,
    )


def _media_format(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return None


async def media(bot: Bot, identifier: str) -> tuple[bytes, str]:
    items = await resolve_ids(bot, [identifier])
    item = items[0]
    directory = storage.ROOT / str(bot.id) / "media"
    path = directory / f"{identifier}.bin"
    if (
        path.is_file()
        and path.stat().st_size <= MAX_MEDIA_BYTES
        and time.time() - path.stat().st_mtime < 86400
    ):
        content = await asyncio.to_thread(path.read_bytes)
        if format_name := _media_format(content):
            return content, _FORMAT_MIME[format_name]
    file_id = item.thumbnail_file_id or (item.file_id if item.format == "static" else "")
    if not file_id:
        raise TelegramEmojiError("telegram_emoji_preview_unavailable", 404)
    file = await _api(lambda: bot.get_file(file_id))
    if not file.file_path or (file.file_size is not None and file.file_size > MAX_MEDIA_BYTES):
        raise TelegramEmojiError("telegram_emoji_preview_too_large", 413)
    # The shared client supports proxies and local Bot API file paths. Never return its URL.
    content = _PreviewBuffer()
    await _api(
        partial(
            bot.download_file, file.file_path, destination=content, timeout=15, chunk_size=65536
        )
    )
    result = content.getvalue()
    format_name = _media_format(result)
    if format_name is None:
        raise TelegramEmojiError("telegram_emoji_preview_invalid", 415)
    await asyncio.to_thread(storage.atomic_bytes, path, result)
    await asyncio.to_thread(storage.prune_cache, bot.id)
    return result, _FORMAT_MIME[format_name]
