"""Neutral behavioral domain-event helpers."""

from __future__ import annotations

import logging
import time
from typing import Literal

from bot.infra import events
from bot.infra.event_payloads import BotStartedPayload, PlansViewedPayload
from bot.infra.redis import get_redis
from config.settings import Settings

logger = logging.getLogger(__name__)

PLANS_VIEWED_THROTTLE_SECONDS = 5 * 60

PlansViewedSource = Literal["webapp", "bot"]
BotStartedSource = Literal["direct", "referral", "promo", "ad", "ticket", "notifications"]

_LOCAL_THROTTLES: dict[str, float] = {}


def reset_behavior_event_throttles() -> None:
    """Clear in-process throttle state for tests."""
    _LOCAL_THROTTLES.clear()


def _normalized_start_param(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text[:256] if text else None


def _event_throttle_key(settings: Settings, event_name: str, user_id: int) -> str:
    try:
        prefix_value = settings.REDIS_KEY_PREFIX
    except AttributeError:
        prefix_value = None
    prefix = str(prefix_value or "remnawave-tg-shop").strip(":")
    return ":".join([prefix, "event-throttle", event_name, str(user_id)])


def _redis_url_configured(settings: Settings) -> bool:
    try:
        return bool(settings.REDIS_URL)
    except AttributeError:
        return False


async def _claim_event_throttle(
    settings: Settings,
    event_name: str,
    user_id: int,
    *,
    ttl_seconds: int,
) -> bool:
    ttl_seconds = max(0, int(ttl_seconds or 0))
    if ttl_seconds <= 0:
        return True

    key = _event_throttle_key(settings, event_name, user_id)
    redis = await get_redis(settings) if _redis_url_configured(settings) else None
    if redis is not None:
        try:
            return bool(await redis.set(key, "1", nx=True, ex=ttl_seconds))
        except Exception as exc:
            logger.warning("Redis event throttle failed for %s: %s", event_name, exc)

    now = time.monotonic()
    expires_at = _LOCAL_THROTTLES.get(key)
    if expires_at is not None and expires_at > now:
        return False
    _LOCAL_THROTTLES[key] = now + ttl_seconds
    if len(_LOCAL_THROTTLES) > 4096:
        expired_keys = [item_key for item_key, expiry in _LOCAL_THROTTLES.items() if expiry <= now]
        for item_key in expired_keys:
            _LOCAL_THROTTLES.pop(item_key, None)
    return True


async def emit_plans_viewed(
    settings: Settings,
    *,
    user_id: int,
    source: PlansViewedSource,
    plans_count: int,
    tariff_key: str | None = None,
    throttle_seconds: int = PLANS_VIEWED_THROTTLE_SECONDS,
) -> bool:
    """Emit the neutral plans-view signal at most once per user per throttle window."""
    if not await _claim_event_throttle(
        settings,
        events.PLANS_VIEWED,
        int(user_id),
        ttl_seconds=throttle_seconds,
    ):
        return False
    normalized_tariff_key = str(tariff_key or "").strip() or None
    await events.emit_model(
        PlansViewedPayload(
            user_id=int(user_id),
            source=source,
            plans_count=max(0, int(plans_count or 0)),
            tariff_key=normalized_tariff_key,
        )
    )
    return True


async def emit_bot_started(
    *,
    user_id: int,
    returning: bool,
    source: BotStartedSource,
    start_param: str | None = None,
) -> None:
    """Emit a typed `/start` signal without affecting the command flow."""
    await events.emit_model(
        BotStartedPayload(
            user_id=int(user_id),
            returning=bool(returning),
            source=source,
            start_param=_normalized_start_param(start_param),
        )
    )
