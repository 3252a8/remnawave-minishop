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
