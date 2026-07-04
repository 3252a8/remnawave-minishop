"""Helpers for webapp cache lifecycle and runtime invalidation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Awaitable, Callable, Optional, cast

from aiohttp import web

from bot.app.web.context import (
    get_app_webapp_settings_cache,
    get_or_create_subscription_guides_config_cache,
    get_or_create_subscription_guides_panel_config_cache,
    get_or_create_subscription_guides_public_subscription_cache,
    get_or_create_subscription_guides_resolved_config_cache,
    set_webapp_logo_cache,
)
from bot.infra.redis import cache_delete, cache_delete_pattern, redis_key
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings

_WEBAPP_USER_PAYLOAD_CACHES: dict[tuple[int, str, int], AsyncTTLCache] = {}


def _changed_setting_keys(
    updates: Mapping[str, Any] | None = None,
    deletes: Sequence[Any] | None = None,
) -> set[str]:
    keys = {str(key) for key in (updates or {}).keys()}
    keys.update(str(key) for key in (deletes or []) if key is not None)
    return keys


WEBAPP_APPEARANCE_SETTING_KEYS = frozenset(
    {
        "WEBAPP_TITLE",
        "WEBAPP_HOME_BRAND_VISIBLE",
        "WEBAPP_TARIFF_CHANGE_VISIBLE",
        "WEBAPP_LOGO_URL",
        "WEBAPP_FAVICON_URL",
        "WEBAPP_FAVICON_USE_CUSTOM",
        "WEBAPP_LOGO_FAVICON_URL",
    }
)

WEBAPP_APPEARANCE_ASSET_URL_SETTING_KEYS = frozenset(
    {
        "WEBAPP_LOGO_URL",
        "WEBAPP_FAVICON_URL",
        "WEBAPP_LOGO_FAVICON_URL",
    }
)

WEBAPP_DEVICE_PAYLOAD_SETTING_KEYS = frozenset(
    {
        "MY_DEVICES_SECTION_ENABLED",
        "USER_HWID_DEVICE_LIMIT",
        "USER_TRAFFIC_LIMIT_GB",
        "USER_TRAFFIC_STRATEGY",
    }
)


def reset_webapp_settings_cache(app: Mapping[object, object]) -> None:
    cache = get_app_webapp_settings_cache(app)
    if isinstance(cache, dict):
        cache["ts"] = 0.0
        cache["data"] = {}


def reset_subscription_guides_cache(app: Mapping[object, object]) -> None:
    application = cast(web.Application, app)
    cache = get_or_create_subscription_guides_config_cache(application)
    if isinstance(cache, dict):
        cache["fingerprint"] = None
        cache["status"] = None
    panel_cache = get_or_create_subscription_guides_panel_config_cache(application)
    if isinstance(panel_cache, dict):
        panel_cache.clear()
    resolved_cache = get_or_create_subscription_guides_resolved_config_cache(application)
    if isinstance(resolved_cache, dict):
        resolved_cache.clear()
    public_cache = get_or_create_subscription_guides_public_subscription_cache(application)
    if isinstance(public_cache, dict):
        public_cache.clear()


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
    for (settings_id, cache_namespace, _ttl), cache in tuple(_WEBAPP_USER_PAYLOAD_CACHES.items()):
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

    for (settings_id, cache_namespace, _ttl), cache in tuple(_WEBAPP_USER_PAYLOAD_CACHES.items()):
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


async def refresh_webapp_runtime_after_settings_change(
    request: Any,
    *,
    updates: Mapping[str, Any] | None = None,
    deletes: Sequence[Any] | None = None,
    include_user_payloads: bool = True,
) -> None:
    from bot.app.web.context import get_settings

    settings = get_settings(request)
    keys = _changed_setting_keys(updates, deletes)
    app = request.app

    reset_webapp_settings_cache(app)
    reset_subscription_guides_cache(app)

    if include_user_payloads:
        await invalidate_all_webapp_user_payloads(
            settings,
            include_devices=bool(keys & WEBAPP_DEVICE_PAYLOAD_SETTING_KEYS),
        )

    if keys & WEBAPP_APPEARANCE_SETTING_KEYS:
        set_webapp_logo_cache(app, None)
        from bot.app.web.admin_api_impl.themes import prune_unused_appearance_assets

        extra_keep_urls = [
            str(value)
            for key, value in (updates or {}).items()
            if key in WEBAPP_APPEARANCE_ASSET_URL_SETTING_KEYS and value
        ]
        prune_unused_appearance_assets(settings, extra_keep_urls=extra_keep_urls)


__all__ = [
    "reset_webapp_settings_cache",
    "reset_subscription_guides_cache",
    "invalidate_all_webapp_user_payloads",
    "invalidate_webapp_user_caches",
    "invalidate_all_webapp_user_caches",
    "webapp_cached_user_payload",
    "refresh_webapp_runtime_after_settings_change",
]
