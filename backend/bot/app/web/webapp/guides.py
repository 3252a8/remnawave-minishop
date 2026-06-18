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
    user_id = _require_user_id(request)
    status = await _subscription_guides_status_for_request(request, user_id=user_id)
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

    panel_user_uuid = str(subscription.pop("_panel_user_uuid", "") or "").strip()
    status = await _subscription_guides_status_for_request(
        request,
        panel_short_uuid=subscription.get("panel_short_uuid"),
        panel_user_uuid=panel_user_uuid,
    )
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


async def _subscription_guides_status_for_request(
    request: web.Request,
    *,
    user_id: Optional[int] = None,
    panel_short_uuid: Optional[str] = None,
    panel_user_uuid: Optional[str] = None,
) -> Dict[str, Any]:
    settings: Settings = request.app["settings"]
    if not _subscription_guides_should_try_resolved_panel_config(settings):
        return await _subscription_guides_status_shared(request.app)

    short_uuid = str(panel_short_uuid or "").strip()
    resolved_panel_user_uuid = str(panel_user_uuid or "").strip()
    if not short_uuid and user_id is not None:
        context = await _active_panel_subscription_context_for_user(request, int(user_id))
        short_uuid = str(context.get("panel_short_uuid") or "").strip()
        resolved_panel_user_uuid = str(context.get("panel_user_uuid") or "").strip()

    if short_uuid:
        panel_status = await _subscription_guides_status_from_panel_short_uuid(
            request.app,
            settings,
            short_uuid,
            panel_user_uuid=resolved_panel_user_uuid,
            request_headers=_subscription_page_request_headers(request),
        )
        if panel_status.get("enabled"):
            return panel_status

    return await _subscription_guides_status_shared(request.app)


async def _load_subscription_guides_status(
    app: web.Application,
    settings: Settings,
) -> Dict[str, Any]:
    if not bool(getattr(settings, "SUBSCRIPTION_GUIDES_ENABLED", False)):
        return {"enabled": False, "config": None, "source": None, "error": None}

    if _subscription_guides_admin_json_override_enabled(settings):
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


async def _subscription_guides_status_from_panel_short_uuid(
    app: web.Application,
    settings: Settings,
    short_uuid: str,
    *,
    panel_user_uuid: Optional[str] = None,
    request_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
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
            get_config_by_uuid = getattr(
                panel_service, "get_subscription_page_config_by_uuid", None
            )
            if not callable(get_config_by_uuid):
                raise SubscriptionGuidesConfigError(
                    "Panel service cannot load subscription page config by UUID"
                )
            detail = await get_config_by_uuid(config_uuid)
            if detail is None:
                raise SubscriptionGuidesConfigError(
                    f"Panel subscription page config {config_uuid} is unavailable"
                )
            config = validate_panel_subscription_guides_config(detail)
        else:
            config = validate_panel_subscription_guides_config(
                detail,
                allow_default_when_missing=True,
            )
    except Exception as exc:
        logger.warning(
            "Failed to load resolved subscription guides config from Remnawave Panel: %s",
            exc,
        )
        return {"enabled": False, "config": None, "source": "panel", "error": str(exc)}

    return {"enabled": True, "config": config, "source": "panel", "error": None}


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


async def _active_panel_subscription_context_for_user(
    request: web.Request,
    user_id: int,
) -> Dict[str, str]:
    panel_service = _panel_service_from_app(request.app)
    get_user = getattr(panel_service, "get_user_by_uuid", None)
    if not callable(get_user):
        return {}

    async_session_factory: sessionmaker = request.app["async_session_factory"]
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
            return {"panel_short_uuid": panel_short_uuid, "panel_user_uuid": panel_user_uuid}

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
    }


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


def _panel_service_from_app(app: web.Application) -> Any:
    subscription_service: Optional[SubscriptionService] = app.get("subscription_service")
    panel_service = (
        getattr(subscription_service, "panel_service", None) if subscription_service else None
    )
    return panel_service or app.get("panel_service")


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
    panel_user_uuid: Optional[str],
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


def _looks_like_panel_subscription_page_config(payload: Dict[str, Any]) -> bool:
    return "config" in payload or "viewPosition" in payload or "webpageAllowed" in payload


def _subscription_guides_admin_json_override_enabled(settings: Settings) -> bool:
    admin_json = str(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_JSON", "") or "").strip()
    return bool(
        admin_json
        and bool(getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED", False))
    )


def _subscription_guides_should_try_resolved_panel_config(settings: Settings) -> bool:
    return bool(
        getattr(settings, "SUBSCRIPTION_GUIDES_ENABLED", False)
        and getattr(settings, "SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED", True)
        and not _subscription_guides_admin_json_override_enabled(settings)
    )


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
            request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or request.host
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
