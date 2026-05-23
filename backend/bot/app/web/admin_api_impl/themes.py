# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405
from .webapp_runtime import refresh_webapp_runtime_after_settings_change

import asyncio
import hashlib
import ipaddress
import shutil
import re
import socket

from aiohttp import ClientSession, ClientTimeout
from PIL import Image, ImageOps, UnidentifiedImageError

from config.webapp_themes_config import (
    WebappThemesConfig,
    ensure_webapp_core_themes,
    resolved_webapp_themes_catalog,
    write_webapp_theme_dir,
)


WEBAPP_LOGO_MAX_BYTES = 2 * 1024 * 1024
WEBAPP_UPLOADED_LOGO_DIR = Path(__file__).resolve().parents[5] / "data" / "webapp-logo" / "uploads"
WEBAPP_UPLOADED_LOGO_PATH = "/webapp-uploaded-logo"
WEBAPP_FAVICON_DIR = Path(__file__).resolve().parents[5] / "data" / "webapp-logo" / "favicons"
WEBAPP_FAVICON_PATH = "/webapp-favicon"
WEBAPP_EMOJI_CACHE_DIR = Path(__file__).resolve().parents[5] / "data" / "webapp-emoji"
WEBAPP_FAVICON_SIZES = (16, 32, 48, 180, 192, 512)
WEBAPP_LOGO_UPLOAD_CONTENT_TYPES = {
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def _theme_payload_for_version_compare(theme: Any) -> Dict[str, Any]:
    if hasattr(theme, "model_dump"):
        data = theme.model_dump(mode="json", exclude_none=True)
    elif isinstance(theme, dict):
        data = dict(theme)
    else:
        data = {}
    data.pop("assets_version", None)
    data.pop("default", None)
    return data


def _bump_theme_asset_versions(
    config: WebappThemesConfig,
    previous: WebappThemesConfig,
) -> WebappThemesConfig:
    previous_by_key = {theme.key: theme for theme in previous.themes}
    default_changed = config.default_theme != previous.default_theme
    data = config.model_dump(mode="json", exclude_none=True)
    for theme in data.get("themes", []):
        if not isinstance(theme, dict):
            continue
        if not str(theme.get("css_file") or "").strip():
            continue
        key = str(theme.get("key") or "")
        previous_theme = previous_by_key.get(key)
        previous_version = int(getattr(previous_theme, "assets_version", 0) or 0)
        current_version = int(theme.get("assets_version") or 1)
        theme_changed = (
            previous_theme is None
            or _theme_payload_for_version_compare(theme)
            != _theme_payload_for_version_compare(previous_theme)
        )
        if theme_changed or (default_changed and key == config.default_theme):
            theme["assets_version"] = max(previous_version + 1, current_version, 1)
        elif previous_version > current_version:
            theme["assets_version"] = previous_version
    return WebappThemesConfig.model_validate(data)


def _detect_logo_extension(
    body: bytes, content_type: str = "", filename: str = ""
) -> Optional[str]:
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = Path(filename or "").suffix.lower()
    if content_type == "image/png" or body.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content_type == "image/jpeg" or body.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content_type == "image/gif" or body.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if content_type == "image/webp" or (
        len(body) > 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP"
    ):
        return ".webp"
    if content_type in {"image/svg+xml", "image/svg"} or suffix == ".svg":
        head = body[:512].lstrip().lower()
        if head.startswith(b"<svg") or b"<svg" in head:
            return ".svg"
    if content_type == "image/x-icon" or suffix == ".ico":
        if body.startswith(b"\x00\x00\x01\x00"):
            return ".ico"
    return suffix if suffix in WEBAPP_LOGO_UPLOAD_CONTENT_TYPES else None


def _write_uploaded_logo(body: bytes, content_type: str = "", filename: str = "") -> str:
    if not body or len(body) > WEBAPP_LOGO_MAX_BYTES:
        raise ValueError("logo must be a non-empty image up to 2 MiB")
    ext = _detect_logo_extension(body, content_type, filename)
    if ext not in WEBAPP_LOGO_UPLOAD_CONTENT_TYPES:
        raise ValueError("unsupported image type")
    digest = hashlib.sha256(body).hexdigest()[:16]
    safe_name = f"logo-{digest}{ext}"
    WEBAPP_UPLOADED_LOGO_DIR.mkdir(parents=True, exist_ok=True)
    (WEBAPP_UPLOADED_LOGO_DIR / safe_name).write_bytes(body)
    return f"{WEBAPP_UPLOADED_LOGO_PATH}/{safe_name}"


def _uploaded_logo_filename(url: str) -> Optional[str]:
    parsed = urlsplit(str(url or ""))
    path = parsed.path if parsed.scheme or parsed.netloc else str(url or "")
    prefix = f"{WEBAPP_UPLOADED_LOGO_PATH}/"
    if not path.startswith(prefix):
        return None
    filename = path.removeprefix(prefix)
    if re.fullmatch(r"logo-[0-9a-f]{16}\.(?:gif|ico|jpe?g|png|svg|webp)", filename):
        return filename
    return None


def _favicon_digest(url: str) -> Optional[str]:
    parsed = urlsplit(str(url or ""))
    path = parsed.path if parsed.scheme or parsed.netloc else str(url or "")
    match = re.fullmatch(
        rf"{re.escape(WEBAPP_FAVICON_PATH)}/([0-9a-f]{{16}})/(?:[A-Za-z0-9_.-]+)",
        path,
    )
    return match.group(1) if match else None


def _emoji_to_codepoints(value: str) -> str:
    return "_".join(f"{ord(char):x}" for char in str(value or "").strip())


def prune_unused_appearance_assets(settings: Settings) -> None:
    keep_logos = {
        filename
        for filename in [
            _uploaded_logo_filename(getattr(settings, "WEBAPP_LOGO_URL", "")),
        ]
        if filename
    }
    keep_favicons = {
        digest
        for digest in [
            _favicon_digest(getattr(settings, "WEBAPP_FAVICON_URL", "")),
            _favicon_digest(getattr(settings, "WEBAPP_LOGO_FAVICON_URL", "")),
        ]
        if digest
    }
    keep_emoji_prefixes = set()
    if (
        getattr(settings, "WEBAPP_LOGO_USE_EMOJI", False)
        and str(getattr(settings, "WEBAPP_LOGO_EMOJI_FONT", "") or "").strip()
        == "noto-color-animated"
    ):
        codepoints = _emoji_to_codepoints(getattr(settings, "WEBAPP_LOGO_EMOJI", ""))
        if codepoints:
            keep_emoji_prefixes.add(f"{codepoints}.512.")

    for path in WEBAPP_UPLOADED_LOGO_DIR.glob("logo-*"):
        if path.is_file() and path.name not in keep_logos:
            try:
                path.unlink()
            except OSError:
                logger.warning("Failed to remove unused webapp logo %s", path, exc_info=True)

    for path in WEBAPP_FAVICON_DIR.glob("*"):
        if (
            path.is_dir()
            and re.fullmatch(r"[0-9a-f]{16}", path.name)
            and path.name not in keep_favicons
        ):
            try:
                shutil.rmtree(path)
            except OSError:
                logger.warning("Failed to remove unused webapp favicon set %s", path, exc_info=True)

    for path in WEBAPP_EMOJI_CACHE_DIR.glob("*.512.*"):
        if path.is_file() and not any(
            path.name.startswith(prefix) for prefix in keep_emoji_prefixes
        ):
            try:
                path.unlink()
            except OSError:
                logger.warning("Failed to remove unused webapp emoji asset %s", path, exc_info=True)


async def _persist_appearance_upload(
    request: web.Request,
    updates: Dict[str, Any],
    actor_id: int,
) -> bool:
    settings: Settings = request.app["settings"]
    async_session_factory: sessionmaker = request.app["async_session_factory"]
    result = await update_overrides(
        settings,
        async_session_factory,
        updates=updates,
        deletes=[],
        actor_id=actor_id,
    )
    if not result.get("ok"):
        logger.warning("Failed to persist uploaded appearance asset settings: %s", result)
        return False

    await refresh_webapp_runtime_after_settings_change(request, updates=updates, deletes=[])
    return True


def _image_to_square_icon(source: Image.Image, size: int) -> Image.Image:
    fitted = source.copy()
    fitted.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    left = (size - fitted.width) // 2
    top = (size - fitted.height) // 2
    canvas.alpha_composite(fitted, (left, top))
    return canvas


def _write_favicon_set(body: bytes, content_type: str = "", filename: str = "") -> Dict[str, Any]:
    if not body or len(body) > WEBAPP_LOGO_MAX_BYTES:
        raise ValueError("favicon source must be a non-empty image up to 2 MiB")

    ext = _detect_logo_extension(body, content_type, filename)
    digest = hashlib.sha256(body).hexdigest()[:16]
    target_dir = WEBAPP_FAVICON_DIR / digest
    target_dir.mkdir(parents=True, exist_ok=True)

    if ext == ".svg":
        safe_name = "favicon.svg"
        (target_dir / safe_name).write_bytes(body)
        return {
            "favicon_url": f"{WEBAPP_FAVICON_PATH}/{digest}/{safe_name}",
            "variants": {"svg": f"{WEBAPP_FAVICON_PATH}/{digest}/{safe_name}"},
        }

    try:
        with Image.open(io.BytesIO(body)) as image:
            image.seek(0)
            source = ImageOps.exif_transpose(image).convert("RGBA")
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ValueError("favicon source must be a raster image") from exc

    if source.width < 1 or source.height < 1 or source.width > 8192 or source.height > 8192:
        raise ValueError("favicon source dimensions are not supported")

    variants: Dict[str, str] = {}
    png_icons: Dict[int, Image.Image] = {}
    for size in WEBAPP_FAVICON_SIZES:
        icon = _image_to_square_icon(source, size)
        png_icons[size] = icon
        filename = f"icon-{size}.png"
        icon.save(target_dir / filename, format="PNG", optimize=True)
        variants[f"{size}"] = f"{WEBAPP_FAVICON_PATH}/{digest}/{filename}"

    png_icons[180].save(target_dir / "apple-touch-icon.png", format="PNG", optimize=True)
    variants["apple_touch"] = f"{WEBAPP_FAVICON_PATH}/{digest}/apple-touch-icon.png"
    png_icons[32].save(
        target_dir / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    variants["ico"] = f"{WEBAPP_FAVICON_PATH}/{digest}/favicon.ico"
    return {
        "favicon_url": variants["180"],
        "variants": variants,
    }


async def _read_uploaded_logo_file(request: web.Request) -> tuple[bytes, str, str]:
    reader = await request.multipart()
    async for part in reader:
        if part.name != "file":
            continue
        body = bytearray()
        while True:
            chunk = await part.read_chunk(size=64 * 1024)
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > WEBAPP_LOGO_MAX_BYTES:
                raise ValueError("logo must be up to 2 MiB")
        return bytes(body), part.headers.get("Content-Type", ""), part.filename or ""
    raise ValueError("file field is required")


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
        candidate = sockaddr[0] if sockaddr else ""
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


async def _fetch_logo_from_url(url: str) -> tuple[bytes, str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("only https image URLs are supported")
    if not await _hostname_resolves_to_public_address(parsed.hostname):
        raise ValueError("logo URL must resolve to a public address")

    timeout = ClientTimeout(total=5)
    async with ClientSession(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as session:
        async with session.get(
            url,
            allow_redirects=False,
            headers={"Accept": "image/avif,image/webp,image/svg+xml,image/png,image/*,*/*;q=0.8"},
        ) as response:
            if response.status != 200:
                raise ValueError(f"logo URL returned HTTP {response.status}")
            content_type = (
                (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            )
            if content_type and not content_type.startswith("image/"):
                raise ValueError("logo URL returned non-image content")
            body = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                body.extend(chunk)
                if len(body) > WEBAPP_LOGO_MAX_BYTES:
                    raise ValueError("logo must be up to 2 MiB")
            return bytes(body), content_type, Path(parsed.path).name


async def admin_appearance_logo_upload_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    content_type = (request.headers.get("Content-Type") or "").lower()
    try:
        if content_type.startswith("multipart/form-data"):
            body, detected_content_type, filename = await _read_uploaded_logo_file(request)
        else:
            payload = await _read_json(request)
            source_url = str(payload.get("url") or "").strip()
            if not source_url:
                return _error(400, "invalid_payload", "url or file is required")
            body, detected_content_type, filename = await _fetch_logo_from_url(source_url)
        logo_url = _write_uploaded_logo(body, detected_content_type, filename)
        try:
            favicon_payload = _write_favicon_set(body, detected_content_type, filename)
        except ValueError:
            favicon_payload = {}
    except ValueError as exc:
        return _error(400, "invalid_logo", str(exc))
    except OSError as exc:
        logger.exception("Failed to save uploaded webapp logo")
        return _error(500, "write_failed", str(exc))
    persisted = await _persist_appearance_upload(
        request,
        {
            "WEBAPP_LOGO_URL": logo_url,
            "WEBAPP_LOGO_USE_EMOJI": False,
            **(
                {"WEBAPP_LOGO_FAVICON_URL": favicon_payload["favicon_url"]}
                if favicon_payload.get("favicon_url")
                else {}
            ),
        },
        actor_id,
    )

    return _ok({"logo_url": logo_url, "persisted": persisted, **favicon_payload})


async def admin_appearance_favicon_upload_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    content_type = (request.headers.get("Content-Type") or "").lower()
    try:
        if content_type.startswith("multipart/form-data"):
            body, detected_content_type, filename = await _read_uploaded_logo_file(request)
        else:
            payload = await _read_json(request)
            source_url = str(payload.get("url") or "").strip()
            if not source_url:
                return _error(400, "invalid_payload", "url or file is required")
            body, detected_content_type, filename = await _fetch_logo_from_url(source_url)
        favicon_payload = _write_favicon_set(body, detected_content_type, filename)
    except ValueError as exc:
        return _error(400, "invalid_favicon", str(exc))
    except OSError as exc:
        logger.exception("Failed to save uploaded webapp favicon")
        return _error(500, "write_failed", str(exc))
    persisted = await _persist_appearance_upload(
        request,
        {
            "WEBAPP_FAVICON_URL": favicon_payload["favicon_url"],
            "WEBAPP_FAVICON_USE_CUSTOM": True,
        },
        actor_id,
    )

    return _ok({"persisted": persisted, **favicon_payload})


async def admin_themes_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    primary = settings.WEBAPP_PRIMARY_COLOR or "#00fe7a"
    catalog = resolved_webapp_themes_catalog(
        primary_accent=primary,
        env_default_theme=settings.WEBAPP_DEFAULT_THEME,
        theme_dir=settings.WEBAPP_THEMES_DIR,
    )

    return _ok(
        {
            "exists": Path(settings.WEBAPP_THEMES_DIR).expanduser().exists(),
            "themes_dir": str(Path(settings.WEBAPP_THEMES_DIR).expanduser()),
            "catalog": _webapp_themes_catalog_payload(catalog),
        }
    )


async def admin_themes_save_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = request.app["settings"]
    previous_config = resolved_webapp_themes_catalog(
        primary_accent=settings.WEBAPP_PRIMARY_COLOR or "#00fe7a",
        env_default_theme=settings.WEBAPP_DEFAULT_THEME,
        theme_dir=settings.WEBAPP_THEMES_DIR,
    )
    payload = await _read_json(request)
    catalog = payload.get("catalog") if "catalog" in payload else payload
    if not isinstance(catalog, dict):
        return _error(400, "invalid_payload", "catalog must be an object")

    try:
        config = WebappThemesConfig.model_validate(catalog)
    except (ValidationError, ValueError) as exc:
        return _error(400, "invalid_webapp_themes_config", str(exc))

    config, _changed = ensure_webapp_core_themes(config, settings.WEBAPP_PRIMARY_COLOR or "#00fe7a")
    config = _bump_theme_asset_versions(config, previous_config)

    try:
        write_webapp_theme_dir(settings.WEBAPP_THEMES_DIR, config, delete_missing=True)
    except OSError as exc:
        logger.exception("Failed to write webapp themes to %s", settings.WEBAPP_THEMES_DIR)
        return _error(500, "write_failed", str(exc))

    await refresh_webapp_runtime_after_settings_change(request, updates={}, deletes=[])

    return _ok(
        {
            "exists": True,
            "themes_dir": str(Path(settings.WEBAPP_THEMES_DIR).expanduser()),
            "catalog": _webapp_themes_catalog_payload(config),
        }
    )
