from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from bot.infra.redis import cache_delete, cache_delete_pattern, redis_key
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings

_WEBAPP_USER_PAYLOAD_CACHES: dict[tuple[int, str, int], AsyncTTLCache] = {}


def reset_webapp_settings_cache(app: Any) -> None:
    cache = app.get("webapp_settings_cache") if hasattr(app, "get") else None
    if isinstance(cache, dict):
        cache["ts"] = 0.0
        cache["data"] = {}


def reset_subscription_guides_cache(app: Any) -> None:
    cache = app.get("subscription_guides_config_cache") if hasattr(app, "get") else None
    if isinstance(cache, dict):
        cache["fingerprint"] = None
        cache["status"] = None


def _payload_namespaces(include_devices: bool = False) -> tuple[str, ...]:
    return ("me", "devices") if include_devices else ("me",)


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


def invalidate_all_local_webapp_user_payloads(
    settings: Settings,
    namespace: Optional[str] = None,
    *,
    include_devices: Optional[bool] = None,
) -> None:
    if include_devices is not None:
        namespaces: Optional[set[str]] = set(_payload_namespaces(include_devices))
    elif namespace is not None:
        namespaces = {namespace}
    else:
        namespaces = None

    for (settings_id, cache_namespace, _ttl), cache in tuple(
        _WEBAPP_USER_PAYLOAD_CACHES.items()
    ):
        if settings_id != id(settings):
            continue
        if namespaces is not None and cache_namespace not in namespaces:
            continue
        cache.invalidate()


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


async def invalidate_all_webapp_user_payloads(
    settings: Settings,
    *,
    include_devices: bool = False,
) -> None:
    for namespace in _payload_namespaces(include_devices):
        invalidate_all_local_webapp_user_payloads(settings, namespace=namespace)
        try:
            pattern = redis_key(settings, "cache", "webapp", namespace, "*")
            await cache_delete_pattern(settings, pattern)
        except Exception:
            continue


async def invalidate_all_webapp_user_caches(
    settings: Settings,
    *,
    include_devices: bool = False,
) -> None:
    await invalidate_all_webapp_user_payloads(settings, include_devices=include_devices)
