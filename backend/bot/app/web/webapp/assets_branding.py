from ._runtime import (
    _SHARED_HTTP_SESSION,
    _SHARED_HTTP_SESSION_LOCK,
    WEBAPP_DEFAULT_FAVICON_DIGEST,
    WEBAPP_DEFAULT_FAVICON_DIR,
    WEBAPP_DEFAULT_FAVICON_URL,
    WEBAPP_DEFAULT_LOGO_FILE,
    WEBAPP_DEFAULT_LOGO_PATH,
    WEBAPP_FAVICON_DIR,
    WEBAPP_FAVICON_PATH,
    WEBAPP_LOGO_CACHE_DIR,
    WEBAPP_LOGO_MAX_BYTES,
    WEBAPP_LOGO_PROXY_PATH,
    WEBAPP_THEME_ASSET_CONTENT_TYPES,
    WEBAPP_UPLOADED_LOGO_DIR,
    WEBAPP_UPLOADED_LOGO_PATH,
    Any,
    ClientSession,
    ClientTimeout,
    Dict,
    Optional,
    Path,
    Settings,
    Tuple,
    asyncio,
    datetime,
    hashlib,
    ipaddress,
    json,
    logger,
    re,
    socket,
    timezone,
    urlsplit,
    web,
)
from .assets_static import _read_template_binary_cached

_TEXT_FILE_CACHE: Dict[tuple[str, bool], tuple[int, int, str]] = {}
_BINARY_FILE_CACHE: Dict[str, tuple[int, int, bytes]] = {}
_GZIP_BODY_CACHE: Dict[str, bytes] = {}
_ASSET_NAME_CACHE: Dict[tuple[str, str], tuple[float, str]] = {}
_I18N_PAYLOAD_CACHE: Dict[tuple[int, str, tuple[tuple[str, int, int], ...]], Dict[str, Any]] = {}
_ASSET_NAME_CACHE_TTL_SECONDS = 30.0
WEBAPP_HTML_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"
WEBAPP_LEGACY_ASSET_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"


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
    logo_hostname = parsed_logo_url.hostname
    if not logo_hostname or not await _hostname_resolves_to_public_address(logo_hostname):
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
