import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

WataGetResult = tuple[bool, dict[str, Any]]
WataGetCacheKey = tuple[str, str, str]

_WATA_GET_RATE_LIMIT_SECONDS = 30.0


@dataclass(frozen=True)
class _WataGetCacheEntry:
    expires_at: float
    success: bool
    data: dict[str, Any]
    in_flight: bool = False


def retry_after_seconds(
    header_value: str | None,
    payload: Mapping[str, Any] | None,
) -> float | None:
    if header_value:
        try:
            return max(0.0, float(header_value.strip()))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(header_value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass

    containers = [payload]
    if payload and isinstance(payload.get("data"), Mapping):
        containers.append(payload["data"])
    for container in containers:
        if not container:
            continue
        for key in ("retryAfter", "retryAfterSeconds", "retry_after", "retry_after_seconds"):
            value = container.get(key)
            if value is None:
                continue
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                continue

    if payload:
        for key in ("message", "details"):
            value = payload.get(key)
            if not isinstance(value, str):
                continue
            match = re.search(r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?)", value, re.IGNORECASE)
            if match:
                return max(0.0, float(match.group(1)))
    return None


class WataGetRateLimiter:
    def __init__(self) -> None:
        self._cache: dict[WataGetCacheKey, _WataGetCacheEntry] = {}
        self._locks: dict[WataGetCacheKey, asyncio.Lock] = {}

    @staticmethod
    def cache_key(resource: str, client: str, object_id: str) -> WataGetCacheKey:
        return resource, client, object_id

    def _prune(self, now: float) -> None:
        expired = [key for key, entry in self._cache.items() if entry.expires_at <= now]
        for key in expired:
            self._cache.pop(key, None)
            lock = self._locks.get(key)
            if lock is not None and not lock.locked():
                self._locks.pop(key, None)

    def remember(
        self,
        cache_key: WataGetCacheKey,
        result: WataGetResult,
        *,
        started_at: float | None = None,
    ) -> None:
        success, data = result
        now = time.monotonic()
        if not success and data.get("status") == 429:
            retry_after = data.get("retry_after_seconds")
            if retry_after is None:
                retry_after = _WATA_GET_RATE_LIMIT_SECONDS
            try:
                cooldown = max(0.0, float(retry_after))
            except (TypeError, ValueError):
                cooldown = _WATA_GET_RATE_LIMIT_SECONDS
            expires_at = now + cooldown
        else:
            expires_at = (started_at if started_at is not None else now) + (
                _WATA_GET_RATE_LIMIT_SECONDS
            )
        self._cache[cache_key] = _WataGetCacheEntry(
            expires_at=expires_at,
            success=success,
            data=dict(data),
        )

    async def run(
        self,
        cache_key: WataGetCacheKey,
        request: Callable[[], Awaitable[WataGetResult]],
    ) -> WataGetResult:
        now = time.monotonic()
        self._prune(now)
        cached = self._cache.get(cache_key)
        if cached and cached.expires_at > now and not cached.in_flight:
            return cached.success, dict(cached.data)

        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cached = self._cache.get(cache_key)
            if cached and cached.expires_at > now:
                return cached.success, dict(cached.data)

            self._cache[cache_key] = _WataGetCacheEntry(
                expires_at=now + _WATA_GET_RATE_LIMIT_SECONDS,
                success=False,
                data={
                    "status": 429,
                    "message": "local_rate_limited",
                    "retry_after_seconds": _WATA_GET_RATE_LIMIT_SECONDS,
                },
                in_flight=True,
            )
            result = await request()
            self.remember(cache_key, result, started_at=now)
            return result
