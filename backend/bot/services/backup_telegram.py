"""Telegram delivery of backup ZIPs with bounded multipart uploads."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramEntityTooLarge, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import FSInputFile, InputMediaDocument

from bot.middlewares.i18n import get_i18n_instance
from bot.services.backup_parts import BACKUP_PART_BYTES, split_backup

logger = logging.getLogger(__name__)
MEDIA_GROUP_MAX_FILES = 10
SEND_ATTEMPTS = 3


async def _send_batch(
    bot: Bot, documents: list[InputMediaDocument], chat_id: int, thread_id: int | None
) -> None:
    for attempt in range(SEND_ATTEMPTS):
        try:
            if len(documents) == 1:
                document = documents[0]
                await bot.send_document(
                    chat_id=chat_id,
                    document=document.media,
                    caption=document.caption,
                    parse_mode=None,
                    message_thread_id=thread_id,
                    request_timeout=180,
                )
            else:
                await bot.send_media_group(
                    chat_id=chat_id,
                    media=list(documents),
                    message_thread_id=thread_id,
                    request_timeout=600,
                )
            return
        except TelegramRetryAfter as exc:
            if attempt == SEND_ATTEMPTS - 1:
                raise
            await asyncio.sleep(exc.retry_after)
        except TelegramEntityTooLarge:
            raise
        except TelegramNetworkError:
            if attempt == SEND_ATTEMPTS - 1:
                raise
            await asyncio.sleep(2 ** (attempt + 1))


async def send_backup_parts(
    bot: Bot,
    archive_path: Path,
    *,
    chat_id: int,
    thread_id: int | None,
    caption: str,
    language: str,
    part_bytes: int | None = None,
) -> None:
    i18n = get_i18n_instance()
    with tempfile.TemporaryDirectory(
        prefix="telegram-parts-", dir=archive_path.parent
    ) as temporary:
        parts, manifest_path = await asyncio.to_thread(
            split_backup,
            archive_path,
            Path(temporary),
            part_bytes=BACKUP_PART_BYTES if part_bytes is None else part_bytes,
        )
        manifest_caption = i18n.gettext(
            language, "backup_parts_manifest_caption", name=archive_path.name, count=len(parts)
        )
        documents = [
            InputMediaDocument(
                media=FSInputFile(manifest_path),
                caption=f"{manifest_caption}\n\n{caption}"[:1024],
                parse_mode=None,
            )
        ]
        documents.extend(
            InputMediaDocument(
                media=FSInputFile(part.path),
                caption=i18n.gettext(
                    language,
                    "backup_part_caption",
                    name=archive_path.name,
                    index=index,
                    count=len(parts),
                )[:1024],
                parse_mode=None,
            )
            for index, part in enumerate(parts, start=1)
        )
        delivered = 0
        try:
            for start in range(0, len(documents), MEDIA_GROUP_MAX_FILES):
                batch = documents[start : start + MEDIA_GROUP_MAX_FILES]
                try:
                    await _send_batch(bot, batch, chat_id, thread_id)
                    delivered += len(batch)
                except TelegramEntityTooLarge:
                    if len(batch) == 1:
                        raise
                    # Some gateways cap the whole multipart request, even for an album.
                    for document in batch:
                        await _send_batch(bot, [document], chat_id, thread_id)
                        delivered += 1
        except Exception as exc:
            logger.exception(
                "Backup delivery incomplete archive=%s delivered_files=%s total_files=%s",
                archive_path.name,
                delivered,
                len(documents),
            )
            raise RuntimeError(
                i18n.gettext(
                    language,
                    "backup_parts_delivery_failed",
                    name=archive_path.name,
                    delivered=delivered,
                    total=len(documents),
                )
            ) from exc
        logger.info("Backup parts delivered archive=%s parts=%s", archive_path.name, len(parts))


def needs_backup_parts(archive_path: Path) -> bool:
    return archive_path.stat().st_size > BACKUP_PART_BYTES
