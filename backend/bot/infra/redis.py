import asyncio
import json
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from config.settings import Settings

redis_asyncio: Any
try:
    import redis.asyncio as redis_asyncio
except ModuleNotFoundError:  # pragma: no cover - local dev environments may not be installed yet
    redis_asyncio = None

logger = logging.getLogger(__name__)

_redis: Any | None = None


def redis_key(settings: Settings, *parts: object) -> str:
    prefix = (settings.REDIS_KEY_PREFIX or "remnawave-tg-shop").strip(":")
    clean = [str(part).strip(":") for part in parts if str(part).strip(":")]
    return ":".join([prefix, *clean])


async def get_redis(settings: Settings) -> Any | None:
    global _redis
    if not settings.REDIS_URL:
        return None
    if redis_asyncio is None:
        logger.warning("REDIS_URL is set but redis package is not installed")
        return None
    if _redis is None:
        _redis = redis_asyncio.Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
            protocol=2,
            # redis-py 8 defaults socket reads to 5 seconds. That races the
            # webhook queue's five-second BLMOVE and turns an empty queue into
            # a TimeoutError instead of the expected None response.
            socket_timeout=None,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_get_json(settings: Settings, key: str) -> Any:
    redis = await get_redis(settings)
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
    except Exception as exc:
        logger.warning("Redis cache get failed for key %s: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in Redis cache key %s", key)
        return None


async def cache_set_json(settings: Settings, key: str, value: Any, ttl_seconds: int) -> None:
    redis = await get_redis(settings)
    if redis is None:
        return
    try:
        await redis.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl_seconds)
    except Exception as exc:
        logger.warning("Redis cache set failed for key %s: %s", key, exc)


async def cache_delete(settings: Settings, *keys: str) -> None:
    redis = await get_redis(settings)
    if redis is None or not keys:
        return
    try:
        await redis.delete(*keys)
    except Exception as exc:
        logger.warning("Redis cache delete failed for %s key(s): %s", len(keys), exc)


async def cache_delete_pattern(settings: Settings, pattern: str) -> int:
    redis = await get_redis(settings)
    if redis is None or not pattern:
        return 0
    deleted = 0
    batch = []
    try:
        async for key in redis.scan_iter(match=pattern, count=100):
            batch.append(key)
            if len(batch) >= 100:
                deleted += int(await redis.delete(*batch))
                batch.clear()
        if batch:
            deleted += int(await redis.delete(*batch))
    except Exception as exc:
        logger.warning("Redis cache pattern delete failed for %s: %s", pattern, exc)
    return deleted


@asynccontextmanager
async def redis_lock(
    settings: Settings,
    name: str,
    *,
    ttl_seconds: int,
) -> AsyncIterator[bool]:
    redis = await get_redis(settings)
    if redis is None:
        yield True
        return

    key = redis_key(settings, "lock", name)
    token = secrets.token_urlsafe(16)
    acquired = bool(await redis.set(key, token, nx=True, ex=ttl_seconds))
    try:
        yield acquired
    finally:
        if acquired:
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            end
            return 0
            """
            try:
                await redis.eval(script, 1, key, token)
            except Exception:
                logger.exception("Failed to release Redis lock %s", key)


async def sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return
