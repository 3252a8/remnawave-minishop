"""Cross-process cache fencing and renewable worker ownership on real Redis."""

import asyncio
import os
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from redis.asyncio import Redis

from bot.infra import redis as redis_module
from bot.infra.versioned_cache import invalidate_versioned_cache, read_versioned_cache

REDIS_URL = os.environ.get("CORE_PERFORMANCE_TEST_REDIS_URL", "")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="Disposable Redis URL is required")


def test_cache_generation_prevents_stale_cross_process_store() -> None:
    async def run() -> None:
        client = Redis.from_url(REDIS_URL, decode_responses=True)
        settings: Any = SimpleNamespace(REDIS_KEY_PREFIX="perf-test-" + uuid.uuid4().hex)
        with patch("bot.infra.versioned_cache.get_redis", AsyncMock(return_value=client)):
            old = await read_versioned_cache(settings, "profile", "1")
            assert old is not None
            await invalidate_versioned_cache(settings, "profile", "1")
            new = await read_versioned_cache(settings, "profile", "1")
            assert new is not None
            await new.store({"balance": 200}, 2)
            await old.store({"balance": 100}, 2)
            current = await read_versioned_cache(settings, "profile", "1")
            assert current is not None and current.value == {"balance": 200}
            await invalidate_versioned_cache(settings, "profile")
            current = await read_versioned_cache(settings, "profile", "1")
            assert current is not None and current.value is None
            await client.delete(*old.keys)
        await client.aclose()

    asyncio.run(run())


def test_lease_renews_and_lost_owner_cannot_release_a_new_lease() -> None:
    async def run() -> None:
        client = Redis.from_url(REDIS_URL, decode_responses=True)
        settings: Any = SimpleNamespace(REDIS_KEY_PREFIX="perf-test-" + uuid.uuid4().hex)
        key = redis_module.redis_key(settings, "lock", "worker")
        with patch.object(redis_module, "get_redis", AsyncMock(return_value=client)):
            async with redis_module.redis_lock(settings, "worker", ttl_seconds=1) as acquired:
                assert acquired
                await asyncio.sleep(1.2)
                async with redis_module.redis_lock(settings, "worker", ttl_seconds=1) as other:
                    assert not other
            assert await client.get(key) is None
            with pytest.raises(RuntimeError, match="lease lost"):
                async with redis_module.redis_lock(settings, "worker", ttl_seconds=1):
                    await client.set(key, "new-owner", ex=3)
                    await asyncio.sleep(1)
            assert await client.get(key) == "new-owner"
            await client.delete(key)
        await client.aclose()

    asyncio.run(run())
