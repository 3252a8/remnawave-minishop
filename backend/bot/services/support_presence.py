from __future__ import annotations

import logging
import time
from typing import Literal

from bot.infra.redis import get_redis, redis_key
from config.settings import Settings

logger = logging.getLogger(__name__)

SUPPORT_TYPING_TTL_SECONDS = 8
SupportTypingRole = Literal["user", "admin"]

_local_typing_expiry: dict[str, float] = {}


def _presence_key(settings: Settings, ticket_id: int, role: SupportTypingRole) -> str:
    return redis_key(settings, "support", "typing", ticket_id, role)


def _prune_local_presence(now: float) -> None:
    expired = [key for key, expires_at in _local_typing_expiry.items() if expires_at <= now]
    for key in expired:
        _local_typing_expiry.pop(key, None)


def _set_local_presence(key: str, typing: bool) -> None:
    now = time.monotonic()
    _prune_local_presence(now)
    if typing:
        _local_typing_expiry[key] = now + SUPPORT_TYPING_TTL_SECONDS
    else:
        _local_typing_expiry.pop(key, None)


def _get_local_presence(key: str) -> bool:
    now = time.monotonic()
    _prune_local_presence(now)
    return _local_typing_expiry.get(key, 0) > now


async def set_support_typing(
    settings: Settings,
    ticket_id: int,
    role: SupportTypingRole,
    *,
    typing: bool,
) -> None:
    key = _presence_key(settings, ticket_id, role)
    redis = await get_redis(settings)
    if redis is None:
        _set_local_presence(key, typing)
        return
    try:
        if typing:
            await redis.set(key, "1", ex=SUPPORT_TYPING_TTL_SECONDS)
        else:
            await redis.delete(key)
        _set_local_presence(key, typing)
    except Exception:
        logger.debug("Support typing presence Redis write failed", exc_info=True)
        _set_local_presence(key, typing)


async def is_support_typing(
    settings: Settings,
    ticket_id: int,
    role: SupportTypingRole,
) -> bool:
    key = _presence_key(settings, ticket_id, role)
    redis = await get_redis(settings)
    if redis is None:
        return _get_local_presence(key)
    try:
        return bool(await redis.get(key))
    except Exception:
        logger.debug("Support typing presence Redis read failed", exc_info=True)
        return _get_local_presence(key)
