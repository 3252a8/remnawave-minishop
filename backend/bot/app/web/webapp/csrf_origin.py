"""Browser-origin checks also protect requests which establish a session."""

from urllib.parse import urlsplit

from aiohttp import web

from config.settings import Settings

from .auth_common import _public_webapp_base_url


def _origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            return None
        return (
            parsed.scheme,
            parsed.hostname.lower(),
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


def browser_origin_allowed(request: web.Request, settings: Settings) -> bool:
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    if origin is not None or referer is not None:
        expected = _origin(_public_webapp_base_url(settings, request))
        return (
            expected is not None
            and _origin(origin if origin is not None else referer or "") == expected
        )
    return request.headers.get("Sec-Fetch-Site", "") not in {"cross-site", "same-site"}


def browser_origin_present(request: web.Request) -> bool:
    return bool(
        request.headers.get("Origin")
        or request.headers.get("Referer")
        or request.headers.get("Sec-Fetch-Site") == "same-origin"
    )
