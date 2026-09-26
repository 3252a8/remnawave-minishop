"""Raw, bounded adapter for Remnawave's public subscription endpoint."""

import asyncio
import re
from urllib.parse import quote, urlsplit, urlunsplit

import aiohttp

from bot.services.subscription_delivery import DeliveryRequest, DeliveryResult
from config.settings import Settings

_SHORT_UUID = re.compile(r"[A-Za-z0-9_-]{6,80}\Z")
_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_REQUEST_BLOCKED = _HOP_HEADERS | {
    "host",
    "authorization",
    "cookie",
    "content-length",
    "content-type",
    "accept",
    "accept-encoding",
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "x-remnawave-real-ip",
    "x-minishop-frontend-host",
}
_RESPONSE_BLOCKED = _HOP_HEADERS | {
    "set-cookie",
    "content-length",
    "content-encoding",
    "server",
    "www-authenticate",
    "proxy-authenticate",
}


class SubscriptionTransportError(Exception):
    def __init__(self, status: int) -> None:
        self.status = status


def panel_subscription_url(api_url: str, short_uuid: str, client_type: str | None) -> str:
    parts = urlsplit(str(api_url or ""))
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or not _SHORT_UUID.fullmatch(short_uuid)
    ):
        raise SubscriptionTransportError(502)
    path = parts.path.rstrip("/")
    if not path.endswith("/api"):
        path += "/api"
    path += "/sub/" + quote(short_uuid, safe="")
    if client_type:
        path += "/" + quote(client_type, safe="")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def filter_client_headers(
    headers: dict[str, str], *, edge_header: str = "X-Minishop-Edge-Token"
) -> dict[str, str]:
    connection = next(
        (value for name, value in headers.items() if name.lower() == "connection"), ""
    )
    connection_tokens = {token.strip().lower() for token in connection.split(",") if token.strip()}
    blocked = _REQUEST_BLOCKED | connection_tokens | {edge_header.lower()}
    result = {
        name: value
        for name, value in headers.items()
        if name.lower() not in blocked
        and not name.lower().startswith(("x-forwarded-", "x-original-", "x-rewrite-"))
        and name.lower() not in {"cf-connecting-ip", "true-client-ip", "x-client-ip"}
        and len(name) <= 128
        and len(value) <= 4096
        and "\r" not in value
        and "\n" not in value
    }
    if sum(len(key) + len(value) for key, value in result.items()) > 16384:
        raise SubscriptionTransportError(400)
    return result


def filter_panel_headers(
    headers: dict[str, str], *, edge_header: str = "X-Minishop-Edge-Token"
) -> dict[str, str]:
    connection = next(
        (value for name, value in headers.items() if name.lower() == "connection"), ""
    )
    connection_tokens = {token.strip().lower() for token in connection.split(",") if token.strip()}
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in _RESPONSE_BLOCKED | connection_tokens
        and name.lower() != edge_header.lower()
        and name.lower() != "location"
        and not name.lower().startswith("x-minishop-edge-")
        and len(name) <= 128
        and len(value) <= 4096
        and "\r" not in value
        and "\n" not in value
    }


class RemnawaveSubscriptionSource:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch(self, binding: object, request: DeliveryRequest) -> DeliveryResult:
        if request.is_disconnected and request.is_disconnected():
            raise asyncio.CancelledError
        short_uuid = str(getattr(binding, "panel_short_uuid", "") or "")
        url = panel_subscription_url(
            str(self.settings.PANEL_API_URL or ""), short_uuid, request.client_type
        )
        headers = filter_client_headers(
            request.headers, edge_header=self.settings.MINISHOP_EDGE_TOKEN_HEADER
        )
        user_agent = request.headers.get("User-Agent", "").strip()
        if not user_agent:
            raise SubscriptionTransportError(400)
        headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "x-remnawave-real-ip": request.client_ip,
            }
        )
        api_cookie = str(self.settings.panel_settings.api_cookie or "").strip()
        if api_cookie:
            headers["Cookie"] = api_cookie
        timeout = aiohttp.ClientTimeout(total=30, connect=8, sock_read=22)
        try:
            async with (
                aiohttp.ClientSession(
                    timeout=timeout,
                    cookie_jar=aiohttp.DummyCookieJar(),
                    auto_decompress=True,
                    trust_env=False,
                ) as session,
                session.get(url, headers=headers, allow_redirects=False) as response,
            ):
                if 300 <= response.status < 400:
                    raise SubscriptionTransportError(502)
                if response.content_length and response.content_length > 8 * 1024 * 1024:
                    raise SubscriptionTransportError(502)
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    if request.is_disconnected and request.is_disconnected():
                        raise asyncio.CancelledError
                    body.extend(chunk)
                    if len(body) > 8 * 1024 * 1024:
                        raise SubscriptionTransportError(502)
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type or bytes(body[:128]).lstrip().lower().startswith(
                    (b"<!doctype html", b"<html")
                ):
                    raise SubscriptionTransportError(502)
                if 200 <= response.status < 300 and not body:
                    raise SubscriptionTransportError(502)
                return DeliveryResult(
                    status=response.status,
                    headers=filter_panel_headers(
                        dict(response.headers), edge_header=self.settings.MINISHOP_EDGE_TOKEN_HEADER
                    ),
                    body=bytes(body),
                )
        except TimeoutError as exc:
            raise SubscriptionTransportError(504) from exc
        except (aiohttp.ClientError, OSError) as exc:
            raise SubscriptionTransportError(502) from exc
