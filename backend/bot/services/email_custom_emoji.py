"""Resolve Telegram entities to bounded PNG CID attachments before SMTP delivery."""

from __future__ import annotations

import asyncio
import html
import io
import re
from collections.abc import Sequence
from contextlib import suppress

from aiogram import Bot
from PIL import Image, UnidentifiedImageError

from bot.app.factories.telegram_bot import create_telegram_bot
from bot.services.email_templates_common import EmailInlineImage
from bot.services.telegram_emoji_catalog import (
    MAX_MEDIA_BYTES,
    TelegramEmojiError,
    media,
    resolve_ids,
)
from bot.utils.custom_emoji import valid_emoji_fallback
from config.settings import Settings
from config.telegram_menu import CUSTOM_EMOJI_ID_RE

MAX_EMAIL_EMOJI = 128
MAX_EMAIL_EMOJI_BYTES = 4 * 1024 * 1024
MAX_EMOJI_PNG_BYTES = 64 * 1024
EMOJI_PREPARE_TIMEOUT = 8
_MARKER_RE = re.compile(r'<span data-telegram-emoji-id="([^"<>]*)">([^<>]*)</span>')
_RASTER_MIMES = {"image/png", "image/webp", "image/jpeg", "image/gif"}


def _png_preview(content: bytes, mime: str) -> bytes | None:
    if mime not in _RASTER_MIMES or not content or len(content) > MAX_MEDIA_BYTES:
        return None
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in {"PNG", "WEBP", "JPEG", "GIF"}:
                return None
            if min(source.size) < 1 or max(source.size) > 512:
                return None
            source.seek(0)
            image = source.convert("RGBA")
            image.thumbnail((100, 100), Image.Resampling.LANCZOS)
            result = io.BytesIO()
            image.save(result, format="PNG")
        data = result.getvalue()
        return data if len(data) <= MAX_EMOJI_PNG_BYTES else None
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


async def _load_previews(bot: Bot, identifiers: list[str], images: dict[str, bytes]) -> None:
    # One unavailable ID must not suppress already cached previews of the others.
    with suppress(TelegramEmojiError, OSError):
        # One Bot API batch for uncached metadata, including a complete 96-item set.
        await resolve_ids(bot, identifiers)
    semaphore = asyncio.Semaphore(8)

    async def load(identifier: str) -> None:
        async with semaphore:
            try:
                content, mime = await media(bot, identifier)
                preview = await asyncio.to_thread(_png_preview, content, mime)
            except (TelegramEmojiError, OSError, ValueError):
                return
            if preview:
                images[identifier] = preview

    await asyncio.gather(*(load(identifier) for identifier in identifiers))


async def prepare_email_custom_emoji(
    settings: Settings,
    html_body: str | None,
    inline_images: Sequence[EmailInlineImage],
) -> tuple[str | None, tuple[EmailInlineImage, ...]]:
    """Keep Unicode text on failure; never put a Bot API URL/token in a message."""
    if not html_body or "data-telegram-emoji-id" not in html_body:
        return html_body, tuple(inline_images)
    identifiers = list(
        dict.fromkeys(
            match[1]
            for match in _MARKER_RE.finditer(html_body)
            if CUSTOM_EMOJI_ID_RE.fullmatch(match[1])
            and valid_emoji_fallback(html.unescape(match[2]))
        )
    )[:MAX_EMAIL_EMOJI]
    images: dict[str, bytes] = {}
    if identifiers and settings.BOT_TOKEN:
        try:
            async with asyncio.timeout(EMOJI_PREPARE_TIMEOUT):
                async with create_telegram_bot(settings).context() as bot:
                    await _load_previews(bot, identifiers, images)
        except (TelegramEmojiError, OSError, ValueError, TimeoutError):
            pass

    attachments = list(inline_images)
    attached: dict[str, str] = {}
    total_bytes = 0

    def replace_marker(match: re.Match[str]) -> str:
        nonlocal total_bytes
        identifier, escaped_fallback = match[1], match[2]
        fallback = html.unescape(escaped_fallback)
        if not valid_emoji_fallback(fallback) or not (preview := images.get(identifier)):
            return escaped_fallback
        if identifier not in attached:
            if total_bytes + len(preview) > MAX_EMAIL_EMOJI_BYTES:
                return escaped_fallback
            content_id = f"telegram-emoji-{identifier}@remnawave-minishop"
            attachments.append(EmailInlineImage(content_id, "image/png", preview))
            attached[identifier] = content_id
            total_bytes += len(preview)
        return (
            f'<img src="cid:{attached[identifier]}" '
            f'alt="{html.escape(fallback, quote=True)}" width="20" height="20" '
            'style="display:inline-block;width:20px;height:20px;vertical-align:-4px;'
            'object-fit:contain;border:0;" />'
        )

    return _MARKER_RE.sub(replace_marker, html_body), tuple(attachments)
