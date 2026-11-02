"""Lazy membership reconciliation with a TTL and coalesced API requests."""

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.required_channel_diagnostics import check_required_channel
from bot.utils.channel_subscription import chat_member_is_present, normalize_required_channel_id
from config.settings import Settings
from db.dal.telegram_state_dal import record_channel_membership
from db.models import User

logger = logging.getLogger(__name__)


def membership_is_fresh(user: User, channel_id: int, ttl: int) -> bool:
    checked = user.channel_subscription_checked_at
    if checked is None or user.channel_subscription_verified_for != channel_id:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    return 0 <= (datetime.now(UTC) - checked).total_seconds() < ttl


@dataclass(frozen=True)
class _Observation:
    member: bool | None
    observed_at: datetime


_active: OrderedDict[tuple[int, int], float] = OrderedDict()

_pending: dict[tuple[Bot, int, int], asyncio.Task[_Observation]] = {}
_recent: OrderedDict[tuple[Bot, int, int], tuple[float, _Observation]] = OrderedDict()


async def _observe(bot: Bot, settings: Settings, channel_id: int, telegram_id: int) -> _Observation:
    now = datetime.now(UTC)
    diagnostic = await check_required_channel(bot, settings)
    if diagnostic.status != "available":
        return _Observation(None, now)
    try:
        logger.info("metric telegram_get_chat_member_total=1 purpose=membership")
        member = await bot.get_chat_member(channel_id, telegram_id)
        return _Observation(chat_member_is_present(member), now)
    except TelegramAPIError:
        # No API error, including 'user not found', proves non-membership.
        logger.warning("metric telegram_membership_check_errors_total=1")
        return _Observation(None, now)


async def _coalesced_observation(
    bot: Bot, settings: Settings, channel_id: int, telegram_id: int
) -> _Observation:
    key = (bot, channel_id, telegram_id)
    cached = _recent.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    task = _pending.get(key)
    if task is None:

        async def run() -> _Observation:
            try:
                result = await _observe(bot, settings, channel_id, telegram_id)
                _recent[key] = (time.monotonic() + 5, result)
                _recent.move_to_end(key)
                if len(_recent) > 4096:
                    _recent.popitem(last=False)
                return result
            finally:
                _pending.pop(key, None)

        task = asyncio.create_task(run())
        _pending[key] = task
    return await asyncio.shield(task)


async def check_membership(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    user: User,
    *,
    force: bool = False,
) -> bool | None:
    channel_id = normalize_required_channel_id(settings.REQUIRED_CHANNEL_ID)
    if channel_id is None:
        return True
    if (await check_required_channel(bot, settings)).status != "available":
        return None
    active_key = (bot.id, int(user.user_id))
    if _active.get(active_key, 0) <= time.monotonic():
        logger.info("metric telegram_membership_active_users_total=1")
        _active[active_key] = time.monotonic() + 900
        _active.move_to_end(active_key)
        if len(_active) > 10000:
            _active.popitem(last=False)
    ttl = settings.REQUIRED_CHANNEL_VERIFICATION_TTL_SECONDS
    if not force and membership_is_fresh(user, channel_id, ttl):
        return bool(user.channel_subscription_verified)
    telegram_id = user.telegram_id
    if telegram_id is None:
        return None
    observation = await _coalesced_observation(bot, settings, channel_id, int(telegram_id))
    if channel_id != normalize_required_channel_id(settings.REQUIRED_CHANNEL_ID):
        return None
    if observation.member is None:
        return None
    updated = await record_channel_membership(
        session,
        int(user.user_id),
        int(telegram_id),
        channel_id,
        observation.member,
        observation.observed_at,
    )
    if updated is not None:
        return observation.member
    # A newer event may have committed while the request was in flight.
    await session.refresh(user)
    if user.telegram_id != telegram_id or not membership_is_fresh(user, channel_id, ttl):
        return None
    return bool(user.channel_subscription_verified)
