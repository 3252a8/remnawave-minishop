import asyncio
import time

import pytest

from bot.utils.ttl_cache import AsyncTTLCache


def test_one_cancelled_reader_does_not_cancel_other_reader() -> None:
    async def run() -> None:
        cache = AsyncTTLCache(60)
        started, release = asyncio.Event(), asyncio.Event()

        async def load() -> int:
            started.set()
            await release.wait()
            return 42

        first = asyncio.create_task(cache.get_or_load("user", load))
        await started.wait()
        second = asyncio.create_task(cache.get_or_load("user", load))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert await second == 42
        assert cache.get_fresh("user") == 42

    asyncio.run(run())


def test_last_cancelled_reader_closes_loader_resources() -> None:
    async def run() -> None:
        cache = AsyncTTLCache(60)
        started, closed = asyncio.Event(), asyncio.Event()

        async def load() -> None:
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                closed.set()

        reader = asyncio.create_task(cache.get_or_load("user", load))
        await started.wait()
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
        assert closed.is_set()
        assert not cache._inflight
        assert not cache._waiters

    asyncio.run(run())


def test_invalidation_fences_a_previous_loader() -> None:
    async def run() -> None:
        cache = AsyncTTLCache(60)
        started, release = asyncio.Event(), asyncio.Event()

        async def old_load() -> int:
            started.set()
            await release.wait()
            return 10

        async def fresh_load() -> int:
            return 20

        old = asyncio.create_task(cache.get_or_load("balance", old_load))
        await started.wait()
        cache.invalidate("balance")
        assert await cache.get_or_load("balance", fresh_load) == 20
        release.set()
        assert await old == 10
        assert cache.get_fresh("balance") == 20

    asyncio.run(run())


def test_cache_evicts_and_limits_stale_lifetime() -> None:
    async def run() -> None:
        cache = AsyncTTLCache(1, max_entries=3)

        async def load() -> int:
            return 42

        for key in range(10):
            await cache.get_or_load(str(key), load)
        assert len(cache._data) == 3
        assert cache.get_fresh("0") is None
        cache._data["9"] = (time.monotonic() - 31, 42)
        assert cache.get_stale("9") is None

    asyncio.run(run())


def test_loader_timeout_releases_singleflight() -> None:
    async def run() -> None:
        cache = AsyncTTLCache(60, load_timeout=0.01)

        async def load() -> None:
            await asyncio.Event().wait()

        with pytest.raises(TimeoutError):
            await cache.get_or_load("user", load)
        assert not cache._inflight
        assert not cache._waiters

    asyncio.run(run())
