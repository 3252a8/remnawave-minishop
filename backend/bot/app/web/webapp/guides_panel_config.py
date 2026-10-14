"""Panel-driven subscription guides config resolution and caching.

Split out of ``guides.py`` (which re-exports the shared surface); route
handlers stay there.
"""

import asyncio
import hashlib
import logging
import time
from typing import Any, cast

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_app_optional_subscription_service,
    get_app_panel_service,
    get_app_settings,
    get_or_create_subscription_guides_config_cache,
    get_or_create_subscription_guides_config_lock,
    get_or_create_subscription_guides_panel_config_cache,
    get_or_create_subscription_guides_panel_config_lock,
    get_or_create_subscription_guides_resolved_config_cache,
    get_or_create_subscription_guides_resolved_config_lock,
    get_session_factory,
    get_settings,
)
from bot.services.subscription_guides_resolution import (
    _default_panel_subscription_page_config_uuid as _default_panel_subscription_page_config_uuid,
)
from bot.services.subscription_guides_resolution import (
    _looks_like_panel_subscription_page_config as _looks_like_panel_subscription_page_config,
)
from bot.services.subscription_guides_resolution import (
    _panel_external_squad_uuid_from_user as _panel_external_squad_uuid_from_user,
)
from bot.services.subscription_guides_resolution import (
    _panel_subpage_config_uuid as _panel_subpage_config_uuid,
)
from bot.services.subscription_guides_resolution import (
    _panel_subscription_page_config_items as _panel_subscription_page_config_items,
)
from bot.services.subscription_guides_resolution import (
    resolve_panel_subscription_guides_config,
)
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    subscription_guides_status,
    validate_panel_subscription_guides_config,
)
from db.dal import subscription_dal, user_dal

logger = logging.getLogger(__name__)

PANEL_DEFAULT_SUBPAGE_CONFIG_UUID = "00000000-0000-0000-0000-000000000000"
SUBSCRIPTION_GUIDES_CACHE_ERROR_TTL_SECONDS = 30
SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS = 300
SUBSCRIPTION_GUIDES_RESOLVED_CACHE_MAX_ITEMS = 512


class _PanelSubscriptionPageConfigUnavailable(SubscriptionGuidesConfigError):
    pass


async def _subscription_guides_status_shared(app: web.Application) -> dict[str, Any]:
    settings: Settings = get_app_settings(app)
    cache = get_or_create_subscription_guides_config_cache(app)
    lock: asyncio.Lock = get_or_create_subscription_guides_config_lock(app)
    fingerprint = _subscription_guides_settings_fingerprint(settings)
    now = time.monotonic()

    cached = cache.get("status")
    if (
        cached is not None
        and cache.get("fingerprint") == fingerprint
        and (
            cached.get("enabled")
            or now - float(cache.get("ts", 0.0)) < SUBSCRIPTION_GUIDES_CACHE_ERROR_TTL_SECONDS
        )
    ):
        return cached

    async with lock:
        cached = cache.get("status")
        if (
            cached is not None
            and cache.get("fingerprint") == fingerprint
            and (
                cached.get("enabled")
                or now - float(cache.get("ts", 0.0)) < SUBSCRIPTION_GUIDES_CACHE_ERROR_TTL_SECONDS
            )
        ):
            return cached

        status = await _load_subscription_guides_status(app, settings)
        cache["fingerprint"] = fingerprint
        cache["status"] = status
        cache["ts"] = time.monotonic()
        return status


async def _subscription_guides_status_for_request(
    request: web.Request,
    *,
    user_id: int | None = None,
    panel_short_uuid: str | None = None,
    panel_user_uuid: str | None = None,
) -> dict[str, Any]:
    settings: Settings = get_settings(request)
    if not _subscription_guides_should_try_resolved_panel_config(settings):
        return await _subscription_guides_status_shared(request.app)

    short_uuid = str(panel_short_uuid or "").strip()
    resolved_panel_user_uuid = str(panel_user_uuid or "").strip()
    short_uuid_from_local_db = False
    if not short_uuid and user_id is not None:
        context = await _active_panel_subscription_context_for_user(request, int(user_id))
        short_uuid = str(context.get("panel_short_uuid") or "").strip()
        resolved_panel_user_uuid = str(context.get("panel_user_uuid") or "").strip()
        short_uuid_from_local_db = context.get("source") == "local"

    if short_uuid:
        request_headers = _subscription_page_request_headers(request)
        panel_status = await _subscription_guides_status_from_panel_short_uuid_cached(
            request.app,
            settings,
            short_uuid,
            panel_user_uuid=resolved_panel_user_uuid,
            request_headers=request_headers,
        )
        if panel_status.get("enabled"):
            return panel_status
        if short_uuid_from_local_db and resolved_panel_user_uuid:
            # The locally stored short UUID goes stale when the subscription
            # link is revoked/reset on the panel side; retry with a fresh one
            # before falling back to the shared default config.
            fresh_short_uuid = await _fresh_panel_short_uuid(request.app, resolved_panel_user_uuid)
            if fresh_short_uuid and fresh_short_uuid != short_uuid:
                panel_status = await _subscription_guides_status_from_panel_short_uuid_cached(
                    request.app,
                    settings,
                    fresh_short_uuid,
                    panel_user_uuid=resolved_panel_user_uuid,
                    request_headers=request_headers,
                )
                if panel_status.get("enabled"):
                    return panel_status

    return await _subscription_guides_status_shared(request.app)


async def _load_subscription_guides_status(
    app: web.Application,
    settings: Settings,
) -> dict[str, Any]:
    if not bool(settings.SUBSCRIPTION_GUIDES_ENABLED):
        return {"enabled": False, "config": None, "source": None, "error": None}

    if _subscription_guides_admin_json_override_enabled(settings):
        return subscription_guides_status(settings)

    if bool(settings.SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED):
        panel_status = await _subscription_guides_status_from_panel_config(app, settings)
        if panel_status.get("enabled"):
            return panel_status

    return subscription_guides_status(settings)


async def _subscription_guides_status_from_panel_config(
    app: web.Application,
    settings: Settings,
) -> dict[str, Any]:
    panel_service = _panel_service_from_app(app)
    if panel_service is None:
        return {
            "enabled": False,
            "config": None,
            "source": "panel",
            "error": "Panel service is unavailable",
        }

    try:
        config_uuid = str(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_UUID", "") or "").strip()
        if not config_uuid:
            config_uuid = await _default_panel_subscription_page_config_uuid(panel_service)
        config_uuid = config_uuid or PANEL_DEFAULT_SUBPAGE_CONFIG_UUID
        try:
            config = await _panel_subscription_page_config_by_uuid_cached(
                app,
                settings,
                config_uuid,
            )
        except _PanelSubscriptionPageConfigUnavailable:
            if config_uuid == PANEL_DEFAULT_SUBPAGE_CONFIG_UUID:
                raise
            config = await _panel_subscription_page_config_by_uuid_cached(
                app,
                settings,
                PANEL_DEFAULT_SUBPAGE_CONFIG_UUID,
            )
    except (SubscriptionGuidesConfigError, Exception) as exc:
        logger.warning("Failed to load subscription guides config from Remnawave Panel: %s", exc)
        return {"enabled": False, "config": None, "source": "panel", "error": str(exc)}

    return {"enabled": True, "config": config, "source": "panel", "error": None}


async def _subscription_guides_status_from_panel_short_uuid_cached(
    app: web.Application,
    settings: Settings,
    short_uuid: str,
    *,
    panel_user_uuid: str | None = None,
    request_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    ttl_seconds = max(
        0,
        int(settings.SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS or 0),
    )
    if ttl_seconds <= 0:
        return await _subscription_guides_status_from_panel_short_uuid(
            app,
            settings,
            short_uuid,
            panel_user_uuid=panel_user_uuid,
            request_headers=request_headers,
        )

    cache = get_or_create_subscription_guides_resolved_config_cache(app)
    lock: asyncio.Lock = get_or_create_subscription_guides_resolved_config_lock(app)
    key = (
        _subscription_guides_settings_fingerprint(settings),
        str(short_uuid or "").strip(),
        str(panel_user_uuid or "").strip(),
        _subscription_guides_request_headers_fingerprint(request_headers or {}),
    )
    now = time.monotonic()

    cached = cache.get(key)
    if cached is not None and now - float(cached.get("ts", 0.0)) < ttl_seconds:
        return cached["status"]

    async with lock:
        now = time.monotonic()
        cached = cache.get(key)
        if cached is not None and now - float(cached.get("ts", 0.0)) < ttl_seconds:
            return cached["status"]

        status = await _subscription_guides_status_from_panel_short_uuid(
            app,
            settings,
            short_uuid,
            panel_user_uuid=panel_user_uuid,
            request_headers=request_headers,
        )
        if status.get("enabled"):
            cache[key] = {"status": status, "ts": time.monotonic()}
            _prune_subscription_guides_resolved_cache(cache)
        return status


async def _subscription_guides_status_from_panel_short_uuid(
    app: web.Application,
    settings: Settings,
    short_uuid: str,
    *,
    panel_user_uuid: str | None = None,
    request_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    panel_service = _panel_service_from_app(app)
    get_config = getattr(panel_service, "get_subscription_page_config_by_short_uuid", None)
    if not callable(get_config):
        return {
            "enabled": False,
            "config": None,
            "source": "panel",
            "error": "Panel service cannot resolve subscription page config by short UUID",
        }

    try:
        detail = await get_config(short_uuid, request_headers=request_headers or {})
        if detail is None:
            raise SubscriptionGuidesConfigError(
                f"Panel subscription page config for subscription {short_uuid} is unavailable"
            )

        async def owner_configuration() -> str:
            return await _external_squad_subpage_config_uuid_for_panel_user(
                panel_service, panel_user_uuid
            )

        async def configuration_by_uuid(config_uuid: str) -> dict[str, Any]:
            return await _panel_subscription_page_config_by_uuid_cached(app, settings, config_uuid)

        async def default_configuration() -> dict[str, Any]:
            status = await _subscription_guides_status_from_panel_config(app, settings)
            if not status.get("enabled"):
                raise SubscriptionGuidesConfigError(
                    str(status.get("error") or "Panel default config is unavailable")
                )
            return cast(dict[str, Any], status["config"])

        config = await resolve_panel_subscription_guides_config(
            detail,
            owner_configuration=owner_configuration,
            configuration_by_uuid=configuration_by_uuid,
            default_configuration=default_configuration,
        )
    except Exception as exc:
        logger.warning(
            "Failed to load resolved subscription guides config from Remnawave Panel: %s",
            exc,
        )
        return {"enabled": False, "config": None, "source": "panel", "error": str(exc)}

    return {"enabled": True, "config": config, "source": "panel", "error": None}


async def _panel_subscription_page_config_by_uuid_cached(
    app: web.Application,
    settings: Settings,
    config_uuid: str,
) -> dict[str, Any]:
    config_uuid = str(config_uuid or "").strip()
    if not config_uuid:
        raise SubscriptionGuidesConfigError("Panel subscription page config UUID is empty")

    ttl_seconds = max(
        0,
        int(settings.SUBSCRIPTION_GUIDES_CONFIG_CACHE_TTL_SECONDS or 0),
    )
    if ttl_seconds <= 0:
        return await _load_panel_subscription_page_config_by_uuid(app, config_uuid)

    cache = get_or_create_subscription_guides_panel_config_cache(app)
    lock: asyncio.Lock = get_or_create_subscription_guides_panel_config_lock(app)
    key = (_subscription_guides_settings_fingerprint(settings), config_uuid)
    now = time.monotonic()

    cached = cache.get(key)
    if cached is not None and now - float(cached.get("ts", 0.0)) < ttl_seconds:
        return cached["config"]

    async with lock:
        now = time.monotonic()
        cached = cache.get(key)
        if cached is not None and now - float(cached.get("ts", 0.0)) < ttl_seconds:
            return cached["config"]

        config = await _load_panel_subscription_page_config_by_uuid(app, config_uuid)
        cache[key] = {"config": config, "ts": time.monotonic()}
        _prune_subscription_guides_panel_config_cache(cache)
        return config


async def _load_panel_subscription_page_config_by_uuid(
    app: web.Application,
    config_uuid: str,
) -> dict[str, Any]:
    panel_service = _panel_service_from_app(app)
    get_config_by_uuid = getattr(panel_service, "get_subscription_page_config_by_uuid", None)
    if not callable(get_config_by_uuid):
        raise SubscriptionGuidesConfigError(
            "Panel service cannot load subscription page config by UUID"
        )
    detail = await get_config_by_uuid(config_uuid)
    if detail is None:
        raise _PanelSubscriptionPageConfigUnavailable(
            f"Panel subscription page config {config_uuid} is unavailable"
        )
    return validate_panel_subscription_guides_config(detail)


async def _warm_panel_subscription_page_configs(app: web.Application) -> None:
    settings: Settings = get_app_settings(app)
    if not _subscription_guides_should_try_resolved_panel_config(settings):
        return

    panel_service = _panel_service_from_app(app)
    get_list = getattr(panel_service, "get_subscription_page_config_list", None)
    if not callable(get_list):
        return

    payload = await get_list()
    configs = _panel_subscription_page_config_items(payload)
    config_uuids = [
        str(item.get("uuid") or "").strip()
        for item in configs
        if str(item.get("uuid") or "").strip()
    ]
    if not config_uuids:
        return

    seen: set[str] = set()
    warmed_uuids: list[str] = []
    tasks = []
    for config_uuid in config_uuids:
        if config_uuid in seen:
            continue
        seen.add(config_uuid)
        warmed_uuids.append(config_uuid)
        tasks.append(_panel_subscription_page_config_by_uuid_cached(app, settings, config_uuid))
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for config_uuid, result in zip(warmed_uuids, results, strict=True):
            if isinstance(result, Exception):
                logger.debug(
                    "Failed to warm panel subscription page config %s: %s",
                    config_uuid,
                    result,
                )


async def _active_panel_subscription_context_for_user(
    request: web.Request,
    user_id: int,
) -> dict[str, str]:
    panel_service = _panel_service_from_app(request.app)
    get_user = getattr(panel_service, "get_user_by_uuid", None)
    if not callable(get_user):
        return {}

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        db_user = await user_dal.get_user_by_id(session, user_id)
        panel_user_uuid = str(getattr(db_user, "panel_user_uuid", "") or "").strip()
        if not panel_user_uuid:
            return {}
        local_sub = await subscription_dal.get_active_subscription_by_user_id(
            session,
            user_id,
            panel_user_uuid,
        )
        if not local_sub:
            return {}
        panel_short_uuid = str(getattr(local_sub, "panel_subscription_uuid", "") or "").strip()
        if panel_short_uuid:
            return {
                "panel_short_uuid": panel_short_uuid,
                "panel_user_uuid": panel_user_uuid,
                "source": "local",
            }

    try:
        panel_user = await get_user(panel_user_uuid)
    except Exception:
        logger.warning(
            "Failed to resolve panel short UUID for install guides user %s",
            user_id,
            exc_info=True,
        )
        return {"panel_user_uuid": panel_user_uuid}
    return {
        "panel_short_uuid": _panel_short_uuid_from_user(panel_user),
        "panel_user_uuid": panel_user_uuid,
        "source": "panel",
    }


async def _fresh_panel_short_uuid(app: web.Application, panel_user_uuid: str) -> str:
    panel_service = _panel_service_from_app(app)
    get_user = getattr(panel_service, "get_user_by_uuid", None)
    if not callable(get_user):
        return ""
    try:
        panel_user = await get_user(panel_user_uuid)
    except Exception:
        logger.warning(
            "Failed to refresh panel short UUID for install guides panel user %s",
            panel_user_uuid,
            exc_info=True,
        )
        return ""
    return _panel_short_uuid_from_user(panel_user)


def _panel_service_from_app(app: web.Application) -> Any:
    subscription_service: SubscriptionService | None = get_app_optional_subscription_service(app)
    panel_service = (
        getattr(subscription_service, "panel_service", None) if subscription_service else None
    )
    return panel_service or get_app_panel_service(app)


def _panel_short_uuid_from_user(panel_user: Any) -> str:
    if not isinstance(panel_user, dict):
        return ""
    for key in ("shortUuid", "shortUUID", "short_uuid"):
        value = str(panel_user.get(key) or "").strip()
        if value:
            return value
    return ""


async def _external_squad_subpage_config_uuid_for_panel_user(
    panel_service: Any,
    panel_user_uuid: str | None,
) -> str:
    user_uuid = str(panel_user_uuid or "").strip()
    if not user_uuid:
        return ""
    get_user = getattr(panel_service, "get_user_by_uuid", None)
    if not callable(get_user):
        return ""
    try:
        panel_user = await get_user(user_uuid)
    except Exception:
        logger.warning(
            "Failed to resolve external squad for install guides panel user %s",
            user_uuid,
            exc_info=True,
        )
        return ""

    external_squad_uuid = _panel_external_squad_uuid_from_user(panel_user)
    if not external_squad_uuid:
        return ""

    get_external_squad = getattr(panel_service, "get_external_squad", None)
    if not callable(get_external_squad):
        return ""
    try:
        external_squad = await get_external_squad(external_squad_uuid)
    except Exception:
        logger.warning(
            "Failed to resolve external squad %s for install guides",
            external_squad_uuid,
            exc_info=True,
        )
        return ""
    return _panel_subpage_config_uuid(external_squad)


def _subscription_guides_admin_json_override_enabled(settings: Settings) -> bool:
    admin_json = str(settings.SUBSCRIPTION_PAGE_CONFIG_JSON or "").strip()
    return bool(admin_json and bool(settings.SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED))


def _subscription_guides_should_try_resolved_panel_config(settings: Settings) -> bool:
    return bool(
        settings.SUBSCRIPTION_GUIDES_ENABLED
        and settings.SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED
        and not _subscription_guides_admin_json_override_enabled(settings)
    )


def _subscription_guides_settings_fingerprint(settings: Settings) -> tuple[Any, ...]:
    admin_json = str(settings.SUBSCRIPTION_PAGE_CONFIG_JSON or "")
    return (
        bool(settings.SUBSCRIPTION_GUIDES_ENABLED),
        bool(settings.SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED),
        bool(settings.SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED),
        str(settings.SUBSCRIPTION_PAGE_CONFIG_PATH or ""),
        str(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_UUID", "") or ""),
        hashlib.sha256(admin_json.encode("utf-8")).hexdigest(),
        str(settings.PANEL_API_URL or ""),
        bool(settings.PANEL_API_KEY or ""),
    )


def _subscription_guides_request_headers_fingerprint(headers: dict[str, str]) -> tuple[str, ...]:
    return (
        str(headers.get("host") or "").strip().lower(),
        str(headers.get("x-forwarded-host") or "").strip().lower(),
        str(headers.get("x-forwarded-proto") or "").strip().lower(),
    )


def _prune_subscription_guides_resolved_cache(cache: dict[Any, Any]) -> None:
    overflow = len(cache) - SUBSCRIPTION_GUIDES_RESOLVED_CACHE_MAX_ITEMS
    for key in list(cache.keys())[: max(0, overflow)]:
        cache.pop(key, None)


def _prune_subscription_guides_panel_config_cache(cache: dict[Any, Any]) -> None:
    overflow = len(cache) - SUBSCRIPTION_GUIDES_RESOLVED_CACHE_MAX_ITEMS
    for key in list(cache.keys())[: max(0, overflow)]:
        cache.pop(key, None)


def _subscription_page_request_headers(request: web.Request) -> dict[str, str]:
    headers = request.headers
    host = headers.get("X-Forwarded-Host") or headers.get("Host") or request.host
    proto = headers.get("X-Forwarded-Proto") or request.scheme or "https"
    user_agent = headers.get(
        "User-Agent",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari",
    )
    return {
        "host": host,
        "x-forwarded-host": host,
        "x-forwarded-proto": proto,
        "user-agent": user_agent,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": headers.get("Accept-Language", "ru,en;q=0.9"),
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "upgrade-insecure-requests": "1",
    }
