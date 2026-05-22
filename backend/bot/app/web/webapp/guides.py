# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

from config.subscription_guides_config import (
    SubscriptionGuidesConfigError,
    subscription_guides_status,
    validate_panel_subscription_guides_config,
)

PANEL_DEFAULT_SUBPAGE_CONFIG_UUID = "00000000-0000-0000-0000-000000000000"
SUBSCRIPTION_GUIDES_CACHE_ERROR_TTL_SECONDS = 30


async def warm_subscription_guides_config(app: web.Application) -> None:
    try:
        await _subscription_guides_status_shared(app)
    except Exception as exc:
        logger.warning("Failed to warm subscription guides config: %s", exc)


async def subscription_guides_route(request: web.Request) -> web.Response:
    _require_user_id(request)
    status = await _subscription_guides_status_shared(request.app)
    payload = {
        "enabled": bool(status.get("enabled")),
        "config": status.get("config") if status.get("enabled") else None,
        "source": status.get("source"),
    }
    if status.get("error"):
        payload["error"] = status["error"]
    return web.json_response({"ok": True, **payload})


async def public_subscription_guides_route(request: web.Request) -> web.Response:
    share_token = subscription_dal.normalize_install_share_token(
        request.match_info.get("share_token")
    )
    if not share_token:
        return web.json_response({"ok": False, "error": "invalid_share_token"}, status=404)

    subscription = await _public_subscription_payload(request, share_token)
    if not subscription.get("active"):
        return web.json_response(
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

    status = await _subscription_guides_status_shared(request.app)
    payload = {
        "enabled": bool(status.get("enabled")),
        "config": status.get("config") if status.get("enabled") else None,
        "source": status.get("source"),
        "subscription": subscription,
    }
    if status.get("error"):
        payload["error"] = status["error"]
    return web.json_response({"ok": True, **payload})


async def _subscription_guides_status_shared(app: web.Application) -> Dict[str, Any]:
    settings: Settings = app["settings"]
    cache = app.setdefault("subscription_guides_config_cache", {})
    lock: asyncio.Lock = app.setdefault("subscription_guides_config_lock", asyncio.Lock())
    fingerprint = _subscription_guides_settings_fingerprint(settings)
    now = time.monotonic()

    cached = cache.get("status")
    if cached is not None and cache.get("fingerprint") == fingerprint:
        if cached.get("enabled") or now - float(cache.get("ts", 0.0)) < (
            SUBSCRIPTION_GUIDES_CACHE_ERROR_TTL_SECONDS
        ):
            return cached

    async with lock:
        cached = cache.get("status")
        if cached is not None and cache.get("fingerprint") == fingerprint:
            if cached.get("enabled") or now - float(cache.get("ts", 0.0)) < (
                SUBSCRIPTION_GUIDES_CACHE_ERROR_TTL_SECONDS
            ):
                return cached

        status = await _load_subscription_guides_status(app, settings)
        cache["fingerprint"] = fingerprint
        cache["status"] = status
        cache["ts"] = time.monotonic()
        return status


async def _load_subscription_guides_status(
    app: web.Application,
    settings: Settings,
) -> Dict[str, Any]:
    if not bool(getattr(settings, "SUBSCRIPTION_GUIDES_ENABLED", False)):
        return {"enabled": False, "config": None, "source": None, "error": None}

    admin_json = str(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_JSON", "") or "").strip()
    json_override_enabled = bool(
        getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED", False)
    )
    if admin_json and json_override_enabled:
        return subscription_guides_status(settings)

    if bool(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED", True)):
        panel_status = await _subscription_guides_status_from_panel_config(app, settings)
        if panel_status.get("enabled"):
            return panel_status

    return subscription_guides_status(settings)


async def _subscription_guides_status_from_panel_config(
    app: web.Application,
    settings: Settings,
) -> Dict[str, Any]:
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
        detail = await panel_service.get_subscription_page_config_by_uuid(config_uuid)
        if detail is None and config_uuid != PANEL_DEFAULT_SUBPAGE_CONFIG_UUID:
            detail = await panel_service.get_subscription_page_config_by_uuid(
                PANEL_DEFAULT_SUBPAGE_CONFIG_UUID
            )
        if detail is None:
            raise SubscriptionGuidesConfigError(
                f"Panel subscription page config {config_uuid} is unavailable"
            )
        config = validate_panel_subscription_guides_config(detail)
    except (SubscriptionGuidesConfigError, Exception) as exc:
        logger.warning("Failed to load subscription guides config from Remnawave Panel: %s", exc)
        return {"enabled": False, "config": None, "source": "panel", "error": str(exc)}

    return {"enabled": True, "config": config, "source": "panel", "error": None}


async def _default_panel_subscription_page_config_uuid(panel_service: Any) -> str:
    get_list = getattr(panel_service, "get_subscription_page_config_list", None)
    if not callable(get_list):
        return ""
    payload = await get_list()
    configs = (payload or {}).get("configs")
    if not isinstance(configs, list):
        return ""

    candidates: list[Dict[str, Any]] = [item for item in configs if isinstance(item, dict)]
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


async def _public_subscription_payload(
    request: web.Request,
    share_token: str,
) -> Dict[str, Any]:
    settings: Settings = request.app["settings"]
    panel_service = _panel_service_from_app(request.app)
    raw_link = ""
    username = ""
    resolved_short_uuid = ""

    async_session_factory: sessionmaker = request.app["async_session_factory"]
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
            resolved_short_uuid = str(panel_user.get("shortUuid") or "").strip()

    display_link, connect_url = await prepare_config_links(settings, raw_link)
    return {
        "active": bool(display_link),
        "config_link": display_link,
        "connect_url": connect_url or display_link,
        "panel_short_uuid": resolved_short_uuid or None,
        "install_share_token": share_token,
        "username": username,
        "share_url": _public_install_url(request, share_token),
    }


def _panel_service_from_app(app: web.Application) -> Any:
    subscription_service: Optional[SubscriptionService] = app.get("subscription_service")
    panel_service = (
        getattr(subscription_service, "panel_service", None) if subscription_service else None
    )
    return panel_service or app.get("panel_service")


def _subscription_guides_settings_fingerprint(settings: Settings) -> Tuple[Any, ...]:
    admin_json = str(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_JSON", "") or "")
    return (
        bool(getattr(settings, "SUBSCRIPTION_GUIDES_ENABLED", False)),
        bool(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED", True)),
        bool(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED", False)),
        str(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_PATH", "") or ""),
        str(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_UUID", "") or ""),
        hashlib.sha256(admin_json.encode("utf-8")).hexdigest(),
        str(getattr(settings, "PANEL_API_URL", "") or ""),
        bool(getattr(settings, "PANEL_API_KEY", "") or ""),
    )


def _local_subscription_is_publicly_active(subscription: Any) -> bool:
    end_date = getattr(subscription, "end_date", None)
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    return bool(
        getattr(subscription, "is_active", False)
        and end_date
        and end_date > datetime.now(timezone.utc)
    )


def _public_install_url(request: web.Request, share_token: str) -> str:
    settings: Settings = request.app["settings"]
    configured_base = str(getattr(settings, "SUBSCRIPTION_MINI_APP_URL", "") or "").strip()
    if configured_base:
        parts = urlsplit(configured_base)
        if parts.scheme and parts.netloc:
            base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        else:
            base = configured_base.rstrip("/")
    else:
        host = (
            request.headers.get("X-Forwarded-Host")
            or request.headers.get("Host")
            or request.host
        )
        proto = request.headers.get("X-Forwarded-Proto") or request.scheme or "https"
        base = f"{proto}://{host}"
    return f"{base.rstrip('/')}/s/{quote(share_token)}"


def _subscription_page_request_headers(request: web.Request) -> Dict[str, str]:
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
