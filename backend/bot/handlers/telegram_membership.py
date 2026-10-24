"""Telegram service events never register users or grant shop access."""

import logging
from datetime import UTC, datetime

from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated, Update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.required_channel_diagnostics import check_required_channel
from bot.services.telegram_notifications import mark_telegram_notifications_status
from bot.utils.channel_subscription import chat_member_is_present, normalize_required_channel_id
from config.settings import Settings
from db.dal import user_dal
from db.dal.telegram_state_dal import record_channel_membership

logger = logging.getLogger(__name__)


def build_telegram_membership_router() -> Router:
    router = Router(name="telegram_membership")
    router.my_chat_member.register(bot_membership_updated)
    router.chat_member.register(channel_membership_updated)
    return router


def _metric(event: ChatMemberUpdated, kind: str, applied: bool) -> None:
    logger.info(
        "metric telegram_service_updates_total=1 kind=%s result=%s lag_seconds=%.3f",
        kind,
        "applied" if applied else "ignored",
        max(0, (datetime.now(UTC) - event.date).total_seconds()),
    )


async def bot_membership_updated(
    event: ChatMemberUpdated,
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
    event_update: Update,
    i18n_instance: JsonI18n | None = None,
) -> None:
    if event.new_chat_member.user.id != bot.id:
        _metric(event, "bot", False)
        return
    if event.chat.type != "private":
        if event.chat.id == normalize_required_channel_id(settings.REQUIRED_CHANNEL_ID):
            await check_required_channel(
                bot,
                settings,
                force=True,
                i18n=i18n_instance,
                session=session,
                event_order=(event.date, event_update.update_id),
            )
        else:
            _metric(event, "channel_bot", False)
        return
    old, new = event.old_chat_member.status, event.new_chat_member.status
    status = (
        "blocked" if new == "kicked" else "enabled" if old == "kicked" and new == "member" else None
    )
    user = await user_dal.get_user_by_telegram_id(session, event.chat.id) if status else None
    if user is None or status is None:
        _metric(event, "bot", False)
        return
    try:
        updated = await mark_telegram_notifications_status(
            session,
            int(user.user_id),
            status,
            telegram_id=event.chat.id,
            checked_at=event.date,
            update_id=event_update.update_id,
        )
    except Exception:
        logger.exception("metric telegram_service_write_errors_total=1 kind=bot")
        raise
    _metric(event, "bot", updated is not None)


async def channel_membership_updated(
    event: ChatMemberUpdated,
    settings: Settings,
    session: AsyncSession,
    event_update: Update,
) -> None:
    if event.chat.id != normalize_required_channel_id(settings.REQUIRED_CHANNEL_ID):
        _metric(event, "member", False)
        return
    telegram_id = event.new_chat_member.user.id
    user = await user_dal.get_user_by_telegram_id(session, telegram_id)
    if user is None:
        _metric(event, "member", False)
        return
    try:
        updated = await record_channel_membership(
            session,
            int(user.user_id),
            telegram_id,
            event.chat.id,
            chat_member_is_present(event.new_chat_member),
            event.date,
            update_id=event_update.update_id,
        )
    except Exception:
        logger.exception("metric telegram_service_write_errors_total=1 kind=member")
        raise
    _metric(event, "member", updated is not None)
