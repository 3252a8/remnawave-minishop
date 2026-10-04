"""Bounded disk-only preview batches; opening the palette never waits on Telegram here."""

from __future__ import annotations

import asyncio
import base64
import re

from bot.services import telegram_emoji_storage as storage
from bot.services.telegram_emoji_catalog import (
    MAX_MEDIA_BYTES,
    TelegramEmojiError,
    validated_format,
)
from bot.services.telegram_emoji_schemas import EmojiBatchPreview, EmojiPreviewBatchOut

MAX_ITEMS = 32
MAX_BATCH_BYTES = 4 * 1024 * 1024
_REFERENCE = re.compile(r"([1-9][0-9]{0,19}):([a-f0-9]{16})\Z")


def preview_references(value: str) -> list[tuple[str, str]]:
    values = value.split(",")
    if not value or len(values) > MAX_ITEMS or len(value) > MAX_ITEMS * 38:
        raise TelegramEmojiError("telegram_emoji_invalid_id", 400)
    result: list[tuple[str, str]] = []
    for value in values:
        match = _REFERENCE.fullmatch(value)
        if match is None:
            raise TelegramEmojiError("telegram_emoji_invalid_id", 400)
        reference = (match[1], match[2])
        if reference not in result:
            result.append(reference)
    return result


def _read_previews(bot_id: int, references: list[tuple[str, str]]) -> EmojiPreviewBatchOut:
    previews: list[EmojiBatchPreview] = []
    size = 0
    for identifier, version in references:
        item = storage.read_item(bot_id, identifier)
        if item is None or storage.media_version(item) != version:
            continue
        content = storage.read_media(bot_id, item, MAX_MEDIA_BYTES)
        if not content or size + len(content) > MAX_BATCH_BYTES:
            continue
        format_name = validated_format(content)
        mime = {
            "png": "image/png",
            "webp": "image/webp",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
        }.get(format_name or "")
        if mime is None:
            continue
        previews.append(
            EmojiBatchPreview.model_validate(
                {
                    "id": identifier,
                    "version": version,
                    "mime": mime,
                    "data": base64.b64encode(content).decode("ascii"),
                }
            )
        )
        size += len(content)
    return EmojiPreviewBatchOut(previews=previews)


async def cached_previews(bot_id: int, references: list[tuple[str, str]]) -> EmojiPreviewBatchOut:
    return await asyncio.to_thread(_read_previews, bot_id, references)
