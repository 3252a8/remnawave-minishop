from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from bot.infra.redis import cache_delete, redis_key
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings

_WEBAPP_USER_PAYLOAD_CACHES: dict[tuple[int, str, int], AsyncTTLCache] = {}


def _webapp_user_payload_cache(
    settings: Settings,
    namespace: str,
    ttl_seconds: int,
) -> Optional[AsyncTTLCache]:
    ttl = max(0, int(ttl_seconds or 0))
    if ttl <= 0:
        return None
    cache_key = (id(settings), namespace, ttl)
    cache = _WEBAPP_USER_PAYLOAD_CACHES.get(cache_key)
    if cache is None:
        cache = AsyncTTLCache(
            ttl_seconds=ttl,
            settings=settings,
            namespace=f"webapp:{namespace}",
        )
        _WEBAPP_USER_PAYLOAD_CACHES[cache_key] = cache
    return cache


async def webapp_cached_user_payload(
    settings: Settings,
    namespace: str,
    user_id: int,
    ttl_seconds: int,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    cache = _webapp_user_payload_cache(settings, namespace, ttl_seconds)
    if cache is None:
        return await loader()
    return await cache.get_or_load(str(int(user_id)), loader)


def invalidate_local_webapp_user_payload(
    settings: Settings,
    namespace: str,
    user_id: int,
) -> None:
    key = str(int(user_id))
    for (settings_id, cache_namespace, _ttl), cache in tuple(
        _WEBAPP_USER_PAYLOAD_CACHES.items()
    ):
        if settings_id == id(settings) and cache_namespace == namespace:
            cache.invalidate(key)


async def invalidate_webapp_user_caches(
    settings: Settings,
    *user_ids: Optional[int],
    include_devices: bool = False,
) -> None:
    keys: list[str] = []
    seen: set[int] = set()
    for raw_user_id in user_ids:
        if raw_user_id is None:
            continue
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            continue
        if user_id in seen:
            continue
        seen.add(user_id)
        keys.append(redis_key(settings, "cache", "webapp", "me", user_id))
        invalidate_local_webapp_user_payload(settings, "me", user_id)
        if include_devices:
            keys.append(redis_key(settings, "cache", "webapp", "devices", user_id))
            invalidate_local_webapp_user_payload(settings, "devices", user_id)
    if keys:
        await cache_delete(settings, *keys)
