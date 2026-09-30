"""Shared resource quotas: atomic Redis windows or bounded single-process storage."""

import asyncio
import hashlib
import logging
import math
import time
from collections import deque
from collections.abc import Sequence

from aiohttp import web

from bot.app.web.context import (
    get_settings,
    get_webapp_rate_limit_buckets,
    get_webapp_rate_limit_lock,
)
from bot.infra.redis import get_redis, redis_key
from bot.utils.request_security import request_client_ip

from .response_helpers import json_response

logger = logging.getLogger(__name__)
_MAX_BUCKETS = 10000
_COUNTERS = """
local retry = 0
for i, key in ipairs(KEYS) do
  local count = redis.call('INCR', key)
  local ttl = redis.call('TTL', key)
  if ttl < 0 then
    redis.call('EXPIRE', key, ARGV[1])
    ttl = tonumber(ARGV[1])
  end
  if count > tonumber(ARGV[i + 1]) then retry = math.max(retry, ttl, 1) end
end
return retry
"""


def client_ip(request: web.Request) -> str:
    settings = get_settings(request)
    return (
        request_client_ip(request, trusted_proxies=settings.trusted_proxies)
        or request.remote
        or "unknown"
    )


def rate_error(retry_after: int, *, status: int = 429) -> web.Response:
    return json_response(
        {
            "ok": False,
            "error": "rate_limited" if status == 429 else "limiter_unavailable",
            "retry_after": retry_after,
        },
        status=status,
        headers={"Retry-After": str(retry_after)},
    )


async def check_request_limits(
    request: web.Request,
    limits: Sequence[tuple[str, int]],
    *,
    window_seconds: int,
) -> web.Response | None:
    settings = get_settings(request)
    window = max(1, int(window_seconds))
    normalized = [(f"{window}:{key}", max(1, int(maximum))) for key, maximum in limits]
    try:
        async with asyncio.timeout(0.5):
            redis = await get_redis(settings)
            if redis is not None:
                keys = [
                    redis_key(
                        settings,
                        "rate-limit",
                        "resources",
                        hashlib.sha256(key.encode()).hexdigest(),
                    )
                    for key, _ in normalized
                ]
                retry = int(
                    await redis.eval(
                        _COUNTERS, len(keys), *keys, window, *(maximum for _, maximum in normalized)
                    )
                )
                return rate_error(retry) if retry else None
    except Exception:
        logger.warning("Shared request limiter is unavailable", exc_info=True)
        if settings.REDIS_URL:
            return rate_error(window, status=503)
    if settings.REDIS_URL:
        return rate_error(window, status=503)

    buckets = get_webapp_rate_limit_buckets(request)
    lock = get_webapp_rate_limit_lock(request)
    now = time.monotonic()
    async with lock:
        # Expired keys are collected globally; a full store rejects new identities.
        for key, bucket in list(buckets.items()):
            ttl = int(key.partition(":")[0]) if key.partition(":")[0].isdigit() else window
            if not bucket or now - bucket[-1] >= ttl:
                buckets.pop(key, None)
        missing = sum(key not in buckets for key, _ in normalized)
        if len(buckets) + missing > _MAX_BUCKETS:
            return rate_error(window)
        retry = 0
        for key, maximum in normalized:
            bucket = buckets.setdefault(key, deque())
            while bucket and now - bucket[0] >= window:
                bucket.popleft()
            if len(bucket) >= maximum:
                retry = max(retry, max(1, math.ceil(window - (now - bucket[0]))))
        if retry:
            return rate_error(retry)
        for key, _ in normalized:
            buckets[key].append(now)
    return None


async def enforce_action_limit(
    request: web.Request, *, user_id: int, action: str
) -> web.Response | None:
    settings = get_settings(request)
    maximum = settings.WEBAPP_RATE_LIMIT_MAX_REQUESTS
    return await check_request_limits(
        request,
        (
            (f"action:{action}:user:{int(user_id)}", maximum),
            (f"action:{action}:ip:{client_ip(request)}", maximum * 4),
        ),
        window_seconds=settings.WEBAPP_RATE_LIMIT_TTL_SECONDS,
    )
