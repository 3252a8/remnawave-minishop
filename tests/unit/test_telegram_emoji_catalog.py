from __future__ import annotations

import asyncio
import io
import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import PhotoSize, Sticker, StickerSet
from PIL import Image

from bot.services import telegram_emoji_catalog as catalog
from bot.services import telegram_emoji_storage as storage
from config.telegram_menu import TelegramEmojiLibrary


def preview_png() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (4, 4), "red").save(output, "PNG")
    return output.getvalue()


def sticker(identifier: str = "9007199254740993") -> Sticker:
    return Sticker(
        file_id="telegram-file",
        file_unique_id="telegram-unique",
        type="custom_emoji",
        width=100,
        height=100,
        is_animated=True,
        is_video=False,
        emoji="🙂",
        custom_emoji_id=identifier,
        set_name="TestEmoji",
        thumbnail=PhotoSize(
            file_id="thumbnail-file", file_unique_id="thumb-unique", width=100, height=100
        ),
    )


def test_catalog_deduplicates_set_and_manual_ids_and_keeps_token_private(
    tmp_path, monkeypatch
) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = MagicMock(spec=Bot)
        bot.id = 1234
        bot.get_sticker_set = AsyncMock(
            return_value=StickerSet(
                name="TestEmoji", title="Test", sticker_type="custom_emoji", stickers=[sticker()]
            )
        )
        bot.get_custom_emoji_stickers = AsyncMock(return_value=[sticker()])
        result = await catalog.catalog(
            bot, TelegramEmojiLibrary(sets=["TestEmoji"], manual_ids=["9007199254740993"])
        )
        assert result.total == 1
        assert result.items[0].id == "9007199254740993"
        assert result.items[0].thumbnail_url.startswith(
            "/api/admin/telegram-emoji/media/9007199254740993?v="
        )
        assert "file_id" not in result.items[0].model_dump()
        await catalog.catalog(bot, TelegramEmojiLibrary(sets=["TestEmoji"]))
        assert bot.get_sticker_set.await_count == 1

    asyncio.run(run())


def media_bot() -> MagicMock:
    bot = MagicMock(spec=Bot)
    bot.id = 1234
    bot.get_custom_emoji_stickers = AsyncMock(return_value=[sticker()])
    bot.get_file = AsyncMock(return_value=MagicMock(file_path="private/image", file_size=32))

    async def download(path, destination, **kwargs):
        destination.write(preview_png())

    bot.download_file = AsyncMock(side_effect=download)
    return bot


def test_immutable_disk_cache_survives_age_and_loop_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    bot = media_bot()
    first = asyncio.run(catalog.media(bot, "9007199254740993"))
    item = storage.read_item(bot.id, "9007199254740993")
    path = storage.media_path(bot.id, item)
    old = time.time() - 30 * 86400
    os.utime(path, (old, old))
    second = asyncio.run(catalog.media(bot, item.id))
    assert first == second
    assert bot.download_file.await_count == bot.get_file.await_count == 1
    assert path.stat().st_mtime > old
    assert storage.read_media(9999, item, catalog.MAX_MEDIA_BYTES) is None


def test_shared_download_survives_one_cancelled_view(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = media_bot()
        entered = asyncio.Event()
        release = asyncio.Event()

        async def download(path, destination, **kwargs):
            entered.set()
            await release.wait()
            destination.write(preview_png())

        bot.download_file.side_effect = download
        first = asyncio.create_task(catalog.media(bot, "9007199254740993"))
        await entered.wait()
        second = asyncio.create_task(catalog.media(bot, "9007199254740993"))
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert (await second)[1] == "image/png"
        assert bot.download_file.await_count == 1

    asyncio.run(run())


def test_changed_thumbnail_version_does_not_reuse_old_media(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = media_bot()
        await catalog.media(bot, "9007199254740993")
        old = storage.read_item(bot.id, "9007199254740993")
        storage.save_set(
            bot.id, catalog.CachedEmojiSet(name="TestEmoji", title="Test", saved_at=0, items=[old])
        )
        changed = sticker().model_copy(
            update={
                "thumbnail": PhotoSize(
                    file_id="new-thumbnail", file_unique_id="new-unique", width=100, height=100
                )
            }
        )
        bot.get_custom_emoji_stickers.return_value = [changed]
        new = (await catalog.resolve_ids(bot, [old.id], refresh=True))[0]
        assert new.thumbnail_url != old.thumbnail_url
        assert storage.read_set(bot.id, "TestEmoji").items[0].thumbnail_url == new.thumbnail_url
        await catalog.media(bot, old.id)
        assert bot.get_file.await_count == 2
        assert bot.get_file.call_args.args == ("new-thumbnail",)

    asyncio.run(run())


def test_cached_catalog_remains_available_during_telegram_outage(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = media_bot()
        item = catalog._item(sticker())
        cached = catalog.CachedEmojiSet(name="TestEmoji", title="Test", saved_at=0, items=[item])
        storage.save_set(bot.id, cached)
        await catalog.media(bot, item.id)
        bot.get_sticker_set = AsyncMock(side_effect=OSError("offline"))
        library = TelegramEmojiLibrary(sets=["TestEmoji"])
        assert (await catalog.catalog(bot, library)).total == 1
        assert (await catalog.catalog(bot, library)).total == 1
        assert bot.get_sticker_set.await_count == 1
        with pytest.raises(catalog.TelegramEmojiError):
            await catalog.load_set(bot, "TestEmoji", refresh=True)

    asyncio.run(run())


def test_library_warms_the_entire_set_without_a_catalog_view(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = media_bot()
        items = [sticker(str(9007199254740993 + index)) for index in range(96)]
        bot.get_sticker_set = AsyncMock(
            return_value=StickerSet(
                name="TestEmoji", title="Test", sticker_type="custom_emoji", stickers=items
            )
        )
        active = peak = 0

        async def download(path, destination, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            destination.write(preview_png())
            active -= 1

        bot.download_file.side_effect = download
        await catalog.load_set(bot, "TestEmoji", refresh=True)
        library = TelegramEmojiLibrary(sets=["TestEmoji"])
        await catalog.warm_library(bot, library)
        task = catalog._cache(bot).warming["testemoji"]
        await task
        info = (await catalog.library_sets(bot, library))[0]
        assert info.state == "ready"
        assert info.cached_count == info.preview_count == info.count == 96
        assert 0 < peak <= catalog.WARM_CONCURRENCY
        assert bot.download_file.await_count == 96
        # A subsequent opening (and even a loop restart) uses the persistent media.
        await catalog.warm_library(bot, library)
        assert bot.download_file.await_count == 96
        storage.media_path(bot.id, storage.read_item(bot.id, items[-1].custom_emoji_id)).unlink()
        await catalog.stop_warming(bot)
        await catalog.warm_library(bot, library)
        await catalog._cache(bot).warming["testemoji"]
        assert bot.download_file.await_count == 97

    asyncio.run(run())


def test_warm_failure_keeps_partial_media_and_retries_on_refresh(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = media_bot()
        items = [sticker("111"), sticker("222")]
        bot.get_sticker_set = AsyncMock(
            return_value=StickerSet(
                name="TestEmoji", title="Test", sticker_type="custom_emoji", stickers=items
            )
        )
        await catalog.load_set(bot, "TestEmoji")
        library = TelegramEmojiLibrary(sets=["TestEmoji"])
        bot.download_file.side_effect = OSError("network unavailable")
        await catalog.warm_library(bot, library)
        await catalog._cache(bot).warming["testemoji"]
        info = (await catalog.library_sets(bot, library))[0]
        assert info.state == "partial" and info.cached_count == 0
        calls = bot.get_file.await_count
        await catalog.warm_library(bot, library)
        assert bot.get_file.await_count == calls  # Polling does not create a retry storm.
        bot.download_file.side_effect = media_bot().download_file.side_effect
        await catalog.warm_library(bot, library, retry=True)
        await catalog._cache(bot).warming["testemoji"]
        assert (await catalog.library_sets(bot, library))[0].state == "ready"

    asyncio.run(run())


def test_active_set_is_pinned_and_capacity_does_not_cause_eviction_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    item = catalog._item(sticker())
    cached = catalog.CachedEmojiSet(name="TestEmoji", title="Test", saved_at=0, items=[item])
    storage.save_set(1234, cached)
    storage.pin_library(1234, [cached], [])
    payload = b"\x89PNG\r\n\x1a\nimage"
    assert storage.save_media(1234, item, payload)
    size = sum(
        path.stat().st_size
        for directory in ("sets", "items", "media")
        for path in (tmp_path / "1234" / directory).glob("*")
    )
    monkeypatch.setattr(storage, "MAX_CACHE_BYTES", size)
    second = catalog._item(sticker("222"))
    assert not storage.save_media(1234, second, payload)
    assert storage.read_media(1234, item, catalog.MAX_MEDIA_BYTES) == payload
    storage.pin_library(1234, [], [])
    assert storage.save_media(1234, second, payload)


def test_resolves_ids_in_api_batches_and_preserves_decimal_precision(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = MagicMock(spec=Bot)
        bot.id = 1234
        identifiers = [str(9007199254740993 + value) for value in range(201)]

        async def resolve(custom_emoji_ids):
            return [sticker(identifier) for identifier in custom_emoji_ids]

        bot.get_custom_emoji_stickers = AsyncMock(side_effect=resolve)
        result = await catalog.resolve_ids(bot, identifiers)
        assert [item.id for item in result] == identifiers
        assert [
            len(call.kwargs["custom_emoji_ids"])
            for call in bot.get_custom_emoji_stickers.call_args_list
        ] == [200, 1]

    asyncio.run(run())


def test_normal_sticker_sets_and_path_like_ids_are_rejected(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = MagicMock(spec=Bot)
        bot.id = 1234
        bot.get_sticker_set = AsyncMock(
            return_value=StickerSet(
                name="TestEmoji", title="Test", sticker_type="regular", stickers=[]
            )
        )
        with pytest.raises(catalog.TelegramEmojiError, match="not_custom"):
            await catalog.load_set(bot, "TestEmoji")
        with pytest.raises(catalog.TelegramEmojiError, match="invalid_id"):
            await catalog.resolve_ids(bot, ["../secret"])

    asyncio.run(run())


def test_binary_preview_uses_thumbnail_and_rejects_non_image_content(tmp_path, monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = MagicMock(spec=Bot)
        bot.id = 1234
        bot.get_custom_emoji_stickers = AsyncMock(return_value=[sticker()])
        bot.get_file = AsyncMock(
            return_value=MagicMock(file_path="private/thumbnail", file_size=30)
        )

        async def download(path, destination, **kwargs):
            destination.write(b"<html>not an image</html>")

        bot.download_file = AsyncMock(side_effect=download)
        with pytest.raises(catalog.TelegramEmojiError, match="preview_invalid"):
            await catalog.media(bot, "9007199254740993")
        bot.get_file.assert_awaited_once_with("thumbnail-file")
        assert not (tmp_path / "1234" / "media" / "9007199254740993.bin").exists()

    asyncio.run(run())


def test_corrupted_cached_image_is_repaired_instead_of_becoming_permanent(tmp_path, monkeypatch):
    async def run() -> None:
        monkeypatch.setattr(storage, "ROOT", tmp_path)
        bot = media_bot()
        item = catalog._item(sticker())
        storage.save_item(bot.id, item)
        path = storage.media_path(bot.id, item)
        storage.atomic_bytes(path, b"\x89PNG\r\n\x1a\ntruncated")
        content, mime = await catalog.media(bot, item.id)
        assert content == preview_png() and mime == "image/png"
        assert bot.download_file.await_count == 1
        assert path.read_bytes() == content

    asyncio.run(run())
