import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.utils.text_decorations import html_decoration as hd

from bot.utils.message_queue import get_queue_manager
from config.settings import Settings

logger = logging.getLogger(__name__)

_configured_settings: Settings | None = None
_configured_bot: Bot | None = None


def configure_message_log_notifier(settings: Settings, bot: Bot | None = None) -> None:
    global _configured_settings, _configured_bot
    _configured_settings = settings
    _configured_bot = bot


def message_log_chat_enabled(settings: Settings) -> bool:
    log_level = str(settings.LOG_LEVEL or "").strip().upper()
    return bool(settings.LOG_CHAT_ID and log_level == "DEBUG")


def _compact(value: object, max_length: int) -> str:
    text = value.isoformat() if isinstance(value, datetime) else " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}..."


def _code(value: object, max_length: int = 240) -> str:
    return f"<code>{hd.quote(_compact(value, max_length))}</code>"


def _user_line(log_payload: Mapping[str, object]) -> str:
    parts: list[str] = []
    user_id = log_payload.get("user_id")
    target_user_id = log_payload.get("target_user_id")
    username = _compact(log_payload.get("telegram_username"), 64)
    first_name = _compact(log_payload.get("telegram_first_name"), 64)

    if user_id:
        parts.append(f"id={_code(user_id, 32)}")
    if target_user_id and target_user_id != user_id:
        parts.append(f"target={_code(target_user_id, 32)}")
    if username:
        display_username = username if username.startswith("@") else f"@{username}"
        parts.append(_code(display_username, 80))
    if first_name:
        parts.append(_code(first_name, 80))

    return " ".join(parts)


def format_message_log_notification(log_payload: Mapping[str, object]) -> str:
    """Build a compact Telegram message from a DB message_log payload.

    raw_update_preview is intentionally omitted: it may contain noisy or sensitive
    Telegram payload fragments and is still available in the admin DB logs.
    """
    event_type = log_payload.get("event_type") or "unknown"
    content = _compact(log_payload.get("content"), 900)
    timestamp = log_payload.get("timestamp")

    lines = [
        "<b>User action log</b>",
        f"<b>Event:</b> {_code(event_type, 160)}",
    ]
    user_line = _user_line(log_payload)
    if user_line:
        lines.append(f"<b>User:</b> {user_line}")
    if content and content != "N/A":
        lines.append(f"<b>Content:</b> {_code(content, 900)}")
    if log_payload.get("is_admin_event"):
        lines.append("<b>Admin:</b> yes")
    if timestamp:
        lines.append(f"<b>Time:</b> {_code(timestamp, 80)}")
    return "\n".join(lines)


async def notify_message_log(
    log_payload: Mapping[str, object],
    *,
    settings: Settings | None = None,
    bot: Bot | None = None,
) -> None:
    resolved_settings = settings or _configured_settings
    if resolved_settings is None or not message_log_chat_enabled(resolved_settings):
        return

    chat_id = resolved_settings.LOG_CHAT_ID
    if chat_id is None:
        return

    message = format_message_log_notification(log_payload)
    kwargs: dict[str, Any] = {
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if resolved_settings.LOG_THREAD_ID:
        kwargs["message_thread_id"] = resolved_settings.LOG_THREAD_ID

    queue_manager = get_queue_manager()
    try:
        if queue_manager:
            await queue_manager.send_message(chat_id, **kwargs)
            return

        resolved_bot = bot or _configured_bot
        if resolved_bot is None:
            logger.debug("Skipping message log notification: no queue manager or bot configured")
            return
        await resolved_bot.send_message(chat_id=chat_id, **kwargs)
    except Exception:
        logger.exception("Failed to send message log notification to chat %s", chat_id)
