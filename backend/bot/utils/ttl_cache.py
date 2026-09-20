import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from bot.infra.performance import record_cache_result


class AsyncTTLCache:
    """In-memory async-safe TTL cache with single-flight loader.

    Concurrent get_or_load() calls for the same key share one loader execution.
    """

    def __init__(
        self,
        ttl_seconds: float,
        settings: Any = None,
        namespace: str | None = None,
        *,
        max_entries: int = 1024,
        load_timeout: float = 30.0,
        shared_versioned: bool = False,
    ):
        self.ttl_seconds = ttl_seconds
        self.settings = settings
        self.namespace = namespace
        self.max_entries = max(1, max_entries)
        self.load_timeout = max(0.01, load_timeout)
        self.shared_versioned = shared_versioned
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._inflight: dict[str, asyncio.Task[Any]] = {}
        self._waiters: dict[asyncio.Task[Any], int] = {}
        self._load_slots = asyncio.Semaphore(32)

    def _remember(self, key: str, value: Any) -> None:
        self._data[key] = (time.monotonic() + self.ttl_seconds, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def _is_fresh(self, expires_at: float) -> bool:
        return time.monotonic() < expires_at

    def get_fresh(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if not self._is_fresh(expires_at):
            if time.monotonic() - expires_at > min(300.0, max(30.0, self.ttl_seconds)):
                self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def get_stale(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() - expires_at > min(300.0, max(30.0, self.ttl_seconds)):
            self._data.pop(key, None)
            return None
        if not self._is_cacheable(value):
            return None
        return value

    @staticmethod
    def _is_cacheable(value: Any) -> bool:
        if value is None:
            return False
        return not (isinstance(value, dict) and value.get("error"))

    async def get_or_load(self, key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        if (
            self.shared_versioned
            and self.settings is not None
            and self.namespace
            and getattr(self.settings, "REDIS_URL", None)
        ):
            from bot.infra.versioned_cache import read_versioned_cache

            entry = await read_versioned_cache(self.settings, self.namespace, key)
            if entry is not None and entry.value is not None:
                record_cache_result("shared_hit")
                return entry.value

            async def versioned_loader() -> Any:
                value = await loader()
                if entry is not None and self._is_cacheable(value):
                    await entry.store(value, max(1, int(self.ttl_seconds)))
                return value

            # Every request consults Redis, so a worker invalidation also reaches
            # another backend's L1. Generations prevent joining an obsolete flight.
            flight_key = f"{key}:{entry.version}" if entry is not None else key
            return await self._singleflight(flight_key, versioned_loader, remember=False)
        return await self._singleflight(key, loader, remember=True)

    async def _singleflight(
        self, key: str, loader: Callable[[], Awaitable[Any]], *, remember: bool
    ) -> Any:
        cached = self.get_fresh(key) if remember else None
        if cached is not None:
            record_cache_result("local_hit")
            return cached

        task = self._inflight.get(key)
        record_cache_result("shared_load" if task is not None else "miss")
        if task is None:
            if len(self._inflight) >= self.max_entries:
                async with asyncio.timeout(self.load_timeout), self._load_slots:
                    return await loader()
            task = asyncio.create_task(self._bounded_load(key, loader, remember=remember))
            self._inflight[key] = task
        self._waiters[task] = self._waiters.get(task, 0) + 1
        try:
            return await asyncio.shield(task)
        finally:
            remaining = self._waiters[task] - 1
            if remaining:
                self._waiters[task] = remaining
            else:
                self._waiters.pop(task, None)
                if self._inflight.get(key) is task:
                    self._inflight.pop(key, None)
                if not task.done():
                    task.cancel()
                    # Finish cancellation before request-owned resources disappear.
                    await asyncio.gather(task, return_exceptions=True)

    async def _bounded_load(
        self, key: str, loader: Callable[[], Awaitable[Any]], *, remember: bool
    ) -> Any:
        async with asyncio.timeout(self.load_timeout), self._load_slots:
            return await self._load_and_store(key, loader) if remember else await loader()

    def _owns_flight(self, key: str) -> bool:
        return self._inflight.get(key) is asyncio.current_task()

    async def _load_and_store(self, key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        cache_key = None
        if self.settings is not None and self.namespace:
            try:
                from bot.infra.redis import cache_get_json, redis_key

                cache_key = redis_key(self.settings, "cache", self.namespace, key)
                cached = await cache_get_json(self.settings, cache_key)
                if cached is not None:
                    if self._is_cacheable(cached) and self._owns_flight(key):
                        self._remember(key, cached)
                    return cached
            except Exception:
                cache_key = None

        value = await loader()
        if self._is_cacheable(value) and self._owns_flight(key):
            self._remember(key, value)
            if cache_key is not None:
                try:
                    from bot.infra.redis import cache_set_json

                    await cache_set_json(
                        self.settings,
                        cache_key,
                        value,
                        max(1, int(self.ttl_seconds)),
                    )
                except Exception:
                    pass
        return value

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._data.clear()
            self._inflight.clear()
            return
        self._data.pop(key, None)
        self._inflight.pop(key, None)

    async def invalidate_remote(self, key: str | None = None) -> None:
        self.invalidate(key)
        if self.settings is None or not self.namespace:
            return
        if self.shared_versioned:
            from bot.infra.versioned_cache import invalidate_versioned_cache

            await invalidate_versioned_cache(self.settings, self.namespace, key)
            return
        try:
            from bot.infra.redis import cache_delete, cache_delete_pattern, redis_key

            if key is None:
                pattern = redis_key(self.settings, "cache", self.namespace, "*")
                await cache_delete_pattern(self.settings, pattern)
                return
            await cache_delete(
                self.settings, redis_key(self.settings, "cache", self.namespace, key)
            )
        except Exception:
            return
