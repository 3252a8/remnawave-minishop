from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import PhotoSize, Sticker, StickerSet

from bot.services import telegram_emoji_catalog as catalog
from bot.services import telegram_emoji_storage as storage
from config.telegram_menu import TelegramEmojiLibrary


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
        assert result.items[0].thumbnail_url == "/api/admin/telegram-emoji/media/9007199254740993"
        assert "file_id" not in result.items[0].model_dump()
        await catalog.catalog(bot, TelegramEmojiLibrary(sets=["TestEmoji"]))
        assert bot.get_sticker_set.await_count == 1

    asyncio.run(run())


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
