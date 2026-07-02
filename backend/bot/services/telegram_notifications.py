import logging
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from db.dal import user_dal
from db.models import User

logger = logging.getLogger(__name__)

TELEGRAM_NOTIFICATIONS_UNKNOWN = "unknown"
TELEGRAM_NOTIFICATIONS_ENABLED = "enabled"
TELEGRAM_NOTIFICATIONS_NEEDS_START = "needs_start"
TELEGRAM_NOTIFICATIONS_BLOCKED = "blocked"
TELEGRAM_NOTIFICATION_STATUSES = {
    TELEGRAM_NOTIFICATIONS_UNKNOWN,
    TELEGRAM_NOTIFICATIONS_ENABLED,
    TELEGRAM_NOTIFICATIONS_NEEDS_START,
    TELEGRAM_NOTIFICATIONS_BLOCKED,
}


def normalize_telegram_notification_status(value: str | None) -> str:
    status = str(value or "").strip().lower()
    return status if status in TELEGRAM_NOTIFICATION_STATUSES else TELEGRAM_NOTIFICATIONS_UNKNOWN


def telegram_notifications_enabled(user: User | None) -> bool:
    return (
        bool(getattr(user, "telegram_id", None))
        and normalize_telegram_notification_status(
            getattr(user, "telegram_notifications_status", None)
        )
        == TELEGRAM_NOTIFICATIONS_ENABLED
    )


def telegram_notifications_need_prompt(user: User | None) -> bool:
    status = normalize_telegram_notification_status(
        getattr(user, "telegram_notifications_status", None)
    )
    return bool(getattr(user, "telegram_id", None)) and status in {
        TELEGRAM_NOTIFICATIONS_NEEDS_START,
        TELEGRAM_NOTIFICATIONS_BLOCKED,
    }


def telegram_notifications_start_link(bot_username: str | None) -> str | None:
    username = str(bot_username or "").strip().lstrip("@")
    if not username or username == "your_bot_username":
        return None
    return f"https://t.me/{username}?start=notifications"


def telegram_notification_status_from_error(exc: Exception) -> str | None:
    if isinstance(exc, TelegramForbiddenError):
        return TELEGRAM_NOTIFICATIONS_BLOCKED
    if not isinstance(exc, TelegramBadRequest):
        return None

    message = str(exc).lower()
    if any(
        token in message
        for token in (
            "bot was blocked",
            "user is deactivated",
            "forbidden",
        )
    ):
        return TELEGRAM_NOTIFICATIONS_BLOCKED
    if any(
        token in message
        for token in (
            "chat not found",
            "bot can't initiate conversation",
            "bot can't initiate",
            "user not found",
        )
    ):
        return TELEGRAM_NOTIFICATIONS_NEEDS_START
    return None


async def mark_telegram_notifications_status(
    session: AsyncSession,
    user_id: int,
    status: str,
    *,
    telegram_id: int | None = None,
    checked_at: datetime | None = None,
) -> User | None:
    normalized = normalize_telegram_notification_status(status)
    now = checked_at or datetime.now(UTC)
    update_data: dict[str, Any] = {
        "telegram_notifications_status": normalized,
        "telegram_notifications_checked_at": now,
    }
    if telegram_id:
        update_data["telegram_id"] = int(telegram_id)
    if normalized == TELEGRAM_NOTIFICATIONS_ENABLED:
        update_data["telegram_notifications_enabled_at"] = now
        update_data["telegram_notifications_blocked_at"] = None
    elif normalized == TELEGRAM_NOTIFICATIONS_BLOCKED:
        update_data["telegram_notifications_blocked_at"] = now
    return await user_dal.update_user(session, user_id, update_data)


async def mark_telegram_notifications_enabled_for_telegram_user(
    session: AsyncSession,
    telegram_id: int,
) -> User | None:
    db_user = await user_dal.get_user_by_telegram_id(session, telegram_id)
    if not db_user:
        db_user = await user_dal.get_user_by_id(session, telegram_id)
    if not db_user:
        return None
    return await mark_telegram_notifications_status(
        session,
        int(db_user.user_id),
        TELEGRAM_NOTIFICATIONS_ENABLED,
        telegram_id=telegram_id,
    )


async def probe_telegram_notifications(
    *,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    i18n: JsonI18n | None,
    user: User,
    bot_username: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    telegram_id = getattr(user, "telegram_id", None)
    if not telegram_id:
        return {
            "ok": False,
            "status": TELEGRAM_NOTIFICATIONS_UNKNOWN,
            "start_link": telegram_notifications_start_link(bot_username),
        }

    current_status = normalize_telegram_notification_status(
        getattr(user, "telegram_notifications_status", None)
    )
    if current_status == TELEGRAM_NOTIFICATIONS_ENABLED and not force:
        return {
            "ok": True,
            "status": TELEGRAM_NOTIFICATIONS_ENABLED,
            "start_link": telegram_notifications_start_link(bot_username),
        }

    try:
        await bot.get_chat(int(telegram_id))
    except Exception as exc:
        status = telegram_notification_status_from_error(exc)
        if status:
            await mark_telegram_notifications_status(session, int(user.user_id), status)
            return {
                "ok": False,
                "status": status,
                "start_link": telegram_notifications_start_link(bot_username),
            }
        logger.warning(
            "Telegram notification chat probe failed for user %s / telegram %s: %s",
            user.user_id,
            telegram_id,
            exc,
        )
        await mark_telegram_notifications_status(
            session,
            int(user.user_id),
            TELEGRAM_NOTIFICATIONS_UNKNOWN,
        )
        return {
            "ok": False,
            "status": TELEGRAM_NOTIFICATIONS_UNKNOWN,
            "start_link": telegram_notifications_start_link(bot_username),
        }

    await mark_telegram_notifications_status(
        session,
        int(user.user_id),
        TELEGRAM_NOTIFICATIONS_ENABLED,
        telegram_id=int(telegram_id),
    )
    return {
        "ok": True,
        "status": TELEGRAM_NOTIFICATIONS_ENABLED,
        "start_link": telegram_notifications_start_link(bot_username),
    }
