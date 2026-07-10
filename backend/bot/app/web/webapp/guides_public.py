"""Public (share-token) subscription payload for the install guides page.

Split out of ``guides.py`` (which re-exports the shared surface).
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_or_create_subscription_guides_public_subscription_cache,
    get_or_create_subscription_guides_public_subscription_lock,
    get_session_factory,
    get_settings,
)
from bot.services.panel_activity import record_subscription_panel_activity
from bot.utils.config_link import prepare_config_links
from config.settings import Settings
from db.dal import subscription_dal

from .guides_panel_config import (
    SUBSCRIPTION_GUIDES_RESOLVED_CACHE_MAX_ITEMS,
    _panel_service_from_app,
    _panel_short_uuid_from_user,
)

SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS = 300


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
            async with async_session_factory() as session:
                if await record_subscription_panel_activity(session, local_sub, panel_user):
                    await session.commit()
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
