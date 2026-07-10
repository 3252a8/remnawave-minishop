"""Helpers for shortcode personalization in Telegram admin handlers."""

from __future__ import annotations

import logging

from aiogram import Bot, types
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.broadcast_personalization import (
    BroadcastUserContext,
    load_broadcast_contexts,
    render_broadcast_text,
)
from bot.services.panel_api_service import PanelApiService
from bot.utils import MessageContent
from config.settings import Settings

logger = logging.getLogger(__name__)


def message_content_html_text(message: types.Message, content: MessageContent) -> str:
    """Return aiogram's entity-preserving HTML for text or media captions."""
    if content.content_type == "text":
        return str(getattr(message, "html_text", None) or content.text or "")
    return str(
        getattr(message, "html_caption", None)
        or getattr(message, "html_text", None)
        or content.text
        or ""
    )


def localized_shortcode_error(
    i18n: JsonI18n,
    lang: str,
    key: str,
    detail: str,
) -> str:
    base = i18n.gettext(lang, key)
    return f"{base}: {detail}" if detail else base


async def bot_username_for_shortcodes(bot: Bot, needed: set[str]) -> str:
    if "referral_bot_link" not in needed:
        return ""
    try:
        me = await bot.get_me()
    except Exception as exc:
        logger.warning("Failed to resolve bot username for broadcast shortcodes: %s", exc)
        return ""
    return str(getattr(me, "username", "") or "")


async def load_admin_broadcast_contexts(
    session: AsyncSession,
    settings: Settings,
    user_ids: list[int],
    needed: set[str],
) -> dict[int, BroadcastUserContext]:
    if not needed:
        return {}
    if "config_link" in needed:
        async with PanelApiService(settings) as panel_service:
            return await load_broadcast_contexts(
                session,
                settings,
                user_ids,
                needed,
                panel_service,
            )
    return await load_broadcast_contexts(session, settings, user_ids, needed, None)


def render_personalized_admin_broadcast_text(
    template: str,
    contexts: dict[int, BroadcastUserContext],
    user_id: int,
    *,
    fallback_lang: str,
    i18n: JsonI18n,
    settings: Settings,
    bot_username: str,
) -> str:
    ctx = contexts.get(user_id)
    lang = (ctx.language_code if ctx else None) or fallback_lang or settings.DEFAULT_LANGUAGE
    return render_broadcast_text(
        template,
        ctx,
        lang=lang,
        i18n=i18n,
        settings=settings,
        bot_username=bot_username,
        escape=True,
    )


__all__ = [
    "bot_username_for_shortcodes",
    "load_admin_broadcast_contexts",
    "localized_shortcode_error",
    "message_content_html_text",
    "render_personalized_admin_broadcast_text",
]
