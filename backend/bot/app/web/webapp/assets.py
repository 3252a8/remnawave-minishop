# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405
import gzip

from config.webapp_themes_config import (
    default_webapp_theme_asset_file,
    default_webapp_theme_css_files,
    effective_webapp_theme_accent,
    effective_webapp_theme_tokens,
    ensure_default_webapp_theme_descriptor_files,
    public_theme_payload,
    public_themes_catalog_payload,
    resolve_webapp_theme_selection,
)
from bot.middlewares.i18n import locale_language_options

_TEXT_FILE_CACHE: Dict[tuple[str, bool], tuple[int, int, str]] = {}
_BINARY_FILE_CACHE: Dict[str, tuple[int, int, bytes]] = {}
_GZIP_BODY_CACHE: Dict[str, bytes] = {}
_ASSET_NAME_CACHE: Dict[tuple[str, str], tuple[float, str]] = {}
_I18N_PAYLOAD_CACHE: Dict[tuple[int, str, tuple[tuple[str, int, int], ...]], Dict[str, Any]] = {}
_ASSET_NAME_CACHE_TTL_SECONDS = 30.0
WEBAPP_HTML_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"
WEBAPP_LEGACY_ASSET_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"


async def health_route(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def robots_txt_route(request: web.Request) -> web.Response:
    response = web.Response(text=ROBOTS_TX, content_type="text/plain")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


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
    settings: Settings = request.app["settings"]
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
    settings: Settings = request.app["settings"]
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


def _resolve_webapp_logo_url(settings: Settings) -> str:
    raw_logo_url = (getattr(settings, "WEBAPP_LOGO_URL", None) or "").strip()
    if not raw_logo_url:
        return WEBAPP_DEFAULT_LOGO_PATH

    parsed_logo_url = urlsplit(raw_logo_url)
    if parsed_logo_url.scheme == "https":
        cache_key = hashlib.sha256(raw_logo_url.encode("utf-8")).hexdigest()[:12]
        return f"{WEBAPP_LOGO_PROXY_PATH}?v={cache_key}"
    if parsed_logo_url.scheme in {"http", "data"}:
        return raw_logo_url
    if raw_logo_url.startswith("/"):
        return raw_logo_url
    return WEBAPP_DEFAULT_LOGO_PATH


def _resolve_webapp_favicon_url(settings: Settings, logo_url: str = "") -> str:
    raw_custom_url = (getattr(settings, "WEBAPP_FAVICON_URL", None) or "").strip()
    raw_logo_favicon_url = (getattr(settings, "WEBAPP_LOGO_FAVICON_URL", None) or "").strip()
    if getattr(settings, "WEBAPP_FAVICON_USE_CUSTOM", False) and raw_custom_url:
        return _resolve_webapp_asset_url(raw_custom_url)
    if logo_url and raw_logo_favicon_url:
        resolved = _resolve_webapp_asset_url(raw_logo_favicon_url)
        if resolved:
            return resolved
    if logo_url and logo_url != WEBAPP_DEFAULT_LOGO_PATH:
        return logo_url
    return WEBAPP_DEFAULT_FAVICON_URL


def _resolve_webapp_asset_url(raw_url: str) -> str:
    parsed_url = urlsplit(raw_url)
    if parsed_url.scheme in {"https", "http", "data"}:
        return raw_url
    if raw_url.startswith("/"):
        return raw_url
    return ""


def _webapp_logo_cache_key(logo_url: str) -> str:
    return hashlib.sha256(logo_url.encode("utf-8")).hexdigest()


def _webapp_logo_disk_paths(logo_url: str) -> Tuple[Path, Path]:
    cache_key = _webapp_logo_cache_key(logo_url)
    return WEBAPP_LOGO_CACHE_DIR / f"{cache_key}.bin", WEBAPP_LOGO_CACHE_DIR / f"{cache_key}.json"


def _is_proxyable_webapp_logo_url(logo_url: str) -> bool:
    parsed_logo_url = urlsplit(logo_url)
    return parsed_logo_url.scheme == "https" and bool(parsed_logo_url.hostname)


def _uploaded_webapp_logo_filename(logo_url: str) -> Optional[str]:
    parsed_logo_url = urlsplit(str(logo_url or ""))
    path = parsed_logo_url.path if parsed_logo_url.scheme or parsed_logo_url.netloc else logo_url
    prefix = f"{WEBAPP_UPLOADED_LOGO_PATH}/"
    if not path.startswith(prefix):
        return None
    filename = path.removeprefix(prefix)
    if re.fullmatch(r"logo-[0-9a-f]{16}\.(?:gif|ico|jpe?g|png|svg|webp)", filename):
        return filename
    return None


def _uploaded_webapp_logo_response(filename: str) -> web.Response:
    if not re.fullmatch(r"logo-[0-9a-f]{16}\.(?:gif|ico|jpe?g|png|svg|webp)", filename):
        raise web.HTTPNotFound(text="webapp_logo_not_found")

    root = WEBAPP_UPLOADED_LOGO_DIR.expanduser().resolve()
    path = (root / filename).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise web.HTTPNotFound(text="webapp_logo_not_found") from None

    content_type = WEBAPP_THEME_ASSET_CONTENT_TYPES.get(path.suffix.lower())
    if not content_type:
        raise web.HTTPNotFound(text="webapp_logo_not_found")

    try:
        if path.stat().st_size > WEBAPP_LOGO_MAX_BYTES:
            raise web.HTTPNotFound(text="webapp_logo_too_large")
        body = path.read_bytes()
    except OSError:
        raise web.HTTPNotFound(text="webapp_logo_not_found") from None

    if not body:
        raise web.HTTPNotFound(text="webapp_logo_not_found")

    response = web.Response(body=body, content_type=content_type)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


async def webapp_logo_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    raw_logo_url = (settings.WEBAPP_LOGO_URL or "").strip()
    if not raw_logo_url:
        raise web.HTTPNotFound(text="webapp_logo_not_configured")

    uploaded_filename = _uploaded_webapp_logo_filename(raw_logo_url)
    if uploaded_filename:
        return _uploaded_webapp_logo_response(uploaded_filename)

    if not _is_proxyable_webapp_logo_url(raw_logo_url):
        raise web.HTTPNotFound(text="webapp_logo_not_proxied")

    parsed_logo_url = urlsplit(raw_logo_url)
    if not await _hostname_resolves_to_public_address(parsed_logo_url.hostname):
        raise web.HTTPNotFound(text="webapp_logo_not_proxied")

    source_logo_url = raw_logo_url
    logo_cache: Optional[Tuple[str, bytes, str]] = request.app.get("webapp_logo_cache")
    if logo_cache is None or logo_cache[0] != source_logo_url:
        cache_lock: asyncio.Lock = request.app["webapp_logo_cache_lock"]
        async with cache_lock:
            logo_cache = request.app.get("webapp_logo_cache")
            if logo_cache is None or logo_cache[0] != source_logo_url:
                fetched_logo = await _load_or_fetch_webapp_logo(source_logo_url)
                logo_cache = (
                    (source_logo_url, fetched_logo[0], fetched_logo[1]) if fetched_logo else None
                )
                request.app["webapp_logo_cache"] = logo_cache

    if not logo_cache:
        raise web.HTTPNotFound(text="webapp_logo_unavailable")

    _, body, content_type = logo_cache
    response = web.Response(body=body, content_type=content_type)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


async def webapp_uploaded_logo_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    filename = str(request.match_info.get("filename") or "").strip()
    return _uploaded_webapp_logo_response(filename)


async def webapp_default_logo_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    response = _webapp_default_brand_file_response(WEBAPP_DEFAULT_LOGO_FILE, "image/webp")
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


async def webapp_favicon_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    digest = str(request.match_info.get("digest") or "").strip().lower()
    filename = str(request.match_info.get("filename") or "").strip()
    return _webapp_favicon_file_response(digest, filename)


async def webapp_current_favicon_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    requested_filename = str(request.path.rsplit("/", 1)[-1] or "").strip()
    target_filename = _webapp_root_favicon_target_filename(requested_filename)
    if not target_filename:
        raise web.HTTPNotFound(text="webapp_favicon_not_found")

    favicon_url = _resolve_webapp_favicon_url(settings, _resolve_webapp_logo_url(settings))
    digest = _webapp_generated_favicon_digest(favicon_url)
    if digest:
        response = _webapp_favicon_file_response(digest, target_filename)
        response.headers["Cache-Control"] = "no-cache"
        return response

    redirect_url = _webapp_redirectable_favicon_url(favicon_url, target_filename)
    if redirect_url:
        redirect = web.HTTPFound(location=redirect_url)
        redirect.headers["Cache-Control"] = "no-cache"
        raise redirect

    raise web.HTTPNotFound(text="webapp_favicon_not_found")


def _webapp_root_favicon_target_filename(filename: str) -> str:
    if filename == "apple-touch-icon-precomposed.png":
        return "apple-touch-icon.png"
    if filename in {
        "apple-touch-icon.png",
        "favicon.ico",
        "icon-192.png",
        "icon-512.png",
    }:
        return filename
    return ""


def _webapp_generated_favicon_digest(favicon_url: str) -> str:
    parsed = urlsplit(str(favicon_url or ""))
    path = parsed.path if parsed.scheme or parsed.netloc else str(favicon_url or "")
    match = re.fullmatch(
        rf"{re.escape(WEBAPP_FAVICON_PATH)}/([0-9a-f]{{16}})/"
        r"(?:icon-(?:16|32|48|180|192|512)\.png|apple-touch-icon\.png|favicon\.(?:ico|svg))",
        path,
    )
    return match.group(1) if match else ""


def _webapp_redirectable_favicon_url(favicon_url: str, target_filename: str) -> str:
    href = str(favicon_url or "").strip()
    if not href:
        return ""

    parsed = urlsplit(href)
    path = parsed.path if parsed.scheme or parsed.netloc else href
    suffix = Path(path).suffix.lower()
    if target_filename in {"apple-touch-icon.png", "icon-192.png", "icon-512.png"}:
        if suffix != ".png":
            return ""
    elif target_filename == "favicon.ico":
        if suffix != ".ico":
            return ""
    else:
        return ""

    if parsed.scheme in {"http", "https"} or href.startswith("/"):
        return href
    return ""


def _webapp_favicon_file_response(digest: str, filename: str) -> web.Response:
    if not re.fullmatch(r"[0-9a-f]{16}", digest):
        raise web.HTTPNotFound(text="webapp_favicon_not_found")
    if not re.fullmatch(
        r"(?:icon-(?:16|32|48|180|192|512)\.png|apple-touch-icon\.png|favicon\.(?:ico|svg))",
        filename,
    ):
        raise web.HTTPNotFound(text="webapp_favicon_not_found")

    if digest == WEBAPP_DEFAULT_FAVICON_DIGEST:
        return _webapp_default_favicon_file_response(filename)

    root = WEBAPP_FAVICON_DIR.expanduser().resolve()
    path = (root / digest / filename).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise web.HTTPNotFound(text="webapp_favicon_not_found") from None

    content_type = WEBAPP_THEME_ASSET_CONTENT_TYPES.get(path.suffix.lower())
    if not content_type:
        raise web.HTTPNotFound(text="webapp_favicon_not_found")

    try:
        if path.stat().st_size > WEBAPP_LOGO_MAX_BYTES:
            raise web.HTTPNotFound(text="webapp_favicon_too_large")
        body = path.read_bytes()
    except OSError:
        raise web.HTTPNotFound(text="webapp_favicon_not_found") from None

    if not body:
        raise web.HTTPNotFound(text="webapp_favicon_not_found")

    response = web.Response(body=body, content_type=content_type)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def _webapp_default_favicon_file_response(filename: str) -> web.Response:
    path = WEBAPP_DEFAULT_FAVICON_DIR / filename
    content_type = WEBAPP_THEME_ASSET_CONTENT_TYPES.get(path.suffix.lower())
    if not content_type:
        raise web.HTTPNotFound(text="webapp_favicon_not_found")

    response = _webapp_default_brand_file_response(path, content_type)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def _webapp_default_brand_file_response(path: Path, content_type: str) -> web.Response:
    try:
        body = _read_template_binary_cached(path)
    except OSError:
        raise web.HTTPNotFound(text="webapp_default_brand_not_found") from None

    if not body or len(body) > WEBAPP_LOGO_MAX_BYTES:
        raise web.HTTPNotFound(text="webapp_default_brand_not_found")

    return web.Response(body=body, content_type=content_type)


async def _warm_webapp_logo_cache(app: web.Application) -> None:
    settings: Settings = app["settings"]
    raw_logo_url = (settings.WEBAPP_LOGO_URL or "").strip()
    if not raw_logo_url or not _is_proxyable_webapp_logo_url(raw_logo_url):
        return

    parsed_logo_url = urlsplit(raw_logo_url)
    if not parsed_logo_url.hostname or not await _hostname_resolves_to_public_address(
        parsed_logo_url.hostname
    ):
        return

    cache_lock: asyncio.Lock = app["webapp_logo_cache_lock"]
    async with cache_lock:
        logo_cache: Optional[Tuple[str, bytes, str]] = app.get("webapp_logo_cache")
        if logo_cache and logo_cache[0] == raw_logo_url:
            return
        loaded_logo = await _load_or_fetch_webapp_logo(raw_logo_url)
        app["webapp_logo_cache"] = (
            (raw_logo_url, loaded_logo[0], loaded_logo[1]) if loaded_logo else None
        )


async def _load_or_fetch_webapp_logo(logo_url: str) -> Optional[Tuple[bytes, str]]:
    disk_logo = await asyncio.to_thread(_read_webapp_logo_from_disk, logo_url)
    if disk_logo:
        return disk_logo

    fetched_logo = await _fetch_webapp_logo(logo_url)
    if fetched_logo:
        await asyncio.to_thread(_write_webapp_logo_to_disk, logo_url, fetched_logo)
    return fetched_logo


def _read_webapp_logo_from_disk(logo_url: str) -> Optional[Tuple[bytes, str]]:
    body_path, meta_path = _webapp_logo_disk_paths(logo_url)
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if metadata.get("source_url") != logo_url:
            return None
        content_type = str(metadata.get("content_type") or "").strip().lower()
        if not content_type.startswith("image/"):
            return None
        body = body_path.read_bytes()
    except (OSError, json.JSONDecodeError):
        return None

    if not body or len(body) > WEBAPP_LOGO_MAX_BYTES:
        return None
    return body, content_type


def _write_webapp_logo_to_disk(logo_url: str, logo: Tuple[bytes, str]) -> None:
    body, content_type = logo
    if not body or len(body) > WEBAPP_LOGO_MAX_BYTES:
        return

    body_path, meta_path = _webapp_logo_disk_paths(logo_url)
    try:
        WEBAPP_LOGO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(body)
        meta_path.write_text(
            json.dumps(
                {
                    "source_url": logo_url,
                    "content_type": content_type,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "bytes": len(body),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write WEBAPP_LOGO_URL cache: %s", exc)


async def _fetch_webapp_logo(logo_url: str) -> Optional[Tuple[bytes, str]]:
    """Fetch and cache the configured logo on the server side."""
    try:
        session = await _get_shared_http_session()
        timeout = ClientTimeout(total=3)
        async with session.get(
            logo_url,
            allow_redirects=False,
            headers={"Accept": "image/avif,image/webp,image/svg+xml,image/png,image/*,*/*;q=0.8"},
            timeout=timeout,
        ) as response:
            if response.status != 200:
                logger.warning(
                    "WEBAPP_LOGO_URL returned HTTP %s; keeping the logo hidden.",
                    response.status,
                )
                return None

            content_type = (
                (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            )
            if content_type and not content_type.startswith("image/"):
                logger.warning(
                    "WEBAPP_LOGO_URL returned non-image content type %s; keeping the logo hidden.",
                    content_type,
                )
                return None

            body = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                body.extend(chunk)
                if len(body) > WEBAPP_LOGO_MAX_BYTES:
                    logger.warning("WEBAPP_LOGO_URL exceeded the 2 MiB limit.")
                    return None

            if not body:
                logger.warning("WEBAPP_LOGO_URL returned an empty response body.")
                return None

            return bytes(body), content_type or "image/png"
    except Exception as exc:
        logger.warning("Failed to fetch WEBAPP_LOGO_URL: %s", exc)
        return None


async def _get_shared_http_session() -> ClientSession:
    global _SHARED_HTTP_SESSION
    async with _SHARED_HTTP_SESSION_LOCK:
        if _SHARED_HTTP_SESSION is None or _SHARED_HTTP_SESSION.closed:
            _SHARED_HTTP_SESSION = ClientSession(
                timeout=ClientTimeout(total=30),
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "*/*",
                },
            )
        return _SHARED_HTTP_SESSION


async def _ensure_shared_http_session() -> None:
    await _get_shared_http_session()


async def _close_shared_http_session() -> None:
    global _SHARED_HTTP_SESSION
    async with _SHARED_HTTP_SESSION_LOCK:
        if _SHARED_HTTP_SESSION and not _SHARED_HTTP_SESSION.closed:
            await _SHARED_HTTP_SESSION.close()
        _SHARED_HTTP_SESSION = None


async def _hostname_resolves_to_public_address(hostname: str) -> bool:
    if not hostname:
        return False

    try:
        ip_obj = ipaddress.ip_address(hostname)
        return not (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_unspecified
            or ip_obj.is_reserved
        )
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        resolved = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except Exception:
        return False

    found_public_ip = False
    for entry in resolved:
        sockaddr = entry[4]
        if not sockaddr:
            continue
        candidate = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_unspecified
            or ip_obj.is_reserved
        ):
            return False
        found_public_ip = True

    return found_public_ip


@web.middleware
async def _security_headers_middleware(request: web.Request, handler):
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
async def _csrf_protection_middleware(request: web.Request, handler):
    settings: Settings = request.app["settings"]
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
    settings: Settings = request.app["settings"]
    cache = request.app["webapp_settings_cache"]
    now = time.monotonic()
    if now - float(cache.get("ts", 0.0)) >= 60 or not cache.get("data"):
        logo_url = _resolve_webapp_logo_url(settings)
        cache["data"] = {
            "logo_url": logo_url,
            "favicon_url": _resolve_webapp_favicon_url(settings, logo_url),
            "subscription_options": settings.subscription_options,
            "stars_subscription_options": settings.stars_subscription_options,
            "traffic_packages": settings.traffic_packages,
            "stars_traffic_packages": settings.stars_traffic_packages,
            "support_url": settings.SUPPORT_LINK or "",
            "server_status_url": settings.SERVER_STATUS_URL or "",
            "privacy_policy_url": settings.PRIVACY_POLICY_URL or "",
            "user_agreement_url": settings.USER_AGREEMENT_URL or "",
            "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            "email_auth_enabled": settings.email_auth_configured,
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
    settings: Settings = request.app["settings"]
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
                return web.json_response(
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

    buckets: Dict[str, deque[float]] = request.app["webapp_rate_limit_buckets"]
    lock: asyncio.Lock = request.app["webapp_rate_limit_lock"]
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
            return web.json_response(
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


async def js_asset_route(request: web.Request) -> web.Response:
    return await _js_asset_route(request, base_name="subscription_webapp")


async def admin_js_asset_route(request: web.Request) -> web.Response:
    return await _js_asset_route(request, base_name="subscription_webapp_admin")


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
    settings: Settings = request.app["settings"]
    cached = _get_cached_webapp_settings(request)
    themes_catalog = settings.webapp_themes_catalog
    primary_color = settings.WEBAPP_PRIMARY_COLOR or "#00fe7a"
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
    i18n_instance: Optional[object] = request.app.get("i18n")
    i18n_scope = _normalize_i18n_scope(request.query.get("i18n_scope") or "webapp")
    if i18n_instance and hasattr(i18n_instance, "reload_overrides_from_file"):
        i18n_instance.reload_overrides_from_file()
    locales_data = getattr(i18n_instance, "locales_data", {}) if i18n_instance else {}
    base_locales_data = getattr(i18n_instance, "base_locales_data", {}) if i18n_instance else {}
    return {
        "config": {
            "title": settings.WEBAPP_TITLE,
            "primaryColor": settings.WEBAPP_PRIMARY_COLOR,
            "themesCatalog": themes_payload,
            "themesDir": settings.WEBAPP_THEMES_DIR,
            "themePreviewKey": preview_key,
            "logoUrl": cached["logo_url"],
            "faviconUrl": cached["favicon_url"],
            "faviconUseCustom": bool(settings.WEBAPP_FAVICON_USE_CUSTOM),
            "apiBase": "/api",
            "adminJsAsset": f"/{_resolve_webapp_admin_js_asset_name()}",
            "adminCssAsset": f"/{_resolve_webapp_admin_css_asset_name()}",
            "telegramLoginBotUsername": request.app.get("bot_username") or "",
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
            "appVersion": _resolve_app_version(),
            "appRepositoryUrl": APP_REPOSITORY_URL,
        },
        "i18n": _filter_webapp_i18n_payload(locales_data, i18n_scope),
    }


async def bootstrap_route(request: web.Request) -> web.Response:
    response = web.json_response({"ok": True, **_build_webapp_bootstrap_payload(request)})
    response.headers["Cache-Control"] = "no-cache"
    return response


async def i18n_route(request: web.Request) -> web.Response:
    i18n_instance: Optional[object] = request.app.get("i18n")
    if i18n_instance and hasattr(i18n_instance, "reload_overrides_from_file"):
        i18n_instance.reload_overrides_from_file()
    scope = _normalize_i18n_scope(request.query.get("scope") or "webapp")
    locales_data = getattr(i18n_instance, "locales_data", {}) if i18n_instance else {}
    response = web.json_response(
        {
            "ok": True,
            "scope": scope,
            "i18n": _filter_webapp_i18n_payload(locales_data, scope),
        }
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


def _webapp_page_title(settings: Settings, suffix: str = "") -> str:
    base = str(getattr(settings, "WEBAPP_TITLE", "") or "").strip() or "Subscription"
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


async def index_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
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
    settings: Settings = request.app["settings"]
    if not getattr(settings, "WEBAPP_ENABLED", True):
        raise web.HTTPNotFound(text="webapp_disabled")

    nonce = html.escape(str(request.get("csp_nonce", "")), quote=True)
    query = getattr(request, "query", {}) or {}
    themes_catalog = getattr(settings, "webapp_themes_catalog", None)
    primary_color = getattr(settings, "WEBAPP_PRIMARY_COLOR", None) or "#00fe7a"
    initial_theme = (
        _initial_theme_for_request(request, themes_catalog) if themes_catalog is not None else None
    )
    lang = _normalize_language(query.get("lang") or getattr(settings, "DEFAULT_LANGUAGE", "ru"))
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
    i18n_instance: Optional[object] = request.app.get("i18n")
    payload: Dict[str, str] = {}
    for payload_key, i18n_key in APP_DEEPLINK_I18N_KEYS.items():
        fallback = APP_DEEPLINK_I18N_FALLBACKS[i18n_key]
        value = ""
        if i18n_instance is not None:
            try:
                value = str(i18n_instance.gettext(lang, i18n_key) or "")
            except Exception as exc:
                logger.debug("Failed to resolve open-app i18n key %s: %s", i18n_key, exc)
        payload[payload_key] = value if value and value != i18n_key else fallback
    return payload


async def _serve_template_asset(
    request: web.Request,
    filename: str,
    content_type: str,
    *,
    allow_precompressed: bool = False,
    strip_dev_mock: bool = False,
) -> web.Response:
    settings: Settings = request.app["settings"]
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
) -> Optional[web.Response]:
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


def _get_cached_asset_name(kind: str) -> Optional[str]:
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


def _strip_marked_block(html: str, start_marker: str, end_marker: str) -> str:
    start = html.find(start_marker)
    if start == -1:
        return html
    end = html.find(end_marker, start)
    if end == -1:
        return html[:start]
    return html[:start] + html[end + len(end_marker) :]
