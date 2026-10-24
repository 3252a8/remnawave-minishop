"""Bounded live diagnostics for the configured Telegram channel."""

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.utils.channel_subscription import normalize_required_channel_id
from config.settings import Settings
from db.auth_models import AccountRole
from db.models import User

logger = logging.getLogger(__name__)
type ChannelStatus = Literal["disabled", "available", "missing_rights", "unavailable"]


@dataclass
class ChannelDiagnostics:
    channel_id: int | None
    status: ChannelStatus
    checked_at: datetime | None

    def payload(self) -> dict[str, object]:
        return {
            "channel_id": self.channel_id,
            "status": self.status,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }


@dataclass
class _State:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    result: ChannelDiagnostics | None = None
    expires: float = 0
    notified_status: ChannelStatus | None = None
    notified_at: float = 0
    event_order: tuple[datetime, int] | None = None


_states: OrderedDict[tuple[int, int], _State] = OrderedDict()


async def check_required_channel(
    bot: Bot | None,
    settings: Settings,
    *,
    force: bool = False,
    i18n: JsonI18n | None = None,
    session: AsyncSession | None = None,
    event_order: tuple[datetime, int] | None = None,
) -> ChannelDiagnostics:
    channel_id = normalize_required_channel_id(settings.REQUIRED_CHANNEL_ID)
    if not channel_id:
        return ChannelDiagnostics(None, "disabled", None)
    if bot is None:
        return ChannelDiagnostics(channel_id, "unavailable", datetime.now(UTC))
    key = (bot.id, channel_id)
    state = _states.setdefault(key, _State())
    _states.move_to_end(key)
    if len(_states) > 64:
        _states.popitem(last=False)
    async with state.lock:
        if event_order and state.event_order and event_order <= state.event_order and state.result:
            return state.result
        if not force and state.result and state.expires > time.monotonic():
            return state.result
        observed_at = datetime.now(UTC)
        status: ChannelStatus = "unavailable"
        try:
            member = await bot.get_chat_member(channel_id, bot.id)
            status = (
                "available" if member.status in {"creator", "administrator"} else "missing_rights"
            )
        except TelegramAPIError:
            logger.warning("metric telegram_channel_diagnostic_errors_total=1")
        state.result = ChannelDiagnostics(channel_id, status, observed_at)
        state.expires = time.monotonic() + 60
        if event_order:
            state.event_order = event_order
        if session is not None:
            known, blocked = (
                await session.execute(
                    select(
                        func.count(User.user_id),
                        func.count(User.user_id).filter(
                            User.telegram_notifications_status == "blocked"
                        ),
                    ).where(
                        User.telegram_id.is_not(None),
                        User.telegram_notifications_status != "unknown",
                    )
                )
            ).one()
            logger.info(
                "metric telegram_known_blocked_fraction=%.6f known_users=%s",
                blocked / known if known else 0,
                known,
            )
        # Notify only on a changed state, at most once per five minutes.
        if (
            i18n is not None
            and session is not None
            and status != state.notified_status
            and (not state.notified_at or time.monotonic() - state.notified_at >= 300)
            and (state.notified_status is not None or status != "available")
        ):
            text = i18n.gettext(
                settings.DEFAULT_LANGUAGE,
                "required_channel_status_changed",
                channel_id=channel_id,
                status=i18n.gettext(settings.DEFAULT_LANGUAGE, f"required_channel_status_{status}"),
            )
            state.notified_at = time.monotonic()
            state.notified_status = status
            recipients = await session.scalars(
                select(User.telegram_id)
                .join(AccountRole, AccountRole.user_id == User.user_id)
                .where(
                    AccountRole.role.in_(("owner", "admin")),
                    AccountRole.revoked_at.is_(None),
                    User.telegram_id.is_not(None),
                    User.is_banned.is_(False),
                )
                .distinct()
            )
            for admin_id in recipients:
                try:
                    await bot.send_message(admin_id, text)
                except TelegramAPIError:
                    logger.warning("Failed to deliver required channel diagnostic notification")
        elif state.notified_status is None and status == "available":
            state.notified_status = status
        return state.result
