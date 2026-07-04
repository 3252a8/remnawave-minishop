import asyncio
import hmac
import html
import json
import re
import secrets
import subprocess
import time
from collections import deque
from typing import Any, Dict, Optional
from urllib.parse import quote

from aiohttp import web
from aiohttp.typedefs import Handler

from bot.app.web.context import (
    get_bot_username,
    get_i18n,
    get_settings,
    get_webapp_rate_limit_buckets,
    get_webapp_rate_limit_lock,
    get_webapp_settings_cache,
)
from bot.app.web.webapp_auth import verify_webapp_session_token
from bot.infra.redis import get_redis, redis_key
from bot.middlewares.i18n import locale_language_options
from bot.utils.request_security import request_client_ip
from config.settings import Settings
from config.webapp_themes_config import (
    public_theme_payload,
    public_themes_catalog_payload,
    resolve_webapp_theme_selection,
)
from db.dal import subscription_dal

from ._runtime import (
    _APP_VERSION_CACHE,
    APP_DEEPLINK_TEMPLATE_PATH,
    APP_REPOSITORY_URL,
    APP_ROOT,
    DEV_MOCK_END_MARKER,
    DEV_MOCK_START_MARKER,
    TEMPLATE_PATH,
    WEBAPP_CONFIG_PLACEHOLDER,
    WEBAPP_CSRF_COOKIE_NAME,
    WEBAPP_CSRF_EXEMPT_PATHS,
    WEBAPP_CSRF_HEADER_NAME,
    WEBAPP_I18N_PLACEHOLDER,
    WEBAPP_JS_PLACEHOLDER,
    WEBAPP_RATE_LIMIT_MAX_REQUESTS,
    WEBAPP_RATE_LIMIT_WINDOW_SECONDS,
    WEBAPP_SESSION_COOKIE_NAME,
    WEBAPP_STATE_CHANGING_METHODS,
    json_response,
    logger,
)
from .assets_branding import (
    _close_shared_http_session,
    _ensure_shared_http_session,
    _fetch_webapp_logo,
    _get_shared_http_session,
    _hostname_resolves_to_public_address,
    _is_proxyable_webapp_logo_url,
    _load_or_fetch_webapp_logo,
    _read_webapp_logo_from_disk,
    _resolve_webapp_asset_url,
    _resolve_webapp_favicon_url,
    _resolve_webapp_logo_url,
    _uploaded_webapp_logo_filename,
    _uploaded_webapp_logo_response,
    _warm_webapp_logo_cache,
    _webapp_default_brand_file_response,
    _webapp_default_favicon_file_response,
    _webapp_favicon_file_response,
    _webapp_generated_favicon_digest,
    _webapp_logo_cache_key,
    _webapp_logo_disk_paths,
    _webapp_redirectable_favicon_url,
    _webapp_root_favicon_target_filename,
    _write_webapp_logo_to_disk,
    webapp_current_favicon_route,
    webapp_default_logo_route,
    webapp_favicon_route,
    webapp_logo_route,
    webapp_uploaded_logo_route,
)
from .assets_static import (
    _ASSET_NAME_CACHE,
    APP_DEEPLINK_I18N_FALLBACKS,
    APP_DEEPLINK_I18N_KEYS,
    WEBAPP_BOOTSTRAP_I18N_KEYS,
    WEBAPP_BOOTSTRAP_I18N_PREFIXES,
    WEBAPP_I18N_SCOPES,
    _get_cached_asset_name,
    _gzip_body_cached,
    _precompressed_template_asset_response,
    _read_template_binary_cached,
    _read_template_text_cached,
    _request_accepts_encoding,
    _resolve_webapp_admin_css_asset_name,
    _resolve_webapp_admin_js_asset_name,
    _resolve_webapp_css_asset_name,
    _resolve_webapp_js_asset_name,
    _serve_template_asset,
    _set_cached_asset_name,
    _stable_asset_name_with_version,
    _strip_marked_block,
    admin_css_asset_route,
    admin_js_asset_route,
    admin_js_chunk_asset_route,
    css_asset_route,
    health_route,
    js_asset_route,
    robots_txt_route,
)
from .assets_theme import (
    _INITIAL_THEME_LOGO_SCALE_TOKENS,
    _INITIAL_THEME_TOKEN_CSS_MAP,
    _app_deeplink_theme_head_markup,
    _favicon_head_markup,
    _initial_theme_declarations,
    _initial_theme_for_request,
    _initial_theme_head_markup,
    _initial_theme_tokens,
    _normalize_etag_for_compare,
    _not_modified_response,
    _request_etag_matches,
    _safe_theme_asset_relative_path,
    _safe_theme_css_relative_path,
    _safe_theme_relative_path,
    _theme_asset_etag,
    _theme_css_href_for_html,
    _theme_text_response,
    theme_asset_route,
    theme_css_asset_route,
)
from .common import (
    _json_error,
    _normalize_language,
    _resolve_telegram_bot_id,
    _resolve_telegram_oauth_client_id,
    _resolve_telegram_oauth_request_access,
)

_TEXT_FILE_CACHE: Dict[tuple[str, bool], tuple[int, int, str]] = {}
_I18N_PAYLOAD_CACHE: Dict[tuple[int, str, tuple[tuple[str, int, int], ...]], Dict[str, Any]] = {}
_ASSET_NAME_CACHE_TTL_SECONDS = 30.0
WEBAPP_HTML_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"
WEBAPP_LEGACY_ASSET_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"


@web.middleware
async def _security_headers_middleware(
    request: web.Request, handler: Handler
) -> web.StreamResponse:
    request["csp_nonce"] = secrets.token_urlsafe(16)
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
    nonce = request.get("csp_nonce", "")
    response.headers.setdefault(
        "Content-Security-Policy",
        (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://telegram.org; "
            "frame-src https://oauth.telegram.org; "
            "frame-ancestors https://web.telegram.org https://t.me; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "  # noqa: E501
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self' https://oauth.telegram.org; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        ),
    )
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
    response.headers.setdefault(
        "Permissions-Policy",
        (
            "accelerometer=(), autoplay=(), camera=(), display-capture=(), "
            "encrypted-media=(), geolocation=(), gyroscope=(), magnetometer=(), "
            "microphone=(), midi=(), payment=(), usb=()"
        ),
    )
    return response


@web.middleware
async def _csrf_protection_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    settings: Settings = get_settings(request)
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if header.startswith(prefix):
        if verify_webapp_session_token(settings, header[len(prefix) :].strip()):
            return await handler(request)

    if (
        request.method in WEBAPP_STATE_CHANGING_METHODS
        and request.path not in WEBAPP_CSRF_EXEMPT_PATHS
        and request.cookies.get(WEBAPP_SESSION_COOKIE_NAME)
    ):
        csrf_cookie = request.cookies.get(WEBAPP_CSRF_COOKIE_NAME, "")
        csrf_header = request.headers.get(WEBAPP_CSRF_HEADER_NAME, "")
        if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_header, csrf_cookie):
            return _json_error(403, "csrf_failed", "Invalid CSRF token")

    return await handler(request)


def _get_cached_webapp_settings(request: web.Request) -> Dict[str, Any]:
    settings: Settings = get_settings(request)
    cache = get_webapp_settings_cache(request)
    now = time.monotonic()
    if now - float(cache.get("ts", 0.0)) >= 60 or not cache.get("data"):
        logo_url = _resolve_webapp_logo_url(settings)
        payment_settings = settings.payment_settings
        support_settings = settings.support_settings
        cache["data"] = {
            "logo_url": logo_url,
            "favicon_url": _resolve_webapp_favicon_url(settings, logo_url),
            "subscription_options": payment_settings.subscription_options,
            "stars_subscription_options": payment_settings.stars_subscription_options,
            "traffic_packages": payment_settings.traffic_packages,
            "stars_traffic_packages": payment_settings.stars_traffic_packages,
            "support_url": support_settings.link or "",
            "server_status_url": settings.SERVER_STATUS_URL or "",
            "privacy_policy_url": settings.PRIVACY_POLICY_URL or "",
            "user_agreement_url": settings.USER_AGREEMENT_URL or "",
            "currency": payment_settings.default_currency_symbol or "CNY",
            "email_auth_enabled": settings.email_auth_configured,
            "registration_invite_only_enabled": bool(
                settings.registration_settings.invite_only_enabled
            ),
            "language": _normalize_language(settings.DEFAULT_LANGUAGE),
        }
        cache["ts"] = now
    return cache["data"]


def _resolve_app_version() -> str:
    # Single source of truth shared with the telemetry worker so the admin
    # sidebar and the install beacon always report the same version.
    from bot.utils import app_version as app_version_module

    global _APP_VERSION_CACHE

    app_version_module.APP_ROOT = APP_ROOT
    app_version_module._run_git_command = _run_git_command
    app_version_module._APP_VERSION_CACHE = _APP_VERSION_CACHE
    version = app_version_module.resolve_app_version()
    _APP_VERSION_CACHE = app_version_module._APP_VERSION_CACHE
    return version


def _run_git_command(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=APP_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


async def _enforce_webapp_rate_limit(
    request: web.Request,
    *,
    user_id: int,
    action: str,
) -> Optional[web.Response]:
    settings: Settings = get_settings(request)
    ip_address = (
        request_client_ip(request, trusted_proxies=settings.trusted_proxies)
        or request.remote
        or "unknown"
    )
    key = f"{action}:{ip_address}:{int(user_id)}"
    try:
        redis = await get_redis(settings)
        if redis is not None:
            redis_rate_key = redis_key(settings, "rate-limit", "webapp", key)
            current = await redis.incr(redis_rate_key)
            if current == 1:
                await redis.expire(redis_rate_key, settings.WEBAPP_RATE_LIMIT_TTL_SECONDS)
            if current > settings.WEBAPP_RATE_LIMIT_MAX_REQUESTS:
                ttl = await redis.ttl(redis_rate_key)
                retry_after = max(
                    1, int(ttl if ttl and ttl > 0 else WEBAPP_RATE_LIMIT_WINDOW_SECONDS)
                )
                return json_response(
                    {
                        "ok": False,
                        "error": "rate_limited",
                        "retry_after": retry_after,
                    },
                    status=429,
                    headers={"Retry-After": str(retry_after)},
                )
            return None
    except Exception as exc:
        logger.warning("Redis webapp rate limiter unavailable; using local fallback: %s", exc)

    buckets: Dict[str, deque[float]] = get_webapp_rate_limit_buckets(request)
    lock: asyncio.Lock = get_webapp_rate_limit_lock(request)
    now = time.monotonic()

    async with lock:
        bucket = buckets.setdefault(key, deque())
        while bucket and now - bucket[0] >= WEBAPP_RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if not bucket:
            buckets.pop(key, None)
            bucket = buckets.setdefault(key, deque())
        if len(bucket) >= WEBAPP_RATE_LIMIT_MAX_REQUESTS:
            retry_after = (
                max(
                    1,
                    int(WEBAPP_RATE_LIMIT_WINDOW_SECONDS - (now - bucket[0])),
                )
                if bucket
                else WEBAPP_RATE_LIMIT_WINDOW_SECONDS
            )
            return json_response(
                {
                    "ok": False,
                    "error": "rate_limited",
                    "retry_after": retry_after,
                },
                status=429,
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)

    return None


def _is_webapp_bootstrap_i18n_key(key: str) -> bool:
    return key in WEBAPP_BOOTSTRAP_I18N_KEYS or key.startswith(WEBAPP_BOOTSTRAP_I18N_PREFIXES)


def _normalize_i18n_scope(raw_scope: object) -> str:
    scope = str(raw_scope or "webapp").strip().lower()
    return scope if scope in WEBAPP_I18N_SCOPES else "webapp"


def _i18n_cache_fingerprint(
    locales_data: Dict[str, Any],
) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        sorted(
            (str(lang), id(messages), len(messages))
            for lang, messages in locales_data.items()
            if isinstance(messages, dict)
        )
    )


def _filter_webapp_i18n_payload(locales_data: object, scope: str = "webapp") -> Dict[str, Any]:
    if not isinstance(locales_data, dict):
        return {}

    normalized_scope = _normalize_i18n_scope(scope)
    cache_key = (id(locales_data), normalized_scope, _i18n_cache_fingerprint(locales_data))
    cached = _I18N_PAYLOAD_CACHE.get(cache_key)
    if cached is not None:
        return cached

    payload: Dict[str, Any] = {}
    for lang, messages in locales_data.items():
        if not isinstance(messages, dict):
            continue
        filtered: Dict[str, Any] = {}
        for key, value in messages.items():
            key_text = str(key)
            is_bootstrap_key = _is_webapp_bootstrap_i18n_key(key_text)
            if (normalized_scope == "webapp" and is_bootstrap_key) or (
                normalized_scope == "admin" and not is_bootstrap_key
            ):
                filtered[key_text] = value
        payload[str(lang)] = filtered
    if len(_I18N_PAYLOAD_CACHE) > 32:
        _I18N_PAYLOAD_CACHE.clear()
    _I18N_PAYLOAD_CACHE[cache_key] = payload
    return payload


def _build_webapp_bootstrap_payload(request: web.Request) -> Dict[str, Any]:
    settings: Settings = get_settings(request)
    cached = _get_cached_webapp_settings(request)
    webapp_settings = settings.webapp_settings
    themes_catalog = settings.webapp_themes_catalog
    primary_color = webapp_settings.primary_color or "#00fe7a"
    preview_key = str(request.query.get("theme_preview") or "").strip()
    preview_theme = (
        resolve_webapp_theme_selection(themes_catalog, preview_key) if preview_key else None
    )
    if preview_theme is None or not preview_theme.enabled:
        preview_key = ""
    elif preview_key == "light":
        preview_key = preview_theme.key
    themes_payload = public_themes_catalog_payload(
        themes_catalog,
        primary_color,
        enabled_only=True,
    )
    if preview_theme is not None and preview_key:
        preview_payload = public_theme_payload(preview_theme, primary_color)
        payload_themes = themes_payload.get("themes")
        if isinstance(payload_themes, list):
            replaced = False
            for idx, theme_payload in enumerate(payload_themes):
                if (
                    isinstance(theme_payload, dict)
                    and theme_payload.get("key") == preview_theme.key
                ):
                    payload_themes[idx] = preview_payload
                    replaced = True
                    break
            if not replaced:
                payload_themes.insert(0, preview_payload)
    i18n_instance: Optional[object] = get_i18n(request)
    i18n_scope = _normalize_i18n_scope(request.query.get("i18n_scope") or "webapp")
    if i18n_instance and hasattr(i18n_instance, "reload_overrides_from_file"):
        i18n_instance.reload_overrides_from_file()
    locales_data = getattr(i18n_instance, "locales_data", {}) if i18n_instance else {}
    base_locales_data = getattr(i18n_instance, "base_locales_data", {}) if i18n_instance else {}
    return {
        "config": {
            "title": webapp_settings.title,
            "primaryColor": webapp_settings.primary_color,
            "homeBrandVisible": bool(webapp_settings.home_brand_visible),
            "tariffChangeVisible": bool(webapp_settings.tariff_change_visible),
            "themesCatalog": themes_payload,
            "themesDir": settings.WEBAPP_THEMES_DIR,
            "themePreviewKey": preview_key,
            "logoUrl": cached["logo_url"],
            "faviconUrl": cached["favicon_url"],
            "faviconUseCustom": bool(webapp_settings.favicon_use_custom),
            "apiBase": "/api",
            "adminJsAsset": f"/{_resolve_webapp_admin_js_asset_name()}",
            "adminCssAsset": f"/{_resolve_webapp_admin_css_asset_name()}",
            "telegramLoginBotUsername": get_bot_username(request),
            "telegramLoginBotId": _resolve_telegram_bot_id(settings.BOT_TOKEN) or 0,
            "telegramOAuthClientId": _resolve_telegram_oauth_client_id(settings) or 0,
            "telegramOAuthRequestAccess": _resolve_telegram_oauth_request_access(settings),
            "supportUrl": cached["support_url"],
            "serverStatusUrl": cached["server_status_url"],
            "privacyPolicyUrl": cached["privacy_policy_url"],
            "userAgreementUrl": cached["user_agreement_url"],
            "currency": cached["currency"],
            "language": cached["language"],
            "languages": locale_language_options(
                locales_data.keys(),
                base_languages=base_locales_data.keys(),
            ),
            "emailAuthEnabled": cached["email_auth_enabled"],
            "registrationInviteOnlyEnabled": cached["registration_invite_only_enabled"],
            "appVersion": _resolve_app_version(),
            "appRepositoryUrl": APP_REPOSITORY_URL,
        },
        "i18n": _filter_webapp_i18n_payload(locales_data, i18n_scope),
    }


async def bootstrap_route(request: web.Request) -> web.Response:
    response = json_response({"ok": True, **_build_webapp_bootstrap_payload(request)})
    response.headers["Cache-Control"] = "no-cache"
    return response


async def i18n_route(request: web.Request) -> web.Response:
    i18n_instance: Optional[object] = get_i18n(request)
    if i18n_instance and hasattr(i18n_instance, "reload_overrides_from_file"):
        i18n_instance.reload_overrides_from_file()
    scope = _normalize_i18n_scope(request.query.get("scope") or "webapp")
    locales_data = getattr(i18n_instance, "locales_data", {}) if i18n_instance else {}
    response = json_response(
        {
            "ok": True,
            "scope": scope,
            "i18n": _filter_webapp_i18n_payload(locales_data, scope),
        }
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


def _webapp_page_title(settings: Settings, suffix: str = "") -> str:
    base = str(settings.WEBAPP_TITLE or "").strip() or "Subscription"
    suffix = str(suffix or "").strip()
    return f"{base} - {suffix}" if suffix else base


def _webapp_preview_meta_markup(page_title: str) -> str:
    escaped_title = html.escape(str(page_title or ""), quote=True)
    return "\n".join(
        [
            f'<meta name="application-name" content="{escaped_title}">',
            f'<meta name="apple-mobile-web-app-title" content="{escaped_title}">',
            f'<meta property="og:title" content="{escaped_title}">',
            '<meta property="og:type" content="website">',
            f'<meta property="og:site_name" content="{escaped_title}">',
            '<meta name="twitter:card" content="summary">',
            f'<meta name="twitter:title" content="{escaped_title}">',
        ]
    )


def _replace_webapp_title(html_text: str, page_title: str) -> str:
    escaped_title = html.escape(str(page_title or ""), quote=False)
    next_title = f"<title>{escaped_title}</title>"
    replaced = re.sub(
        r"<title\b[^>]*>.*?</title>",
        next_title,
        html_text,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if replaced != html_text:
        return replaced
    return html_text.replace("</head>", f"{next_title}\n</head>", 1)


def _replace_webapp_favicon(html_text: str, favicon_markup: str) -> str:
    markup = str(favicon_markup or "").strip()
    if not markup:
        return html_text
    replaced = re.sub(
        r"<link\b(?=[^>]*\bid=[\"']app-favicon[\"'])[^>]*>",
        markup,
        html_text,
        count=1,
        flags=re.IGNORECASE,
    )
    if replaced != html_text:
        return replaced
    return html_text.replace("</head>", f"{markup}\n</head>", 1)


def _apply_webapp_head_metadata(html_text: str, page_title: str, favicon_url: str = "") -> str:
    html_text = _replace_webapp_title(html_text, page_title)
    if 'property="og:title"' not in html_text and "property='og:title'" not in html_text:
        meta_markup = _webapp_preview_meta_markup(page_title)
        html_text = re.sub(
            r"(<title\b[^>]*>.*?</title>)",
            lambda match: f"{match.group(1)}\n{meta_markup}",
            html_text,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return _replace_webapp_favicon(html_text, _favicon_head_markup(favicon_url))


def _webapp_shell_preload_markup(js_asset_name: str, share_token: str = "") -> str:
    js_href = "/" + quote(str(js_asset_name or "").lstrip("/"), safe="/.-_")
    lines = [f'<link rel="preload" href="{js_href}" as="script">']
    normalized_share_token = subscription_dal.normalize_install_share_token(share_token)
    if normalized_share_token:
        fetch_href = f"/api/subscription-guides/public/{quote(normalized_share_token, safe='')}"
        lines.append(
            f'<link rel="preload" href="{fetch_href}" as="fetch" '
            'crossorigin="use-credentials" fetchpriority="high">'
        )
    return "\n".join(lines)


async def index_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    html = _read_template_text_cached(TEMPLATE_PATH)
    cached = _get_cached_webapp_settings(request)
    themes_catalog = settings.webapp_themes_catalog
    primary_color = settings.WEBAPP_PRIMARY_COLOR or "#00fe7a"
    initial_theme = _initial_theme_for_request(request, themes_catalog)
    bootstrap = _build_webapp_bootstrap_payload(request)
    config = bootstrap["config"]
    html = _strip_marked_block(html, DEV_MOCK_START_MARKER, DEV_MOCK_END_MARKER)
    css_asset_name = _resolve_webapp_css_asset_name()
    js_asset_name = _resolve_webapp_js_asset_name()
    html = html.replace(
        'href="/subscription_webapp.css"',
        f'href="/{css_asset_name}"',
        1,
    )
    preload_markup = _webapp_shell_preload_markup(
        js_asset_name,
        str(getattr(request, "match_info", {}).get("share_token") or ""),
    )
    if preload_markup:
        html = html.replace("</head>", f"{preload_markup}\n</head>", 1)
    initial_theme_markup = _initial_theme_head_markup(request, initial_theme, primary_color)
    if initial_theme_markup:
        html = html.replace("</head>", f"{initial_theme_markup}\n</head>", 1)
    html = _apply_webapp_head_metadata(html, _webapp_page_title(settings), cached["favicon_url"])
    i18n_payload = bootstrap["i18n"]
    nonce = request.get("csp_nonce", "")
    html = html.replace(
        WEBAPP_CONFIG_PLACEHOLDER,
        (
            f'<script id="webapp-config" type="application/json" nonce="{nonce}">'
            + json.dumps(config, ensure_ascii=False, separators=(",", ":"))
            + "</script>"
        ),
    )
    html = html.replace(
        WEBAPP_I18N_PLACEHOLDER,
        (
            f'<script id="i18n" type="application/json" nonce="{nonce}">'
            + json.dumps(i18n_payload, ensure_ascii=False, separators=(",", ":"))
            + "</script>"
        ),
    )
    html = html.replace(
        WEBAPP_JS_PLACEHOLDER,
        f'<script src="/{js_asset_name}" defer></script>',
    )
    brand_asset_url = cached["logo_url"]
    if brand_asset_url:
        html = html.replace(
            "</head>",
            (
                f'<link rel="preload" href="{brand_asset_url}" '
                'as="image" fetchpriority="high">\n</head>'
            ),
            1,
        )
    response = web.Response(text=html, content_type="text/html", charset="utf-8")
    response.headers["Cache-Control"] = WEBAPP_HTML_CACHE_CONTROL
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


async def app_deeplink_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    nonce = html.escape(str(request.get("csp_nonce", "")), quote=True)
    query = getattr(request, "query", {}) or {}
    themes_catalog = settings.webapp_themes_catalog
    primary_color = settings.WEBAPP_PRIMARY_COLOR or "#00fe7a"
    initial_theme = (
        _initial_theme_for_request(request, themes_catalog) if themes_catalog is not None else None
    )
    lang = _normalize_language(query.get("lang") or settings.DEFAULT_LANGUAGE)
    messages = _app_deeplink_i18n_payload(request, lang)
    page_title = _webapp_page_title(settings, messages["title"])
    messages_json = json.dumps(
        messages,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    favicon_url = _resolve_webapp_favicon_url(settings, _resolve_webapp_logo_url(settings))
    html_text = (
        _read_template_text_cached(APP_DEEPLINK_TEMPLATE_PATH)
        .replace("__LANG__", html.escape(lang, quote=True))
        .replace("__PAGE_TITLE__", html.escape(page_title, quote=False))
        .replace("__NONCE__", nonce)
        .replace("__MESSAGES_JSON__", messages_json)
    )
    initial_theme_markup = _app_deeplink_theme_head_markup(
        request,
        initial_theme,
        themes_catalog,
        primary_color,
    )
    if initial_theme_markup:
        html_text = html_text.replace("</head>", f"{initial_theme_markup}\n</head>", 1)
    html_text = _apply_webapp_head_metadata(html_text, page_title, favicon_url)
    response = web.Response(text=html_text, content_type="text/html", charset="utf-8")
    response.headers["Cache-Control"] = "no-store"
    return response


def _app_deeplink_i18n_payload(request: web.Request, lang: str) -> Dict[str, str]:
    i18n_instance: Optional[object] = get_i18n(request)
    gettext = getattr(i18n_instance, "gettext", None)
    payload: Dict[str, str] = {}
    for payload_key, i18n_key in APP_DEEPLINK_I18N_KEYS.items():
        fallback = APP_DEEPLINK_I18N_FALLBACKS[i18n_key]
        value = ""
        if callable(gettext):
            try:
                value = str(gettext(lang, i18n_key) or "")
            except Exception as exc:
                logger.debug("Failed to resolve open-app i18n key %s: %s", i18n_key, exc)
        payload[payload_key] = value if value and value != i18n_key else fallback
    return payload


__all__ = [
    "_ASSET_NAME_CACHE",
    "_INITIAL_THEME_LOGO_SCALE_TOKENS",
    "_INITIAL_THEME_TOKEN_CSS_MAP",
    "_app_deeplink_theme_head_markup",
    "_close_shared_http_session",
    "_csrf_protection_middleware",
    "_enforce_webapp_rate_limit",
    "_ensure_shared_http_session",
    "_favicon_head_markup",
    "_fetch_webapp_logo",
    "_get_cached_asset_name",
    "_get_cached_webapp_settings",
    "_get_shared_http_session",
    "_gzip_body_cached",
    "_hostname_resolves_to_public_address",
    "_initial_theme_declarations",
    "_initial_theme_for_request",
    "_initial_theme_head_markup",
    "_initial_theme_tokens",
    "_is_proxyable_webapp_logo_url",
    "_load_or_fetch_webapp_logo",
    "_normalize_etag_for_compare",
    "_not_modified_response",
    "_precompressed_template_asset_response",
    "_read_template_binary_cached",
    "_read_template_text_cached",
    "_read_webapp_logo_from_disk",
    "_request_accepts_encoding",
    "_request_etag_matches",
    "_resolve_app_version",
    "_resolve_webapp_admin_css_asset_name",
    "_resolve_webapp_admin_js_asset_name",
    "_resolve_webapp_asset_url",
    "_resolve_webapp_css_asset_name",
    "_resolve_webapp_favicon_url",
    "_resolve_webapp_js_asset_name",
    "_resolve_webapp_logo_url",
    "_safe_theme_asset_relative_path",
    "_safe_theme_css_relative_path",
    "_safe_theme_relative_path",
    "_security_headers_middleware",
    "_serve_template_asset",
    "_set_cached_asset_name",
    "_stable_asset_name_with_version",
    "_strip_marked_block",
    "_theme_asset_etag",
    "_theme_css_href_for_html",
    "_theme_text_response",
    "_uploaded_webapp_logo_filename",
    "_uploaded_webapp_logo_response",
    "_warm_webapp_logo_cache",
    "_webapp_default_brand_file_response",
    "_webapp_default_favicon_file_response",
    "_webapp_favicon_file_response",
    "_webapp_generated_favicon_digest",
    "_webapp_logo_cache_key",
    "_webapp_logo_disk_paths",
    "_webapp_redirectable_favicon_url",
    "_webapp_root_favicon_target_filename",
    "_webapp_shell_preload_markup",
    "_write_webapp_logo_to_disk",
    "admin_css_asset_route",
    "admin_js_asset_route",
    "admin_js_chunk_asset_route",
    "app_deeplink_route",
    "bootstrap_route",
    "css_asset_route",
    "health_route",
    "i18n_route",
    "index_route",
    "js_asset_route",
    "robots_txt_route",
    "theme_asset_route",
    "theme_css_asset_route",
    "webapp_current_favicon_route",
    "webapp_default_logo_route",
    "webapp_favicon_route",
    "webapp_logo_route",
    "webapp_uploaded_logo_route",
]
