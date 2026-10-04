from __future__ import annotations

import asyncio
import base64
import io
import time
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from bot.services import telegram_emoji_catalog as catalog
from bot.services import telegram_emoji_previews as previews
from bot.services import telegram_emoji_storage as storage
from bot.services.telegram_emoji_schemas import CachedEmojiItem, CachedEmojiSet
from config.telegram_menu import TelegramEmojiLibrary


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (32, 32), "red").save(buffer, "PNG")
    return buffer.getvalue()


def saved_preview(monkeypatch, tmp_path) -> CachedEmojiItem:
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    item = CachedEmojiItem(
        id="5368651601797984900", fallback="📁", file_unique_id="folder", file_id="file"
    )
    storage.save_item(42, item)
    assert storage.save_media(42, item, png())
    return item


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1:x",
        "01:0123456789abcdef",
        "1:0123456789ABCDEF",
        ",",
        ",".join(["1:0123456789abcdef"] * 33),
    ],
)
def test_batch_query_is_bounded_and_strict(value) -> None:
    with pytest.raises(catalog.TelegramEmojiError):
        previews.preview_references(value)


def test_batch_reads_validated_previews_from_disk_without_a_bot(monkeypatch, tmp_path) -> None:
    item = saved_preview(monkeypatch, tmp_path)
    version = storage.media_version(item)
    result = asyncio.run(previews.cached_previews(42, [(item.id, version), (item.id, "0" * 16)]))
    assert len(result.previews) == 1
    assert result.previews[0].mime == "image/png"
    assert base64.b64decode(result.previews[0].data) == png()
    assert not asyncio.run(previews.cached_previews(43, [(item.id, version)])).previews
    assert previews.preview_references(f"{item.id}:{version},{item.id}:{version}") == [
        (item.id, version)
    ]


def test_batch_skips_corrupt_or_oversized_files(monkeypatch, tmp_path) -> None:
    item = saved_preview(monkeypatch, tmp_path)
    version = storage.media_version(item)
    monkeypatch.setattr(previews, "MAX_BATCH_BYTES", len(png()) - 1)
    assert not asyncio.run(previews.cached_previews(42, [(item.id, version)])).previews
    monkeypatch.setattr(previews, "MAX_BATCH_BYTES", 4096)
    assert storage.save_media(42, item, b"\x89PNG\r\n\x1a\ncorrupt")
    assert not asyncio.run(previews.cached_previews(42, [(item.id, version)])).previews


def test_expired_catalog_returns_disk_data_before_telegram_refresh_finishes(
    monkeypatch, tmp_path
) -> None:
    item = saved_preview(monkeypatch, tmp_path)
    storage.save_set(
        42,
        CachedEmojiSet(name="TestEmoji", title="Cached", saved_at=time.time() - 7200, items=[item]),
    )
    bot = AsyncMock()
    bot.id = 42

    async def scenario() -> None:
        async def slow_refresh(*args, **kwargs):
            await asyncio.Event().wait()

        monkeypatch.setattr(catalog, "load_set", slow_refresh)
        result = await asyncio.wait_for(
            catalog.catalog(bot, TelegramEmojiLibrary(sets=["TestEmoji"])), 1
        )
        assert result.total == 1 and result.items[0].id == item.id
        await catalog.stop_warming(bot)

    asyncio.run(scenario())
