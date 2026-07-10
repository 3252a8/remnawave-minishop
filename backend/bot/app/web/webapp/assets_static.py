import gzip
import hashlib
import re
import string
import time
from pathlib import Path
from typing import Any

from aiohttp import web

from bot.app.web.context import (
    get_settings,
)
from config.settings import Settings

from .asset_paths import APP_ROOT, ASSET_DIR
from .constants import ROBOTS_TX
from .response_helpers import json_response

_TEXT_FILE_CACHE: dict[tuple[str, bool], tuple[int, int, str]] = {}
_BINARY_FILE_CACHE: dict[str, tuple[int, int, bytes]] = {}
_GZIP_BODY_CACHE: dict[str, bytes] = {}
_ASSET_NAME_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_I18N_PAYLOAD_CACHE: dict[tuple[int, str, tuple[tuple[str, int, int], ...]], dict[str, Any]] = {}
_ASSET_NAME_CACHE_TTL_SECONDS = 30.0
WEBAPP_HTML_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"
WEBAPP_LEGACY_ASSET_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"
PROVIDER_LOGO_MAX_BYTES = 128 * 1024
PROVIDER_LOGO_SOURCE_DIR = APP_ROOT / "frontend" / "public" / "provider-logos"
_PROVIDER_LOGO_NAME_CHARS = frozenset(string.ascii_letters + string.digits + "_-")
_PROVIDER_LOGO_NAME_MAX_LEN = 64


async def health_route(request: web.Request) -> web.Response:
    return json_response({"ok": True})


async def robots_txt_route(request: web.Request) -> web.Response:
    response = web.Response(text=ROBOTS_TX, content_type="text/plain")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


async def provider_logo_asset_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    filename = str(request.match_info.get("filename") or "")
    # Bounded, non-backtracking validation equivalent to r"[A-Za-z0-9_-]+\.png"
    # (also blocks path traversal); avoids running a regex over user input.
    stem = filename[:-4]
    if (
        len(filename) > _PROVIDER_LOGO_NAME_MAX_LEN
        or not filename.endswith(".png")
        or not stem
        or not _PROVIDER_LOGO_NAME_CHARS.issuperset(stem)
    ):
        raise web.HTTPNotFound(text="provider_logo_not_found")

    path = _provider_logo_asset_path(filename)
    try:
        body = _read_template_binary_cached(path)
    except OSError:
        raise web.HTTPNotFound(text="provider_logo_not_found") from None
    if not body or len(body) > PROVIDER_LOGO_MAX_BYTES:
        raise web.HTTPNotFound(text="provider_logo_not_found")

    response = web.Response(body=body, content_type="image/png")
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _provider_logo_asset_path(filename: str) -> Path:
    built_path = ASSET_DIR / "provider-logos" / filename
    if built_path.is_file():
        return built_path
    return PROVIDER_LOGO_SOURCE_DIR / filename


async def css_asset_route(request: web.Request) -> web.Response:
    return await _css_asset_route(request, base_name="subscription_webapp")


async def admin_css_asset_route(request: web.Request) -> web.Response:
    return await _css_asset_route(request, base_name="subscription_webapp_admin")


async def _css_asset_route(request: web.Request, *, base_name: str) -> web.Response:
    asset_hash = request.match_info.get("asset_hash")
    filename = f"{base_name}.{asset_hash}.css" if asset_hash else f"{base_name}.css"
    response = await _serve_template_asset(
        request,
        filename,
        "text/css",
        allow_precompressed=bool(asset_hash),
    )
    response.headers["Cache-Control"] = (
        "public, max-age=31536000, immutable" if asset_hash else WEBAPP_LEGACY_ASSET_CACHE_CONTROL
    )
    return response


async def js_asset_route(request: web.Request) -> web.Response:
    return await _js_asset_route(request, base_name="subscription_webapp")


async def admin_js_asset_route(request: web.Request) -> web.Response:
    return await _js_asset_route(request, base_name="subscription_webapp_admin")


async def admin_js_chunk_asset_route(request: web.Request) -> web.Response:
    chunk_name = request.match_info.get("chunk_name", "")
    asset_hash = request.match_info.get("asset_hash", "")
    filename = f"subscription_webapp_admin.{chunk_name}.{asset_hash}.js"
    response = await _serve_template_asset(
        request,
        filename,
        "application/javascript",
        allow_precompressed=True,
    )
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


async def _js_asset_route(request: web.Request, *, base_name: str) -> web.Response:
    asset_hash = request.match_info.get("asset_hash")
    filename = f"{base_name}.min.{asset_hash}.js" if asset_hash else f"{base_name}.js"
    response = await _serve_template_asset(
        request,
        filename,
        "application/javascript",
        allow_precompressed=bool(asset_hash),
        strip_dev_mock=not asset_hash,
    )
    response.headers["Cache-Control"] = (
        "public, max-age=31536000, immutable" if asset_hash else WEBAPP_LEGACY_ASSET_CACHE_CONTROL
    )
    return response


WEBAPP_BOOTSTRAP_I18N_PREFIXES = ("wa_",)
WEBAPP_BOOTSTRAP_I18N_KEYS = {"menu_support_button", "menu_server_status_button"}
WEBAPP_I18N_SCOPES = {"webapp", "admin"}
APP_DEEPLINK_I18N_KEYS = {
    "title": "wa_app_launch_title",
    "hint": "wa_app_launch_opening_hint",
    "manualHint": "wa_app_launch_hint",
    "button": "wa_app_launch_button",
    "retryButton": "wa_app_launch_retry_button",
    "doneTitle": "wa_app_launch_done_title",
    "doneHint": "wa_app_launch_done_hint",
    "closeButton": "wa_app_launch_close_button",
    "unavailableTitle": "wa_app_launch_unavailable_title",
    "unavailableHint": "wa_app_launch_unavailable_hint",
}
APP_DEEPLINK_I18N_FALLBACKS = {
    "wa_app_launch_title": "Opening app",
    "wa_app_launch_opening_hint": "Opening the app on this device...",
    "wa_app_launch_hint": "If the app did not open automatically, tap the button below.",
    "wa_app_launch_button": "Open app",
    "wa_app_launch_retry_button": "Open again",
    "wa_app_launch_done_title": "Settings added",
    "wa_app_launch_done_hint": "If the app opened, you can close this window.",
    "wa_app_launch_close_button": "Close window",
    "wa_app_launch_unavailable_title": "App link unavailable",
    "wa_app_launch_unavailable_hint": "Return to Telegram and try again.",
}


async def _serve_template_asset(
    request: web.Request,
    filename: str,
    content_type: str,
    *,
    allow_precompressed: bool = False,
    strip_dev_mock: bool = False,
) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    path = ASSET_DIR / filename
    if allow_precompressed:
        compressed = _precompressed_template_asset_response(request, path, content_type)
        if compressed is not None:
            return compressed

    text = _read_template_text_cached(path, strip_dev_mock=strip_dev_mock)
    return web.Response(text=text, content_type=content_type, charset="utf-8")


def _precompressed_template_asset_response(
    request: web.Request,
    path: Path,
    content_type: str,
) -> web.Response | None:
    for encoding, suffix in (("br", ".br"), ("gzip", ".gz")):
        if not _request_accepts_encoding(request, encoding):
            continue
        compressed_path = path.with_name(f"{path.name}{suffix}")
        try:
            body = _read_template_binary_cached(compressed_path)
        except OSError:
            continue
        response = web.Response(body=body, content_type=content_type)
        response.headers["Content-Encoding"] = encoding
        response.headers["Vary"] = "Accept-Encoding"
        return response
    return None


def _request_accepts_encoding(request: web.Request, encoding: str) -> bool:
    headers = getattr(request, "headers", {}) or {}
    value = str(headers.get("Accept-Encoding", ""))
    if not value:
        return False

    expected = encoding.lower()
    for part in value.split(","):
        token, *params = part.strip().split(";")
        token = token.strip().lower()
        if token not in {expected, "*"}:
            continue
        for param in params:
            param = param.strip().lower()
            if not param.startswith("q="):
                continue
            try:
                if float(param[2:].strip()) <= 0:
                    return False
            except ValueError:
                return False
        return True
    return False


def _gzip_body_cached(cache_key: str, body: bytes) -> bytes:
    cached = _GZIP_BODY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    compressed = gzip.compress(body, compresslevel=9, mtime=0)
    _GZIP_BODY_CACHE[cache_key] = compressed
    if len(_GZIP_BODY_CACHE) > 24:
        _GZIP_BODY_CACHE.clear()
        _GZIP_BODY_CACHE[cache_key] = compressed
    return compressed


def _read_template_binary_cached(path: Path) -> bytes:
    stat = path.stat()
    key = str(path.resolve())
    cached = _BINARY_FILE_CACHE.get(key)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]

    body = path.read_bytes()
    _BINARY_FILE_CACHE[key] = (stat.st_mtime_ns, stat.st_size, body)
    if len(_BINARY_FILE_CACHE) > 24:
        _BINARY_FILE_CACHE.clear()
        _BINARY_FILE_CACHE[key] = (stat.st_mtime_ns, stat.st_size, body)
    return body


def _read_template_text_cached(path: Path, *, strip_dev_mock: bool = False) -> str:
    stat = path.stat()
    key = (str(path.resolve()), strip_dev_mock)
    cached = _TEXT_FILE_CACHE.get(key)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]

    text = path.read_text(encoding="utf-8")
    if strip_dev_mock:
        text = _strip_marked_block(
            text,
            "/* WEBAPP_DEV_MOCK_START */",
            "/* WEBAPP_DEV_MOCK_END */",
        )
    _TEXT_FILE_CACHE[key] = (stat.st_mtime_ns, stat.st_size, text)
    if len(_TEXT_FILE_CACHE) > 24:
        _TEXT_FILE_CACHE.clear()
        _TEXT_FILE_CACHE[key] = (stat.st_mtime_ns, stat.st_size, text)
    return text


def _resolve_webapp_js_asset_name() -> str:
    return _resolve_hashed_js_asset_name(
        kind="js",
        base_name="subscription_webapp",
    )


def _resolve_webapp_admin_js_asset_name() -> str:
    # The admin bundle is lazy-loaded from the already running Mini App. It now
    # ships content-hashed alongside the main bundle (same build, deterministic
    # hashes, served immutable), so iOS WebViews fetch fresh admin assets on every
    # deploy. The App.svelte loader falls back to the bare runtime build name if a
    # hashed asset ever 404s.
    return _resolve_hashed_js_asset_name(
        kind="admin-js",
        base_name="subscription_webapp_admin",
    )


def _resolve_hashed_js_asset_name(*, kind: str, base_name: str) -> str:
    cached = _get_cached_asset_name(kind)
    if cached:
        return cached
    minified_assets = []
    pattern = re.compile(rf"{re.escape(base_name)}\.min\.[0-9a-f]{{8}}\.js")
    for path in ASSET_DIR.glob(f"{base_name}.min.*.js"):
        if not pattern.fullmatch(path.name):
            continue
        try:
            minified_assets.append((path.stat().st_mtime, path.name))
        except OSError:
            continue
    if minified_assets:
        minified_assets.sort(reverse=True)
        return _set_cached_asset_name(kind, minified_assets[0][1])
    return _set_cached_asset_name(kind, _stable_asset_name_with_version(f"{base_name}.js"))


def _resolve_webapp_css_asset_name() -> str:
    return _resolve_hashed_css_asset_name(
        kind="css",
        base_name="subscription_webapp",
    )


def _resolve_webapp_admin_css_asset_name() -> str:
    # Content-hashed and immutable, same rationale as the admin JS bundle above.
    return _resolve_hashed_css_asset_name(
        kind="admin-css",
        base_name="subscription_webapp_admin",
    )


def _resolve_hashed_css_asset_name(*, kind: str, base_name: str) -> str:
    cached = _get_cached_asset_name(kind)
    if cached:
        return cached
    hashed_assets = []
    pattern = re.compile(rf"{re.escape(base_name)}\.[0-9a-f]{{8}}\.css")
    for path in ASSET_DIR.glob(f"{base_name}.*.css"):
        if not pattern.fullmatch(path.name):
            continue
        try:
            hashed_assets.append((path.stat().st_mtime, path.name))
        except OSError:
            continue
    if hashed_assets:
        hashed_assets.sort(reverse=True)
        return _set_cached_asset_name(kind, hashed_assets[0][1])
    return _set_cached_asset_name(kind, _stable_asset_name_with_version(f"{base_name}.css"))


def _stable_asset_name_with_version(filename: str) -> str:
    path = ASSET_DIR / filename
    try:
        stat = path.stat()
    except OSError:
        return filename

    raw_version = f"{filename}:{int(stat.st_mtime_ns)}:{int(stat.st_size)}"
    version = hashlib.sha256(raw_version.encode("utf-8")).hexdigest()[:8]
    return f"{filename}?v={version}"


def _get_cached_asset_name(kind: str) -> str | None:
    key = (str(ASSET_DIR.resolve()), kind)
    cached = _ASSET_NAME_CACHE.get(key)
    if not cached:
        return None
    cached_at, filename = cached
    if time.monotonic() - cached_at >= _ASSET_NAME_CACHE_TTL_SECONDS:
        return None
    return filename


def _set_cached_asset_name(kind: str, filename: str) -> str:
    key = (str(ASSET_DIR.resolve()), kind)
    _ASSET_NAME_CACHE[key] = (time.monotonic(), filename)
    return filename


def _strip_marked_block(html: str, start_marker: str, end_marker: str) -> str:
    start = html.find(start_marker)
    if start == -1:
        return html
    end = html.find(end_marker, start)
    if end == -1:
        return html[:start]
    return html[:start] + html[end + len(end_marker) :]
