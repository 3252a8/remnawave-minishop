import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple


class AsyncTTLCache:
    """In-memory async-safe TTL cache with single-flight loader.

    Concurrent get_or_load() calls for the same key share one loader execution.
    """

    def __init__(self, ttl_seconds: float, settings: Any = None, namespace: Optional[str] = None):
        self.ttl_seconds = ttl_seconds
        self.settings = settings
        self.namespace = namespace
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._inflight: Dict[str, asyncio.Task] = {}

    def _is_fresh(self, expires_at: float) -> bool:
        return time.monotonic() < expires_at

    def get_fresh(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if not self._is_fresh(expires_at):
            return None
        return value

    def get_stale(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            return None
        _, value = entry
        if not self._is_cacheable(value):
            return None
        return value

    @staticmethod
    def _is_cacheable(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, dict) and value.get("error"):
            return False
        return True

    async def get_or_load(self, key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        cached = self.get_fresh(key)
        if cached is not None:
            return cached

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.get_fresh(key)
            if cached is not None:
                return cached
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._load_and_store(key, loader))
                self._inflight[key] = task

                def _forget_inflight(done_task: asyncio.Task) -> None:
                    if self._inflight.get(key) is done_task:
                        self._inflight.pop(key, None)

                task.add_done_callback(_forget_inflight)
        return await task

    async def _load_and_store(self, key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        cache_key = None
        if self.settings is not None and self.namespace:
            try:
                from bot.infra.redis import cache_get_json, redis_key

                cache_key = redis_key(self.settings, "cache", self.namespace, key)
                cached = await cache_get_json(self.settings, cache_key)
                if cached is not None:
                    if self._is_cacheable(cached):
                        self._data[key] = (time.monotonic() + self.ttl_seconds, cached)
                    return cached
            except Exception:
                cache_key = None

        value = await loader()
        if self._is_cacheable(value):
            self._data[key] = (time.monotonic() + self.ttl_seconds, value)
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

    def invalidate(self, key: Optional[str] = None) -> None:
        if key is None:
            self._data.clear()
            return
        self._data.pop(key, None)

    async def invalidate_remote(self, key: Optional[str] = None) -> None:
        self.invalidate(key)
        if self.settings is None or not self.namespace:
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
