"""Public HTML and raw-subscription representations of a single /s/ URL."""

import asyncio
import hashlib
import time
from collections import deque

from aiohttp import web

from bot.app.web.context import get_settings
from bot.infra.redis import get_redis, redis_key
from bot.services.remnawave_subscription_source import (
    RemnawaveSubscriptionSource,
    SubscriptionTransportError,
)
from bot.services.subscription_delivery import DeliveryRequest, SubscriptionDeliveryService
from bot.utils.request_security import request_client_ip
from config.settings import Settings

from .assets import index_route
from .guides_public import _public_install_url
from .subscription_access import PanelLookupUnavailable, resolve_subscription_access

_CLIENT_UA = (
    "happ",
    "clash",
    "mihomo",
    "sing-box",
    "singbox",
    "v2ray",
    "v2rayn",
    "shadowrocket",
    "stash",
    "streisand",
    "hiddify",
    "nekobox",
    "flclash",
    "koala",
    "prizrak",
    "rabbithole",
)
_PREVIEW_UA = (
    "telegrambot",
    "facebookexternalhit",
    "twitterbot",
    "discordbot",
    "slackbot",
    "whatsapp",
    "googlebot",
    "bingbot",
)
_VARY = "User-Agent, Accept, Sec-Fetch-Mode, Sec-Fetch-Dest"
_LOCAL_BUCKETS_KEY: web.AppKey[dict[str, deque[float]]] = web.AppKey(
    "subscription_gateway_rate_buckets", dict
)
_LOCAL_LOCK_KEY: web.AppKey[asyncio.Lock] = web.AppKey(
    "subscription_gateway_rate_lock", asyncio.Lock
)
_DELIVERY_SEMAPHORE_KEY: web.AppKey[asyncio.Semaphore] = web.AppKey(
    "subscription_gateway_delivery_semaphore", asyncio.Semaphore
)


def _html_accepted(value: str) -> bool:
    for item in value.lower().split(","):
        pieces = [piece.strip() for piece in item.split(";")]
        if pieces[0] != "text/html":
            continue
        quality = next((p[2:] for p in pieces[1:] if p.startswith("q=")), "1")
        try:
            return float(quality) > 0
        except ValueError:
            return False
    return False


def _representation(request: web.Request) -> str:
    views = request.query.getall("view", [])
    if len(views) > 1 or (views and views[0] not in {"page", "subscription"}):
        raise web.HTTPBadRequest
    client_type = request.match_info.get("client_type")
    if client_type and views and views[0] == "page":
        raise web.HTTPBadRequest
    if client_type or (views and views[0] == "subscription"):
        return "subscription"
    if views and views[0] == "page":
        return "page"
    ua = request.headers.get("User-Agent", "").lower()
    if any(marker in ua for marker in _CLIENT_UA):
        return "subscription"
    if any(marker in ua for marker in _PREVIEW_UA):
        return "page"
    if (
        request.headers.get("Sec-Fetch-Mode", "").lower() == "navigate"
        or request.headers.get("Sec-Fetch-Dest", "").lower() == "document"
        or _html_accepted(request.headers.get("Accept", ""))
        or "mozilla/" in ua
    ):
        return "page"
    return "subscription"


def _protect(response: web.Response) -> web.Response:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Vary"] = _VARY
    return response


def _error(status: int) -> web.Response:
    response = web.Response(status=status, body=b"Subscription unavailable")
    if status == 429:
        response.headers["Retry-After"] = "60"
    return _protect(response)


async def _rate_limited(request: web.Request, token: str, client_ip: str) -> bool:
    settings: Settings = get_settings(request)
    token_key = hashlib.sha256(token.encode("ascii")).hexdigest()[:24]
    limits = ((f"ip:{client_ip}", 240), (f"token:{token_key}", 60))
    try:
        redis = await get_redis(settings)
        if redis is not None:
            for key, maximum in limits:
                item = redis_key(settings, "rate-limit", "subscription-gateway", key)
                count = await redis.incr(item)
                if count == 1:
                    await redis.expire(item, 60)
                if count > maximum:
                    return True
            return False
    except Exception:
        pass
    buckets = request.app.setdefault(_LOCAL_BUCKETS_KEY, {})
    lock = request.app.setdefault(_LOCAL_LOCK_KEY, asyncio.Lock())
    now = time.monotonic()
    async with lock:
        for key, maximum in limits:
            bucket = buckets.setdefault(key, deque())
            while bucket and now - bucket[0] >= 60:
                bucket.popleft()
            if len(bucket) >= maximum:
                return True
            bucket.append(now)
        if len(buckets) > 10000:
            for key in list(buckets)[:1000]:
                if not buckets[key] or now - buckets[key][-1] >= 60:
                    buckets.pop(key, None)
    return False


async def subscription_gateway_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    try:
        representation = _representation(request)
    except web.HTTPBadRequest:
        return _error(400)
    token = request.match_info["share_token"]
    if representation == "subscription" and not request.headers.get("User-Agent", "").strip():
        return _error(400)
    client_ip = (
        request_client_ip(request, trusted_proxies=settings.trusted_proxies)
        or request.remote
        or "127.0.0.1"
    )
    if await _rate_limited(request, token, client_ip):
        return _error(429)
    if representation == "subscription" and not settings.SUBSCRIPTION_GATEWAY_ENABLED:
        return _error(503)
    try:
        access = await resolve_subscription_access(request, token)
    except PanelLookupUnavailable:
        return _error(503)
    if access is None:
        return _error(404)
    if representation == "page":
        return _protect(await index_route(request))
    semaphore = request.app.setdefault(_DELIVERY_SEMAPHORE_KEY, asyncio.Semaphore(64))
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=2)
    except TimeoutError:
        return _error(503)
    try:
        service = SubscriptionDeliveryService(RemnawaveSubscriptionSource(settings))
        result = await service.deliver(
            access,
            DeliveryRequest(
                client_type=request.match_info.get("client_type"),
                headers=dict(request.headers),
                client_ip=client_ip,
                is_disconnected=lambda: bool(request.transport and request.transport.is_closing()),
            ),
        )
    except SubscriptionTransportError as exc:
        return _error(exc.status)
    finally:
        semaphore.release()
    headers = dict(result.headers)
    if settings.SUBSCRIPTION_GATEWAY_REWRITE_PROFILE_PAGE_URL:
        page_url = _public_install_url(request, token)
        if page_url:
            headers["profile-web-page-url"] = page_url + "?view=page"
    return _protect(web.Response(status=result.status, body=result.body, headers=headers))
