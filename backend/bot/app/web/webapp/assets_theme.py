from bot.app.web.context import (
    get_settings,
)
from config.webapp_themes_config import (
    default_webapp_theme_asset_file,
    default_webapp_theme_css_files,
    effective_webapp_theme_accent,
    effective_webapp_theme_tokens,
    ensure_default_webapp_theme_descriptor_files,
    public_theme_payload,
    resolve_webapp_theme_selection,
)

from ._runtime import (
    WEBAPP_FAVICON_PATH,
    WEBAPP_THEME_ASSET_CONTENT_TYPES,
    WEBAPP_THEME_ASSET_MAX_BYTES,
    WEBAPP_THEME_CSS_MAX_BYTES,
    Any,
    Dict,
    List,
    Optional,
    Path,
    Settings,
    hashlib,
    html,
    quote,
    re,
    web,
)
from .assets_static import _gzip_body_cached, _request_accepts_encoding

_TEXT_FILE_CACHE: Dict[tuple[str, bool], tuple[int, int, str]] = {}
_BINARY_FILE_CACHE: Dict[str, tuple[int, int, bytes]] = {}
_GZIP_BODY_CACHE: Dict[str, bytes] = {}
_ASSET_NAME_CACHE: Dict[tuple[str, str], tuple[float, str]] = {}
_I18N_PAYLOAD_CACHE: Dict[tuple[int, str, tuple[tuple[str, int, int], ...]], Dict[str, Any]] = {}
_ASSET_NAME_CACHE_TTL_SECONDS = 30.0
WEBAPP_HTML_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"
WEBAPP_LEGACY_ASSET_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"


def _safe_theme_css_relative_path(raw_path: str) -> Optional[Path]:
    return _safe_theme_relative_path(raw_path, allowed_suffixes={".css"}, max_length=180)


def _safe_theme_asset_relative_path(raw_path: str) -> Optional[Path]:
    return _safe_theme_relative_path(
        raw_path,
        allowed_suffixes=set(WEBAPP_THEME_ASSET_CONTENT_TYPES),
        max_length=220,
    )


def _safe_theme_relative_path(
    raw_path: str,
    *,
    allowed_suffixes: set[str],
    max_length: int,
) -> Optional[Path]:
    value = str(raw_path or "").replace("\\", "/").strip().lstrip("/")
    if not value or len(value) > max_length or "\x00" in value:
        return None
    parts = [part for part in value.split("/") if part]
    if len(parts) < 2 or any(part in {".", ".."} for part in parts):
        return None
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part) for part in parts):
        return None
    rel_path = Path(*parts)
    if rel_path.suffix.lower() not in allowed_suffixes:
        return None
    return rel_path


async def theme_css_asset_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    ensure_default_webapp_theme_descriptor_files(settings.WEBAPP_THEMES_DIR)
    rel_path = _safe_theme_css_relative_path(request.match_info.get("path") or "")
    if rel_path is None:
        raise web.HTTPNotFound(text="theme_css_not_found")

    root = Path(settings.WEBAPP_THEMES_DIR).expanduser().resolve()
    path = (root / rel_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise web.HTTPNotFound(text="theme_css_not_found") from None

    query = getattr(request, "query", {}) or {}
    cache_control = "public, max-age=31536000, immutable" if query.get("v") else "no-cache"
    try:
        stat = path.stat()
        if stat.st_size > WEBAPP_THEME_CSS_MAX_BYTES:
            raise web.HTTPNotFound(text="theme_css_too_large")
        etag = _theme_asset_etag(
            "theme-css",
            rel_path,
            stat_mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
        )
        if _request_etag_matches(request, etag):
            return _not_modified_response(
                cache_control=cache_control,
                etag=etag,
                vary="Accept-Encoding",
            )
        text = path.read_text(encoding="utf-8")
    except OSError:
        defaults = default_webapp_theme_css_files()
        text = defaults.get(rel_path.as_posix())
        if text is None:
            raise web.HTTPNotFound(text="theme_css_not_found") from None
        etag = _theme_asset_etag(
            "theme-css",
            rel_path,
            body=text.encode("utf-8"),
        )
        if _request_etag_matches(request, etag):
            return _not_modified_response(
                cache_control=cache_control,
                etag=etag,
                vary="Accept-Encoding",
            )

    return _theme_text_response(
        request,
        text,
        content_type="text/css",
        cache_control=cache_control,
        etag=etag,
    )


async def theme_asset_route(request: web.Request) -> web.Response:
    settings: Settings = get_settings(request)
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    ensure_default_webapp_theme_descriptor_files(settings.WEBAPP_THEMES_DIR)
    rel_path = _safe_theme_asset_relative_path(request.match_info.get("path") or "")
    if rel_path is None:
        raise web.HTTPNotFound(text="theme_asset_not_found")

    root = Path(settings.WEBAPP_THEMES_DIR).expanduser().resolve()
    path = (root / rel_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise web.HTTPNotFound(text="theme_asset_not_found") from None

    suffix = rel_path.suffix.lower()
    content_type = WEBAPP_THEME_ASSET_CONTENT_TYPES.get(suffix)
    if not content_type:
        raise web.HTTPNotFound(text="theme_asset_not_found")

    query = getattr(request, "query", {})
    cache_control = (
        "public, max-age=31536000, immutable" if query.get("v") else "public, max-age=3600"
    )

    try:
        stat = path.stat()
        if stat.st_size > WEBAPP_THEME_ASSET_MAX_BYTES:
            raise web.HTTPNotFound(text="theme_asset_too_large")
        etag = _theme_asset_etag(
            "theme-asset",
            rel_path,
            stat_mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
        )
        if _request_etag_matches(request, etag):
            return _not_modified_response(cache_control=cache_control, etag=etag)
        body = path.read_bytes()
    except OSError:
        fallback = default_webapp_theme_asset_file(rel_path)
        if fallback is None:
            raise web.HTTPNotFound(text="theme_asset_not_found") from None
        body, fallback_suffix = fallback
        content_type = WEBAPP_THEME_ASSET_CONTENT_TYPES.get(fallback_suffix, content_type)
        etag = _theme_asset_etag("theme-asset", rel_path, body=body)
        if _request_etag_matches(request, etag):
            return _not_modified_response(cache_control=cache_control, etag=etag)

    if not body or len(body) > WEBAPP_THEME_ASSET_MAX_BYTES:
        raise web.HTTPNotFound(text="theme_asset_not_found")

    response = web.Response(body=body, content_type=content_type)
    response.headers["Cache-Control"] = cache_control
    response.headers["ETag"] = etag
    return response


def _request_etag_matches(request: web.Request, etag: str) -> bool:
    headers = getattr(request, "headers", {}) or {}
    value = str(headers.get("If-None-Match", ""))
    if not value:
        return False
    if value.strip() == "*":
        return True

    expected = _normalize_etag_for_compare(etag)
    return any(_normalize_etag_for_compare(part.strip()) == expected for part in value.split(","))


def _normalize_etag_for_compare(value: str) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("w/"):
        text = text[2:].strip()
    return text


def _theme_asset_etag(
    kind: str,
    rel_path: Path,
    *,
    stat_mtime_ns: int = 0,
    size: int = 0,
    body: bytes = b"",
) -> str:
    if body:
        digest = hashlib.sha256(
            b"\0".join(
                [
                    kind.encode("utf-8"),
                    rel_path.as_posix().encode("utf-8"),
                    body,
                ]
            )
        ).hexdigest()[:16]
    else:
        raw = f"{kind}:{rel_path.as_posix()}:{int(stat_mtime_ns)}:{int(size)}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f'W/"{digest}"'


def _not_modified_response(
    *,
    cache_control: str,
    etag: str,
    vary: Optional[str] = None,
) -> web.Response:
    response = web.Response(status=304)
    response.headers["Cache-Control"] = cache_control
    response.headers["ETag"] = etag
    if vary:
        response.headers["Vary"] = vary
    return response


def _theme_text_response(
    request: web.Request,
    text: str,
    *,
    content_type: str,
    cache_control: str,
    etag: str,
) -> web.Response:
    body = text.encode("utf-8")
    if _request_accepts_encoding(request, "gzip"):
        response = web.Response(
            body=_gzip_body_cached(etag, body),
            content_type=content_type,
            charset="utf-8",
        )
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Vary"] = "Accept-Encoding"
    else:
        response = web.Response(text=text, content_type=content_type, charset="utf-8")
    response.headers["Cache-Control"] = cache_control
    response.headers["ETag"] = etag
    return response


_INITIAL_THEME_TOKEN_CSS_MAP = {
    "accent": "--accent",
    "bg": "--bg",
    "panel": "--panel",
    "panel_2": "--panel-2",
    "panel_3": "--panel-3",
    "border": "--border",
    "border_strong": "--border-strong",
    "text": "--text",
    "muted": "--muted",
    "dim": "--dim",
    "danger": "--danger",
    "danger_text": "--danger-text",
    "danger_soft": "--danger-soft",
    "danger_border": "--danger-border",
    "success": "--success",
    "success_text": "--success-text",
    "success_soft": "--success-soft",
    "success_border": "--success-border",
    "warning": "--warning",
    "warning_text": "--warning-text",
    "warning_soft": "--warning-soft",
    "warning_border": "--warning-border",
    "info": "--info",
    "info_text": "--info-text",
    "info_soft": "--info-soft",
    "info_border": "--info-border",
    "blue": "--blue",
    "radius": "--radius",
    "accent_contrast": "--accent-contrast",
    "surface_sheen": "--surface-sheen",
    "surface_sheen_soft": "--surface-sheen-soft",
    "surface_hover": "--surface-hover",
    "surface_muted": "--surface-muted",
    "surface_subtle": "--surface-subtle",
    "surface_subtle_border": "--surface-subtle-border",
    "overlay_scrim": "--overlay-scrim",
    "nav_bg": "--nav-bg",
    "rail_bg": "--rail-bg",
    "shadow_soft": "--shadow-soft",
    "shadow_strong": "--shadow-strong",
    "shadow_popover": "--shadow-popover",
    "inset_highlight": "--inset-highlight",
    "font_sans": "--font-sans",
    "font_logo": "--font-logo",
    "font_mono": "--font-mono",
    "home_logo_scale": "--home-logo-scale",
    "home_logo_scale_desktop": "--home-logo-scale-desktop",
    "home_logo_scale_mobile": "--home-logo-scale-mobile",
    "admin_bg": "--admin-bg",
    "admin_surface": "--admin-surface",
    "admin_surface_2": "--admin-surface-2",
    "admin_elev": "--admin-elev",
    "admin_border": "--admin-border",
    "admin_border_strong": "--admin-border-strong",
    "admin_text": "--admin-text",
    "admin_muted": "--admin-muted",
    "admin_dim": "--admin-dim",
    "admin_chart_stroke": "--admin-chart-stroke",
    "admin_chart_fill": "--admin-chart-fill",
}

_INITIAL_THEME_LOGO_SCALE_TOKENS = {
    "home_logo_scale",
    "home_logo_scale_desktop",
    "home_logo_scale_mobile",
}


def _theme_css_href_for_html(theme: Any) -> str:
    css_file = str(getattr(theme, "css_file", "") or "").strip()
    key = str(getattr(theme, "key", "") or "").strip()
    if not css_file or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key):
        return ""
    parts = [part for part in css_file.replace("\\", "/").split("/") if part]
    if any(part in {".", ".."} for part in parts):
        return ""
    themed_path = "/".join([key, *parts])
    encoded = "/".join(quote(part, safe="") for part in themed_path.split("/"))
    href = f"/webapp-theme-css/{encoded}" if encoded else ""
    try:
        version = int(getattr(theme, "assets_version", 0) or 0)
    except (TypeError, ValueError):
        version = 0
    if href and version > 0:
        href = f"{href}?v={quote(str(version), safe='')}"
    return href


def _initial_theme_for_request(request: web.Request, catalog: Any) -> Any:
    query = getattr(request, "query", {}) or {}
    preview_key = str(query.get("theme_preview") or "").strip()
    theme = resolve_webapp_theme_selection(catalog, preview_key or None)
    return theme


def _initial_theme_tokens(theme: Any, primary_color: str) -> Dict[str, Any]:
    if theme is None:
        return {}

    try:
        tokens = effective_webapp_theme_tokens(theme, primary_color)
        return tokens.model_dump(mode="json", exclude_none=True)
    except Exception:
        payload = public_theme_payload(theme, primary_color)
        tokens_payload = payload.get("tokens") if isinstance(payload, dict) else {}
        return tokens_payload if isinstance(tokens_payload, dict) else {}


def _initial_theme_declarations(tokens: Dict[str, Any]) -> List[str]:
    declarations = []
    for token_key, css_name in _INITIAL_THEME_TOKEN_CSS_MAP.items():
        if token_key in _INITIAL_THEME_LOGO_SCALE_TOKENS:
            try:
                scale = float(tokens.get(token_key) or 0)
            except (TypeError, ValueError):
                continue
            if scale > 0:
                declarations.append(f"{css_name}:{scale / 100:g}")
            continue
        value = str(tokens.get(token_key) or "").strip()
        if value:
            declarations.append(f"{css_name}:{value}")
    return declarations


def _initial_theme_head_markup(request: web.Request, theme: Any, primary_color: str) -> str:
    if theme is None:
        return ""

    tokens = _initial_theme_tokens(theme, primary_color)
    declarations = _initial_theme_declarations(tokens)

    scheme = "light" if tokens.get("color_scheme") == "light" else "dark"
    bg = str(tokens.get("bg") or "").strip()
    css_rules = [f"html{{color-scheme:{scheme};}}"]
    if bg:
        css_rules.append(f"body{{background-color:{bg};}}")
    if declarations:
        css_rules.append(f".app-shell{{{';'.join(declarations)}}}")

    nonce = html.escape(str(request.get("csp_nonce", "")), quote=True)
    style_tag = (
        f'<style id="webapp-initial-theme" nonce="{nonce}">' + "".join(css_rules) + "</style>"
    )
    href = _theme_css_href_for_html(theme)
    if not href:
        return style_tag
    stylesheet = (
        f'<link rel="stylesheet" href="{html.escape(href, quote=True)}" '
        f'data-initial-theme-css="{html.escape(str(theme.key), quote=True)}">'
    )
    return stylesheet + "\n" + style_tag


def _app_deeplink_theme_head_markup(
    request: web.Request,
    theme: Any,
    catalog: Any,
    primary_color: str,
) -> str:
    tokens = _initial_theme_tokens(theme, primary_color)
    declarations = _initial_theme_declarations(tokens)
    try:
        accent = effective_webapp_theme_accent(
            catalog,
            primary_color,
            theme_key=str(getattr(theme, "key", "") or "") or None,
        )
    except Exception:
        accent = str(primary_color or "#00fe7a").strip() or "#00fe7a"
    if accent and not any(item.startswith("--accent:") for item in declarations):
        declarations.insert(0, f"--accent:{accent}")
    if not declarations:
        return ""

    scheme = "light" if tokens.get("color_scheme") == "light" else "dark"
    nonce = html.escape(str(request.get("csp_nonce", "")), quote=True)
    return (
        f'<style id="webapp-initial-theme" nonce="{nonce}">'
        f"html{{color-scheme:{scheme};}}"
        f":root{{{';'.join(declarations)}}}"
        "</style>"
    )


def _favicon_head_markup(favicon_url: str) -> str:
    href = str(favicon_url or "").strip()
    if not href:
        return ""

    escaped_href = html.escape(href, quote=True)
    match = re.fullmatch(
        rf"{re.escape(WEBAPP_FAVICON_PATH)}/([0-9a-f]{{16}})/icon-(?:16|32|48|180|192|512)\.png",
        href,
    )
    if not match:
        rel = "apple-touch-icon" if href.endswith(".png") else "icon"
        return (
            f'<link id="app-favicon" rel="icon" href="{escaped_href}" sizes="any">\n'
            f'<link rel="{rel}" href="{escaped_href}">'
        )

    digest = match.group(1)
    base = f"{WEBAPP_FAVICON_PATH}/{digest}"
    return "\n".join(
        [
            (
                f'<link id="app-favicon" rel="icon" type="image/png" sizes="32x32" '
                f'href="{base}/icon-32.png">'
            ),
            f'<link rel="icon" type="image/x-icon" sizes="any" href="{base}/favicon.ico">',
            f'<link rel="icon" type="image/png" sizes="16x16" href="{base}/icon-16.png">',
            f'<link rel="icon" type="image/png" sizes="192x192" href="{base}/icon-192.png">',
            f'<link rel="apple-touch-icon" sizes="180x180" href="{base}/apple-touch-icon.png">',
        ]
    )
