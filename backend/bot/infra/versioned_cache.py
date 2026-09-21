"""Redis cache generations fence loads that began before an invalidation."""

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass
from typing import Any

from bot.infra.redis import get_redis, redis_key
from config.settings import Settings

logger = logging.getLogger(__name__)
_TIMEOUT_SECONDS = 0.5


def _keys(settings: Settings, namespace: str, key: str) -> tuple[str, str, str]:
    return (
        redis_key(settings, "cache-epoch", namespace),
        redis_key(settings, "cache-version", namespace, key),
        redis_key(settings, "cache-v2", namespace, key),
    )


@dataclass(frozen=True)
class VersionedCacheEntry:
    redis: Any
    keys: tuple[str, str, str]
    version: tuple[str, str]
    value: Any

    async def store(self, value: Any, ttl: int) -> None:
        script = """
        if (redis.call('GET', KEYS[1]) or '') ~= ARGV[1]
          or (redis.call('GET', KEYS[2]) or '') ~= ARGV[2] then return 0 end
        redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
        return 1
        """
        try:
            async with asyncio.timeout(_TIMEOUT_SECONDS):
                await self.redis.eval(
                    script,
                    3,
                    *self.keys,
                    *self.version,
                    json.dumps(
                        {"version": self.version, "value": value},
                        ensure_ascii=False,
                        default=str,
                    ),
                    ttl,
                )
        except Exception:
            logger.debug("Versioned cache store unavailable")


async def read_versioned_cache(
    settings: Settings, namespace: str, key: str
) -> VersionedCacheEntry | None:
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            redis = await get_redis(settings)
            if redis is None:
                return None
            keys = _keys(settings, namespace, key)
            epoch, generation, raw = await redis.mget(keys)
            version = (epoch or "", generation or "")
            payload = json.loads(raw) if raw is not None else None
            value = (
                payload.get("value")
                if isinstance(payload, dict) and payload.get("version") == list(version)
                else None
            )
            return VersionedCacheEntry(
                redis,
                keys,
                version,
                value,
            )
    except Exception:
        logger.debug("Versioned cache read unavailable")
        return None


async def invalidate_versioned_cache(
    settings: Settings, namespace: str, key: str | None = None
) -> None:
    try:
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            redis = await get_redis(settings)
            if redis is None:
                return
            epoch, generation, value = _keys(settings, namespace, key or "")
            token = secrets.token_hex(16)
            if key is None:
                # Readers reject the old epoch immediately. Values expire by TTL;
                # a global invalidation does not scan all users or race new writes.
                await redis.set(epoch, token)
            else:
                await redis.eval(
                    "redis.call('SET', KEYS[1], ARGV[1], 'EX', 3600); "
                    "return redis.call('DEL', KEYS[2])",
                    2,
                    generation,
                    value,
                    token,
                )
    except Exception:
        logger.warning("Versioned cache invalidation unavailable for namespace %s", namespace)
