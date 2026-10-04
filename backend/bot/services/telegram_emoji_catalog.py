"""Bot API catalog access with bounded local preview media and reusable metadata."""

from __future__ import annotations

import asyncio
import io
import time
import warnings
from collections.abc import Awaitable, Buffer, Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from weakref import WeakKeyDictionary

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Sticker
from aiohttp import ClientError
from PIL import Image, UnidentifiedImageError

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
WARM_CONCURRENCY = 6
WARM_RETRY_SECONDS = 600
_FORMAT_MIME = {"png": "image/png", "webp": "image/webp", "jpeg": "image/jpeg", "gif": "image/gif"}


@dataclass
class _BotCache:
    slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(WARM_CONCURRENCY))
    downloads: dict[str, asyncio.Task[tuple[bytes, str]]] = field(default_factory=dict)
    warming: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    retry_after: dict[str, float] = field(default_factory=dict)
    failures: dict[str, tuple[float, str, int]] = field(default_factory=dict)
    set_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    resolving: asyncio.Lock = field(default_factory=asyncio.Lock)


_CACHES: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[int, Path], _BotCache]] = (
    WeakKeyDictionary()
)


def _cache(bot: Bot) -> _BotCache:
    per_loop = _CACHES.setdefault(asyncio.get_running_loop(), {})
    key = (bot.id, storage.ROOT)
    if key not in per_loop:
        per_loop[key] = _BotCache()
    return per_loop[key]


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
    public = EmojiItem.model_validate(item.model_dump(include=set(EmojiItem.model_fields)))
    if public.thumbnail_url:
        public.thumbnail_url = _thumbnail_url(item)
    return public


def _thumbnail_url(item: CachedEmojiItem) -> str:
    return f"/api/admin/telegram-emoji/media/{item.id}?v={storage.media_version(item)}"


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
    item = CachedEmojiItem(
        id=identifier,
        fallback=fallback,
        set_name=sticker.set_name,
        thumbnail_url=f"/api/admin/telegram-emoji/media/{identifier}" if can_preview else None,
        format=format_name,
        file_id=sticker.file_id,
        file_unique_id=sticker.file_unique_id,
        thumbnail_file_id=thumbnail_file_id,
        thumbnail_unique_id=sticker.thumbnail.file_unique_id if sticker.thumbnail else "",
    )
    if can_preview:
        item.thumbnail_url = _thumbnail_url(item)
    return item


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
    lock = _cache(bot).set_locks.setdefault(normalized.casefold(), asyncio.Lock())
    async with lock:
        cached = await asyncio.to_thread(storage.read_set, bot.id, normalized)
        if cached and not refresh and time.time() - cached.saved_at < CATALOG_TTL_SECONDS:
            return cached
        retry_key = f"metadata:{normalized.casefold()}"
        if cached and not refresh and _cache(bot).retry_after.get(retry_key, 0) > time.time():
            return cached
        try:
            result = await _api(lambda: bot.get_sticker_set(normalized))
        except TelegramEmojiError:
            if cached and not refresh:
                _cache(bot).retry_after[retry_key] = time.time() + WARM_RETRY_SECONDS
                return cached  # Previously imported sets still work during Telegram outages.
            raise
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
        return cached


async def resolve_ids(
    bot: Bot, identifiers: list[str], *, refresh: bool = False
) -> list[CachedEmojiItem]:
    async with _cache(bot).resolving:
        return await _resolve_ids(bot, identifiers, refresh=refresh)


async def _resolve_ids(
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
    return [items[identifier] for identifier in unique]


def _missing(bot_id: int, items: list[CachedEmojiItem]) -> list[CachedEmojiItem]:
    return [
        item
        for item in items
        if item.thumbnail_url
        and not _media_format(storage.media_header(bot_id, item, MAX_MEDIA_BYTES) or b"")
    ]


async def _warm(bot: Bot, name: str, items: list[CachedEmojiItem]) -> None:
    """A bounded worker pool, rather than one task per emoji in a large set."""
    cache = _cache(bot)
    queue = iter(items)
    failed = False
    capacity_full = False

    async def worker() -> None:
        nonlocal failed, capacity_full
        for item in queue:
            if capacity_full:
                break
            try:
                await media(bot, item.id)
            except TelegramEmojiError as exc:
                failed = True
                if exc.status >= 500:
                    capacity_full = True
            except OSError:
                failed = capacity_full = True

    try:
        await asyncio.gather(*(worker() for _ in range(WARM_CONCURRENCY)))
    finally:
        if failed:
            cache.retry_after[name] = time.time() + WARM_RETRY_SECONDS


async def warm_library(bot: Bot, library: TelegramEmojiLibrary, *, retry: bool = False) -> None:
    """Start every media download at import; resume unfinished sets on the next visit."""
    sets = []
    for name in library.sets:
        cached = await asyncio.to_thread(storage.read_set, bot.id, name)
        if cached:
            sets.append(cached)
    manual = []
    for identifier in library.manual_ids:
        item = await asyncio.to_thread(storage.read_item, bot.id, identifier)
        if item:
            manual.append(item)
    await asyncio.to_thread(storage.pin_library, bot.id, sets, manual)
    cache = _cache(bot)
    if retry:
        cache.failures.clear()
    groups = [(cached.name.casefold(), cached.items) for cached in sets] + [("manual", manual)]
    for name, items in groups:
        task = cache.warming.get(name)
        if task and not task.done():
            continue
        if not retry and cache.retry_after.get(name, 0) > time.time():
            continue
        missing = await asyncio.to_thread(_missing, bot.id, items)
        if not missing:
            continue
        cache.retry_after.pop(name, None)
        task = asyncio.create_task(_warm(bot, name, missing))
        cache.warming[name] = task

        def finished(result: asyncio.Task[None], group: str = name) -> None:
            if cache.warming.get(group) is result:
                cache.warming.pop(group, None)
            if not result.cancelled() and result.exception() is not None:
                cache.retry_after[group] = time.time() + WARM_RETRY_SECONDS

        task.add_done_callback(finished)


async def stop_warming(bot: Bot) -> None:
    cache = _cache(bot)
    tasks: list[asyncio.Task[None] | asyncio.Task[tuple[bytes, str]]] = [
        task for task in cache.warming.values() if not task.done()
    ]
    tasks += [task for task in cache.downloads.values() if not task.done()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _CACHES.get(asyncio.get_running_loop(), {}).pop((bot.id, storage.ROOT), None)


async def library_sets(bot: Bot, library: TelegramEmojiLibrary) -> list[EmojiSetInfo]:
    sets: list[EmojiSetInfo] = []
    for name in library.sets:
        cached = await asyncio.to_thread(storage.read_set, bot.id, name)
        sets.append(
            EmojiSetInfo(
                name=name,
                title=cached.title if cached else name,
                count=len(cached.items) if cached else 0,
                state="unknown",
            )
        )
        if cached:
            previews = [item for item in cached.items if item.thumbnail_url]
            missing = await asyncio.to_thread(_missing, bot.id, previews)
            info = sets[-1]
            info.preview_count = len(previews)
            info.cached_count = len(previews) - len(missing)
            task = _cache(bot).warming.get(name.casefold())
            info.state = (
                "ready" if not missing else "warming" if task and not task.done() else "partial"
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
    if not identifiers:
        await warm_library(bot, library)
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


def _validated_format(content: bytes) -> str | None:
    format_name = _media_format(content)
    if format_name is None:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if min(image.size) < 1 or max(image.size) > 512:
                    return None
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image.load()  # WEBP verification alone does not decode a truncated frame.
        return format_name
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None


async def media(bot: Bot, identifier: str) -> tuple[bytes, str]:
    items = await resolve_ids(bot, [identifier])
    item = items[0]
    content = await asyncio.to_thread(storage.read_media, bot.id, item, MAX_MEDIA_BYTES)
    if content and (format_name := await asyncio.to_thread(_validated_format, content)):
        return content, _FORMAT_MIME[format_name]
    cache = _cache(bot)
    key = f"{item.id}-{storage.media_version(item)}"
    failure = cache.failures.get(key)
    if failure and failure[0] > time.time():
        raise TelegramEmojiError(failure[1], failure[2])
    cache.failures.pop(key, None)
    task = cache.downloads.get(key)
    if task is None:
        task = asyncio.create_task(_download(bot, item))
        cache.downloads[key] = task

        def finished(result: asyncio.Task[tuple[bytes, str]]) -> None:
            if cache.downloads.get(key) is result:
                cache.downloads.pop(key, None)
            if not result.cancelled():
                error = result.exception()  # Consume failures if every waiter disconnected.
                if isinstance(error, TelegramEmojiError):
                    cache.failures[key] = (time.time() + 60, error.code, error.status)
                    while len(cache.failures) > 2048:
                        cache.failures.pop(next(iter(cache.failures)))

        task.add_done_callback(finished)
    # Closing one picker/request must not cancel a download needed by another consumer.
    return await asyncio.shield(task)


async def _download(bot: Bot, item: CachedEmojiItem) -> tuple[bytes, str]:
    async with _cache(bot).slots:
        return await _download_in_slot(bot, item)


async def _download_in_slot(bot: Bot, item: CachedEmojiItem) -> tuple[bytes, str]:
    content_cached = await asyncio.to_thread(storage.read_media, bot.id, item, MAX_MEDIA_BYTES)
    if content_cached and (
        format_cached := await asyncio.to_thread(_validated_format, content_cached)
    ):
        return content_cached, _FORMAT_MIME[format_cached]
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
    format_name = await asyncio.to_thread(_validated_format, result)
    if format_name is None:
        raise TelegramEmojiError("telegram_emoji_preview_invalid", 415)
    if not await asyncio.to_thread(storage.save_media, bot.id, item, result):
        raise TelegramEmojiError("telegram_emoji_cache_full", 507)
    return result, _FORMAT_MIME[format_name]
