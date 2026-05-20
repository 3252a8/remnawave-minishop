# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405

from config.webapp_themes_config import (
    default_webapp_theme_asset_file,
    default_webapp_theme_css_files,
    ensure_default_webapp_theme_descriptor_files,
    public_theme_payload,
    public_themes_catalog_payload,
)


async def health_route(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def css_asset_route(request: web.Request) -> web.Response:
    asset_hash = request.match_info.get("asset_hash")
    filename = f"subscription_webapp.{asset_hash}.css" if asset_hash else "subscription_webapp.css"
    response = await _serve_template_asset(request, filename, "text/css")
    response.headers["Cache-Control"] = (
        "public, max-age=31536000, immutable" if asset_hash else "no-cache"
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

    try:
        if path.stat().st_size > WEBAPP_THEME_CSS_MAX_BYTES:
            raise web.HTTPNotFound(text="theme_css_too_large")
        text = path.read_text(encoding="utf-8")
    except OSError:
        defaults = default_webapp_theme_css_files()
        text = defaults.get(rel_path.as_posix())
        if text is None:
            raise web.HTTPNotFound(text="theme_css_not_found") from None

    response = web.Response(text=text, content_type="text/css", charset="utf-8")
    response.headers["Cache-Control"] = "no-cache"
    return response


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

    try:
        if path.stat().st_size > WEBAPP_THEME_ASSET_MAX_BYTES:
            raise web.HTTPNotFound(text="theme_asset_too_large")
        body = path.read_bytes()
    except OSError:
        fallback = default_webapp_theme_asset_file(rel_path)
        if fallback is None:
            raise web.HTTPNotFound(text="theme_asset_not_found") from None
        body, fallback_suffix = fallback
        content_type = WEBAPP_THEME_ASSET_CONTENT_TYPES.get(fallback_suffix, content_type)

    if not body or len(body) > WEBAPP_THEME_ASSET_MAX_BYTES:
        raise web.HTTPNotFound(text="theme_asset_not_found")

    query = getattr(request, "query", {})
    response = web.Response(body=body, content_type=content_type)
    response.headers["Cache-Control"] = (
        "public, max-age=31536000, immutable" if query.get("v") else "public, max-age=3600"
    )
    return response


def _resolve_webapp_logo_url(settings: Settings) -> str:
    if getattr(settings, "WEBAPP_LOGO_USE_EMOJI", False):
        return ""

    raw_logo_url = (settings.WEBAPP_LOGO_URL or "").strip()
    if not raw_logo_url:
        return ""

    parsed_logo_url = urlsplit(raw_logo_url)
    if parsed_logo_url.scheme == "https":
        cache_key = hashlib.sha256(raw_logo_url.encode("utf-8")).hexdigest()[:12]
        return f"{WEBAPP_LOGO_PROXY_PATH}?v={cache_key}"
    if parsed_logo_url.scheme in {"http", "data"}:
        return raw_logo_url
    if raw_logo_url.startswith("/"):
        return raw_logo_url
    return ""


def _resolve_webapp_favicon_url(settings: Settings, logo_url: str = "") -> str:
    raw_custom_url = (getattr(settings, "WEBAPP_FAVICON_URL", None) or "").strip()
    raw_logo_favicon_url = (getattr(settings, "WEBAPP_LOGO_FAVICON_URL", None) or "").strip()
    if getattr(settings, "WEBAPP_FAVICON_USE_CUSTOM", False) and raw_custom_url:
        return _resolve_webapp_asset_url(raw_custom_url)
    if logo_url and raw_logo_favicon_url:
        resolved = _resolve_webapp_asset_url(raw_logo_favicon_url)
        if resolved:
            return resolved
    return logo_url or ""


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


def _emoji_to_codepoints(value: str) -> str:
    return "_".join(f"{ord(char):x}" for char in str(value or "").strip())


def _webapp_emoji_disk_path(codepoints: str, ext: str) -> Path:
    return WEBAPP_EMOJI_CACHE_DIR / f"{codepoints}.512.{ext}"


def _webapp_animated_emoji_source_url(codepoints: str, ext: str) -> str:
    return f"https://fonts.gstatic.com/s/e/notoemoji/latest/{codepoints}/512.{ext}"


def _webapp_animated_emoji_asset_path(emoji: str, ext: str = "gif") -> str:
    codepoints = _emoji_to_codepoints(emoji)
    if not codepoints or ext not in {"gif", "webp"}:
        return ""
    return f"/webapp-emoji/{codepoints}/512.{ext}"


async def webapp_logo_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if getattr(settings, "WEBAPP_LOGO_USE_EMOJI", False):
        raise web.HTTPNotFound(text="webapp_logo_disabled")
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


async def webapp_favicon_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    digest = str(request.match_info.get("digest") or "").strip().lower()
    filename = str(request.match_info.get("filename") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{16}", digest):
        raise web.HTTPNotFound(text="webapp_favicon_not_found")
    if not re.fullmatch(
        r"(?:icon-(?:16|32|48|180|192|512)\.png|apple-touch-icon\.png|favicon\.(?:ico|svg))",
        filename,
    ):
        raise web.HTTPNotFound(text="webapp_favicon_not_found")

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


async def webapp_animated_emoji_route(request: web.Request) -> web.Response:
    codepoints = str(request.match_info.get("codepoints") or "").strip().lower()
    ext = str(request.match_info.get("ext") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]+(?:_[0-9a-f]+)*", codepoints) or ext not in {"gif", "webp"}:
        raise web.HTTPNotFound(text="webapp_emoji_not_found")

    emoji_cache_key = f"{codepoints}:{ext}"
    emoji_caches: Dict[str, Tuple[bytes, str]] = request.app.setdefault("webapp_emoji_cache", {})
    emoji_cache = emoji_caches.get(emoji_cache_key)
    if emoji_cache is None:
        cache_lock: asyncio.Lock = request.app.setdefault("webapp_emoji_cache_lock", asyncio.Lock())
        async with cache_lock:
            emoji_cache = emoji_caches.get(emoji_cache_key)
            if emoji_cache is None:
                emoji_cache = await _load_or_fetch_webapp_animated_emoji(codepoints, ext)
                if emoji_cache:
                    emoji_caches[emoji_cache_key] = emoji_cache

    if not emoji_cache:
        raise web.HTTPNotFound(text="webapp_emoji_unavailable")

    body, content_type = emoji_cache
    response = web.Response(body=body, content_type=content_type)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


async def _warm_webapp_logo_cache(app: web.Application) -> None:
    settings: Settings = app["settings"]
    if getattr(settings, "WEBAPP_LOGO_USE_EMOJI", False):
        return
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


async def _warm_webapp_animated_emoji_cache(app: web.Application) -> None:
    settings: Settings = app["settings"]
    if not getattr(settings, "WEBAPP_LOGO_USE_EMOJI", False):
        return
    if str(settings.WEBAPP_LOGO_EMOJI_FONT or "").strip() != "noto-color-animated":
        return

    codepoints = _emoji_to_codepoints(settings.WEBAPP_LOGO_EMOJI)
    if not codepoints:
        return

    app.setdefault("webapp_emoji_cache", {})
    app.setdefault("webapp_emoji_cache_lock", asyncio.Lock())
    emoji_caches: Dict[str, Tuple[bytes, str]] = app["webapp_emoji_cache"]

    for ext in ("gif", "webp"):
        emoji_cache_key = f"{codepoints}:{ext}"
        if emoji_cache_key in emoji_caches:
            continue
        loaded_emoji = await _load_or_fetch_webapp_animated_emoji(codepoints, ext)
        if loaded_emoji:
            emoji_caches[emoji_cache_key] = loaded_emoji
            if ext == "gif":
                return


async def _load_or_fetch_webapp_animated_emoji(
    codepoints: str, ext: str
) -> Optional[Tuple[bytes, str]]:
    disk_emoji = await asyncio.to_thread(_read_webapp_animated_emoji_from_disk, codepoints, ext)
    if disk_emoji:
        return disk_emoji

    fetched_emoji = await _fetch_webapp_animated_emoji(codepoints, ext)
    if fetched_emoji:
        await asyncio.to_thread(
            _write_webapp_animated_emoji_to_disk, codepoints, ext, fetched_emoji
        )
    return fetched_emoji


def _read_webapp_animated_emoji_from_disk(codepoints: str, ext: str) -> Optional[Tuple[bytes, str]]:
    path = _webapp_emoji_disk_path(codepoints, ext)
    try:
        body = path.read_bytes()
    except OSError:
        return None

    if not body or len(body) > WEBAPP_EMOJI_MAX_BYTES:
        return None
    return body, "image/gif" if ext == "gif" else "image/webp"


def _write_webapp_animated_emoji_to_disk(
    codepoints: str, ext: str, emoji: Tuple[bytes, str]
) -> None:
    body, _content_type = emoji
    if not body or len(body) > WEBAPP_EMOJI_MAX_BYTES:
        return

    path = _webapp_emoji_disk_path(codepoints, ext)
    try:
        WEBAPP_EMOJI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    except OSError as exc:
        logger.warning("Failed to write WEBAPP animated emoji cache: %s", exc)


async def _fetch_webapp_animated_emoji(codepoints: str, ext: str) -> Optional[Tuple[bytes, str]]:
    try:
        session = await _get_shared_http_session()
        timeout = ClientTimeout(total=4)
        source_url = _webapp_animated_emoji_source_url(codepoints, ext)
        async with session.get(
            source_url,
            allow_redirects=False,
            headers={"Accept": "image/gif,image/webp,image/*,*/*;q=0.8"},
            timeout=timeout,
        ) as response:
            if response.status != 200:
                return None

            content_type = (
                (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            )
            expected_content_type = "image/gif" if ext == "gif" else "image/webp"
            if content_type and content_type != expected_content_type:
                return None

            body = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                body.extend(chunk)
                if len(body) > WEBAPP_EMOJI_MAX_BYTES:
                    logger.warning("WEBAPP animated emoji exceeded the 4 MiB limit.")
                    return None

            if not body:
                return None

            return bytes(body), expected_content_type
    except Exception as exc:
        logger.warning("Failed to fetch WEBAPP animated emoji: %s", exc)
        return None


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
            "terms_url": settings.TERMS_OF_SERVICE_URL or "",
            "privacy_policy_url": settings.PRIVACY_POLICY_URL or "",
            "user_agreement_url": settings.USER_AGREEMENT_URL or "",
            "currency": settings.DEFAULT_CURRENCY_SYMBOL or "RUB",
            "email_auth_enabled": settings.email_auth_configured,
            "language": _normalize_language(settings.DEFAULT_LANGUAGE),
        }
        cache["ts"] = now
    return cache["data"]


def _run_git_command(*args: str) -> str:
    repo_root = APP_ROOT
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _resolve_app_version() -> str:
    global _APP_VERSION_CACHE
    if _APP_VERSION_CACHE:
        return _APP_VERSION_CACHE

    env_version = os.getenv("REMNAWAVE_MINISHOP_VERSION", "").strip()
    if env_version:
        _APP_VERSION_CACHE = env_version
        return env_version

    build_version_path = APP_ROOT / ".build-version"
    try:
        build_version = build_version_path.read_text(encoding="utf-8").strip()
    except OSError:
        build_version = ""
    if build_version:
        _APP_VERSION_CACHE = build_version
        return build_version

    tag = _run_git_command("describe", "--tags", "--abbrev=0")
    sha = _run_git_command("rev-parse", "--short", "HEAD")
    dirty = bool(_run_git_command("status", "--porcelain"))

    if tag and sha:
        commits_since_tag = _run_git_command("rev-list", f"{tag}..HEAD", "--count")
        if commits_since_tag and commits_since_tag != "0":
            version = f"{tag}+{commits_since_tag}.g{sha}"
        else:
            version = tag
    elif sha:
        version = f"dev+g{sha}"
    else:
        version = "dev+unknown"

    if dirty:
        version = f"{version}-dirty"

    _APP_VERSION_CACHE = version
    return version


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
    redis = await get_redis(settings)
    if redis is not None:
        redis_rate_key = redis_key(settings, "rate-limit", "webapp", key)
        current = await redis.incr(redis_rate_key)
        if current == 1:
            await redis.expire(redis_rate_key, settings.WEBAPP_RATE_LIMIT_TTL_SECONDS)
        if current > settings.WEBAPP_RATE_LIMIT_MAX_REQUESTS:
            ttl = await redis.ttl(redis_rate_key)
            retry_after = max(1, int(ttl if ttl and ttl > 0 else WEBAPP_RATE_LIMIT_WINDOW_SECONDS))
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
    asset_hash = request.match_info.get("asset_hash")
    filename = (
        f"subscription_webapp.min.{asset_hash}.js" if asset_hash else "subscription_webapp.js"
    )
    response = await _serve_template_asset(
        request,
        filename,
        "application/javascript",
        strip_dev_mock=not asset_hash,
    )
    response.headers["Cache-Control"] = (
        "public, max-age=31536000, immutable" if asset_hash else "no-cache"
    )
    return response


WEBAPP_BOOTSTRAP_I18N_PREFIXES = ("wa_",)
WEBAPP_BOOTSTRAP_I18N_KEYS = {"menu_support_button"}
WEBAPP_I18N_SCOPES = {"webapp", "admin"}


def _is_webapp_bootstrap_i18n_key(key: str) -> bool:
    return key in WEBAPP_BOOTSTRAP_I18N_KEYS or key.startswith(WEBAPP_BOOTSTRAP_I18N_PREFIXES)


def _normalize_i18n_scope(raw_scope: object) -> str:
    scope = str(raw_scope or "webapp").strip().lower()
    return scope if scope in WEBAPP_I18N_SCOPES else "webapp"


def _filter_webapp_i18n_payload(locales_data: object, scope: str = "webapp") -> Dict[str, Any]:
    if not isinstance(locales_data, dict):
        return {}

    normalized_scope = _normalize_i18n_scope(scope)
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
    return payload


def _build_webapp_bootstrap_payload(request: web.Request) -> Dict[str, Any]:
    settings: Settings = request.app["settings"]
    cached = _get_cached_webapp_settings(request)
    themes_catalog = settings.webapp_themes_catalog
    primary_color = settings.WEBAPP_PRIMARY_COLOR or "#00fe7a"
    preview_key = str(request.query.get("theme_preview") or "").strip()
    preview_theme = themes_catalog.theme_by_key(preview_key) if preview_key else None
    if preview_theme is None or not preview_theme.enabled:
        preview_key = ""
    i18n_instance: Optional[object] = request.app.get("i18n")
    i18n_scope = _normalize_i18n_scope(request.query.get("i18n_scope") or "webapp")
    locales_data = getattr(i18n_instance, "locales_data", {}) if i18n_instance else {}
    return {
        "config": {
            "title": settings.WEBAPP_TITLE,
            "primaryColor": settings.WEBAPP_PRIMARY_COLOR,
            "themesCatalog": public_themes_catalog_payload(
                themes_catalog,
                primary_color,
                enabled_only=True,
            ),
            "themesDir": settings.WEBAPP_THEMES_DIR,
            "themePreviewKey": preview_key,
            "logoUrl": cached["logo_url"],
            "logoUseEmoji": bool(settings.WEBAPP_LOGO_USE_EMOJI),
            "logoEmoji": settings.WEBAPP_LOGO_EMOJI,
            "logoEmojiFont": settings.WEBAPP_LOGO_EMOJI_FONT,
            "faviconUrl": cached["favicon_url"],
            "faviconUseCustom": bool(settings.WEBAPP_FAVICON_USE_CUSTOM),
            "apiBase": "/api",
            "telegramLoginBotUsername": request.app.get("bot_username") or "",
            "telegramLoginBotId": _resolve_telegram_bot_id(settings.BOT_TOKEN) or 0,
            "telegramOAuthClientId": _resolve_telegram_oauth_client_id(settings) or 0,
            "telegramOAuthRequestAccess": _resolve_telegram_oauth_request_access(settings),
            "supportUrl": cached["support_url"],
            "termsUrl": cached["terms_url"],
            "privacyPolicyUrl": cached["privacy_policy_url"],
            "userAgreementUrl": cached["user_agreement_url"],
            "currency": cached["currency"],
            "language": cached["language"],
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


async def index_route(request: web.Request) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    cached = _get_cached_webapp_settings(request)
    themes_catalog = settings.webapp_themes_catalog
    primary_color = settings.WEBAPP_PRIMARY_COLOR or "#00fe7a"
    initial_theme = _initial_theme_for_request(request, themes_catalog)
    bootstrap = _build_webapp_bootstrap_payload(request)
    config = bootstrap["config"]
    html = _strip_marked_block(html, DEV_MOCK_START_MARKER, DEV_MOCK_END_MARKER)
    html = html.replace(
        'href="/subscription_webapp.css"',
        f'href="/{_resolve_webapp_css_asset_name()}"',
        1,
    )
    initial_theme_markup = _initial_theme_head_markup(request, initial_theme, primary_color)
    if initial_theme_markup:
        html = html.replace("</head>", f"{initial_theme_markup}\n</head>", 1)
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
        f'<script src="/{_resolve_webapp_js_asset_name()}" defer></script>',
    )
    favicon_markup = _favicon_head_markup(cached["favicon_url"])
    if favicon_markup:
        html = html.replace(
            '<link id="app-favicon" rel="icon" href="data:," sizes="any">',
            favicon_markup,
        )
    brand_asset_url = cached["logo_url"]
    if (
        not brand_asset_url
        and settings.WEBAPP_LOGO_USE_EMOJI
        and settings.WEBAPP_LOGO_EMOJI_FONT == "noto-color-animated"
    ):
        brand_asset_url = _webapp_animated_emoji_asset_path(settings.WEBAPP_LOGO_EMOJI)
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
    response.headers["Cache-Control"] = "no-cache"
    return response


async def _serve_template_asset(
    request: web.Request,
    filename: str,
    content_type: str,
    *,
    strip_dev_mock: bool = False,
) -> web.Response:
    settings: Settings = request.app["settings"]
    if not settings.WEBAPP_ENABLED:
        raise web.HTTPNotFound(text="webapp_disabled")

    path = ASSET_DIR / filename
    text = path.read_text(encoding="utf-8")
    if strip_dev_mock:
        text = _strip_marked_block(
            text,
            "/* WEBAPP_DEV_MOCK_START */",
            "/* WEBAPP_DEV_MOCK_END */",
        )
    return web.Response(text=text, content_type=content_type, charset="utf-8")


def _resolve_webapp_js_asset_name() -> str:
    minified_assets = []
    for path in ASSET_DIR.glob("subscription_webapp.min.*.js"):
        try:
            minified_assets.append((path.stat().st_mtime, path.name))
        except OSError:
            continue
    if minified_assets:
        minified_assets.sort(reverse=True)
        return minified_assets[0][1]
    return "subscription_webapp.js"


def _resolve_webapp_css_asset_name() -> str:
    hashed_assets = []
    for path in ASSET_DIR.glob("subscription_webapp.*.css"):
        if not re.fullmatch(r"subscription_webapp\.[0-9a-f]{8}\.css", path.name):
            continue
        try:
            hashed_assets.append((path.stat().st_mtime, path.name))
        except OSError:
            continue
    if hashed_assets:
        hashed_assets.sort(reverse=True)
        return hashed_assets[0][1]
    return "subscription_webapp.css"


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
    "blue": "--blue",
    "radius": "--radius",
    "font_sans": "--font-sans",
    "font_logo": "--font-logo",
    "font_mono": "--font-mono",
    "admin_bg": "--admin-bg",
    "admin_surface": "--admin-surface",
    "admin_surface_2": "--admin-surface-2",
    "admin_elev": "--admin-elev",
    "admin_border": "--admin-border",
    "admin_border_strong": "--admin-border-strong",
    "admin_text": "--admin-text",
    "admin_muted": "--admin-muted",
    "admin_dim": "--admin-dim",
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
    return f"/webapp-theme-css/{encoded}" if encoded else ""


def _initial_theme_for_request(request: web.Request, catalog: Any) -> Any:
    preview_key = str(request.query.get("theme_preview") or "").strip()
    if preview_key:
        preview_theme = catalog.theme_by_key(preview_key)
        if preview_theme is not None and preview_theme.enabled:
            return preview_theme

    theme = catalog.theme_by_key(catalog.default_theme)
    if theme is not None:
        return theme
    return catalog.enabled_themes()[0] if catalog.enabled_themes() else None


def _initial_theme_head_markup(request: web.Request, theme: Any, primary_color: str) -> str:
    if theme is None:
        return ""

    payload = public_theme_payload(theme, primary_color)
    tokens = payload.get("tokens") if isinstance(payload, dict) else {}
    tokens = tokens if isinstance(tokens, dict) else {}
    declarations = []
    for token_key, css_name in _INITIAL_THEME_TOKEN_CSS_MAP.items():
        value = str(tokens.get(token_key) or "").strip()
        if value:
            declarations.append(f"{css_name}:{value}")

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
