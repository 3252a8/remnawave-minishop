import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

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
    get_or_create_subscription_guides_public_subscription_cache,
    get_or_create_subscription_guides_public_subscription_lock,
    get_or_create_subscription_guides_resolved_config_cache,
    get_or_create_subscription_guides_resolved_config_lock,
    get_session_factory,
    get_settings,
)
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.config_link import prepare_config_links
from config.settings import Settings
from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    subscription_guides_status,
    validate_panel_subscription_guides_config,
)
from db.dal import subscription_dal, user_dal

from .common import (
    _require_user_id,
)
from .response_helpers import json_response

logger = logging.getLogger(__name__)

PANEL_DEFAULT_SUBPAGE_CONFIG_UUID = "00000000-0000-0000-0000-000000000000"
SUBSCRIPTION_GUIDES_CACHE_ERROR_TTL_SECONDS = 30
SUBSCRIPTION_GUIDES_RESOLVED_CACHE_TTL_SECONDS = 300
SUBSCRIPTION_GUIDES_RESOLVED_CACHE_MAX_ITEMS = 512
SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS = 300
SUBSCRIPTION_GUIDES_BROWSER_CACHE_CONTROL = "private, max-age=60"


class _PanelSubscriptionPageConfigUnavailable(SubscriptionGuidesConfigError):
    pass


def _subscription_guides_json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _subscription_guides_json_response(
    payload: dict[str, Any],
    *,
    status: int = 200,
    cache_control: str | None = None,
) -> web.Response:
    response = json_response(payload, status=status, dumps=_subscription_guides_json_dumps)
    if cache_control:
        response.headers["Cache-Control"] = cache_control
    return response


async def warm_subscription_guides_config(app: web.Application) -> None:
    try:
        await _subscription_guides_status_shared(app)
    except Exception as exc:
        logger.warning("Failed to warm subscription guides config: %s", exc)
    try:
        await _warm_panel_subscription_page_configs(app)
    except Exception as exc:
        logger.warning("Failed to warm panel subscription page configs: %s", exc)


async def subscription_guides_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    status = await _subscription_guides_status_for_request(request, user_id=user_id)
    payload = {
        "enabled": bool(status.get("enabled")),
        "config": _subscription_guides_response_config(status.get("config"))
        if status.get("enabled")
        else None,
        "source": status.get("source"),
    }
    if status.get("error"):
        payload["error"] = status["error"]
    return _subscription_guides_json_response(
        {"ok": True, **payload},
        cache_control=SUBSCRIPTION_GUIDES_BROWSER_CACHE_CONTROL if status.get("enabled") else None,
    )


async def public_subscription_guides_route(request: web.Request) -> web.Response:
    share_token = subscription_dal.normalize_install_share_token(
        request.match_info.get("share_token")
    )
    if not share_token:
        return json_response({"ok": False, "error": "invalid_share_token"}, status=404)

    subscription = await _public_subscription_payload_cached(request, share_token)
    if not subscription.get("active"):
        return _subscription_guides_json_response(
            {
                "ok": False,
                "enabled": False,
                "config": None,
                "source": None,
                "subscription": subscription,
                "error": "subscription_unavailable",
            },
            status=404,
        )

    panel_user_uuid = str(subscription.pop("_panel_user_uuid", "") or "").strip()
    status = await _subscription_guides_status_for_request(
        request,
        panel_short_uuid=subscription.get("panel_short_uuid"),
        panel_user_uuid=panel_user_uuid,
    )
    payload = {
        "enabled": bool(status.get("enabled")),
        "config": _subscription_guides_response_config(status.get("config"))
        if status.get("enabled")
        else None,
        "source": status.get("source"),
        "subscription": subscription,
    }
    if status.get("error"):
        payload["error"] = status["error"]
    return _subscription_guides_json_response(
        {"ok": True, **payload},
        cache_control=SUBSCRIPTION_GUIDES_BROWSER_CACHE_CONTROL if status.get("enabled") else None,
    )


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
        config_uuid = _panel_subpage_config_uuid(detail)
        if not config_uuid:
            config_uuid = await _external_squad_subpage_config_uuid_for_panel_user(
                panel_service,
                panel_user_uuid,
            )
        if config_uuid:
            config = await _panel_subscription_page_config_by_uuid_cached(
                app,
                settings,
                config_uuid,
            )
        else:
            try:
                config = validate_panel_subscription_guides_config(detail)
            except SubscriptionGuidesConfigError:
                panel_default = await _subscription_guides_status_from_panel_config(
                    app,
                    settings,
                )
                if not panel_default.get("enabled"):
                    raise SubscriptionGuidesConfigError(
                        str(panel_default.get("error") or "Panel default config is unavailable")
                    ) from None
                config = panel_default["config"]
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


def _panel_subpage_config_uuid(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in (
        "subpageConfigUuid",
        "subscriptionPageConfigUuid",
        "subPageConfigUuid",
        "subpage_config_uuid",
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    for key in (
        "response",
        "data",
        "result",
    ):
        nested = _panel_subpage_config_uuid(payload.get(key))
        if nested:
            return nested
    for key in (
        "subscriptionPageConfig",
        "subpageConfig",
        "subPageConfig",
    ):
        nested_payload = payload.get(key)
        nested = _panel_subpage_config_uuid(nested_payload)
        if nested:
            return nested
        if isinstance(nested_payload, dict):
            nested_uuid = str(nested_payload.get("uuid") or "").strip()
            if nested_uuid:
                return nested_uuid
    nested_uuid = str(payload.get("uuid") or "").strip()
    if nested_uuid and not _looks_like_panel_subscription_page_config(payload):
        return nested_uuid
    return ""


def _subscription_guides_response_config(config: Any) -> Any:
    if not isinstance(config, dict):
        return config

    svg_library = config.get("svgLibrary")
    if not isinstance(svg_library, dict) or not svg_library:
        return config

    referenced_keys = _subscription_guides_referenced_svg_keys(config)
    if not referenced_keys:
        return config

    compact_svg_library = {
        key: svg_library[key] for key in sorted(referenced_keys) if key in svg_library
    }
    if len(compact_svg_library) == len(svg_library):
        return config

    compact_config = dict(config)
    compact_config["svgLibrary"] = compact_svg_library
    return compact_config


def _subscription_guides_referenced_svg_keys(config: dict[str, Any]) -> set[str]:
    keys: set[str] = set()

    def add(value: Any) -> None:
        key = str(value or "").strip()
        if key:
            keys.add(key)

    platforms = config.get("platforms")
    if not isinstance(platforms, dict):
        return keys

    for platform in platforms.values():
        if not isinstance(platform, dict):
            continue
        add(platform.get("svgIconKey"))
        for app in platform.get("apps") or []:
            if not isinstance(app, dict):
                continue
            add(app.get("svgIconKey"))
            for block in app.get("blocks") or []:
                if not isinstance(block, dict):
                    continue
                add(block.get("svgIconKey"))
                for button in block.get("buttons") or []:
                    if isinstance(button, dict):
                        add(button.get("svgIconKey"))
    return keys


async def _default_panel_subscription_page_config_uuid(panel_service: Any) -> str:
    get_list = getattr(panel_service, "get_subscription_page_config_list", None)
    if not callable(get_list):
        return ""
    payload = await get_list()
    configs = _panel_subscription_page_config_items(payload)
    if not configs:
        return ""

    candidates: list[dict[str, Any]] = configs
    for item in candidates:
        uuid = str(item.get("uuid") or "").strip()
        if uuid == PANEL_DEFAULT_SUBPAGE_CONFIG_UUID:
            return uuid

    candidates.sort(key=lambda item: int(item.get("viewPosition") or 0))
    for item in candidates:
        uuid = str(item.get("uuid") or "").strip()
        if uuid:
            return uuid
    return ""


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


def _panel_subscription_page_config_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("configs", "items", "subscriptionPageConfigs", "subpageConfigs"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    for key in ("response", "data", "result"):
        items = _panel_subscription_page_config_items(payload.get(key))
        if items:
            return items
    return []


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


async def _public_subscription_payload_cached(
    request: web.Request,
    share_token: str,
) -> dict[str, Any]:
    settings: Settings = get_settings(request)
    ttl_seconds = max(
        0,
        int(settings.SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS or 0),
    )
    if ttl_seconds <= 0:
        return await _public_subscription_payload_uncached(request, share_token)

    cache = get_or_create_subscription_guides_public_subscription_cache(request.app)
    lock: asyncio.Lock = get_or_create_subscription_guides_public_subscription_lock(request.app)
    key = (
        str(share_token or "").strip(),
        _public_subscription_payload_fingerprint(request),
    )
    now = time.monotonic()

    cached = cache.get(key)
    if cached is not None and now - float(cached.get("ts", 0.0)) < ttl_seconds:
        return dict(cached["payload"])

    async with lock:
        now = time.monotonic()
        cached = cache.get(key)
        if cached is not None and now - float(cached.get("ts", 0.0)) < ttl_seconds:
            return dict(cached["payload"])

        payload = await _public_subscription_payload_uncached(request, share_token)
        if payload.get("active"):
            cache[key] = {"payload": dict(payload), "ts": time.monotonic()}
            _prune_subscription_guides_public_subscription_cache(cache)
        return payload


async def _public_subscription_payload_uncached(
    request: web.Request,
    share_token: str,
) -> dict[str, Any]:
    settings: Settings = get_settings(request)
    panel_service = _panel_service_from_app(request.app)
    raw_link = ""
    username = ""
    resolved_short_uuid = ""

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        local_sub = await subscription_dal.get_subscription_by_install_share_token(
            session,
            share_token,
        )

    if (
        local_sub
        and getattr(local_sub, "panel_user_uuid", None)
        and _local_subscription_is_publicly_active(local_sub)
        and panel_service
    ):
        panel_user = await panel_service.get_user_by_uuid(local_sub.panel_user_uuid)
        if panel_user:
            raw_link = str(panel_user.get("subscriptionUrl") or "").strip()
            username = str(panel_user.get("username") or "").strip()
            resolved_short_uuid = _panel_short_uuid_from_user(panel_user)

    display_link, connect_url = await prepare_config_links(settings, raw_link)
    return {
        "active": bool(display_link),
        "config_link": display_link,
        "connect_url": connect_url or display_link,
        "panel_short_uuid": resolved_short_uuid or None,
        "install_share_token": share_token,
        "username": username,
        "share_url": _public_install_url(request, share_token),
        "_panel_user_uuid": str(getattr(local_sub, "panel_user_uuid", "") or "").strip()
        if local_sub
        else "",
    }


def _public_subscription_payload_fingerprint(request: web.Request) -> tuple[str, ...]:
    settings: Settings = get_settings(request)
    headers = request.headers
    host = headers.get("X-Forwarded-Host") or headers.get("Host") or request.host
    proto = headers.get("X-Forwarded-Proto") or request.scheme or "https"
    return (
        str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip(),
        str(settings.PANEL_API_URL or "").strip(),
        str(settings.CRYPT4_REDIRECT_URL or "").strip(),
        str(bool(settings.CRYPT4_ENABLED)),
        str(host or "").strip().lower(),
        str(proto or "").strip().lower(),
    )


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


def _panel_external_squad_uuid_from_user(panel_user: Any) -> str:
    if not isinstance(panel_user, dict):
        return ""
    for key in ("externalSquadUuid", "external_squad_uuid", "externalSquadUUID"):
        value = str(panel_user.get(key) or "").strip()
        if value:
            return value
    return ""


def _looks_like_panel_subscription_page_config(payload: dict[str, Any]) -> bool:
    return "config" in payload or "viewPosition" in payload or "webpageAllowed" in payload


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


def _prune_subscription_guides_public_subscription_cache(cache: dict[Any, Any]) -> None:
    overflow = len(cache) - SUBSCRIPTION_GUIDES_RESOLVED_CACHE_MAX_ITEMS
    for key in list(cache.keys())[: max(0, overflow)]:
        cache.pop(key, None)


def _local_subscription_is_publicly_active(subscription: Any) -> bool:
    end_date = getattr(subscription, "end_date", None)
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)
    return bool(
        getattr(subscription, "is_active", False) and end_date and end_date > datetime.now(UTC)
    )


def _public_install_url(request: web.Request, share_token: str) -> str:
    settings: Settings = get_settings(request)
    configured_base = str(settings.SUBSCRIPTION_MINI_APP_URL or "").strip()
    if configured_base:
        parts = urlsplit(configured_base)
        if parts.scheme and parts.netloc:
            base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        else:
            base = configured_base.rstrip("/")
    else:
        host = (
            request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or request.host
        )
        proto = request.headers.get("X-Forwarded-Proto") or request.scheme or "https"
        base = f"{proto}://{host}"
    return f"{base.rstrip('/')}/s/{quote(share_token)}"


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
