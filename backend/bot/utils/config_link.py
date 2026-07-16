import hashlib
import logging

from bot.services.panel_api_service import PanelApiService
from bot.utils.ttl_cache import AsyncTTLCache
from config.settings import Settings

logger = logging.getLogger(__name__)

_CRYPT4_LINK_CACHES: dict[tuple[int, int], AsyncTTLCache] = {}


async def _encrypt_raw_link(settings: Settings, raw_link: str) -> str | None:
    """Encrypt the raw subscription URL using local Happ Crypt4 compatibility."""
    async with PanelApiService(settings) as panel_service:
        encrypted_link = await panel_service.encrypt_happ_link(raw_link)
        if isinstance(encrypted_link, str) and encrypted_link:
            return encrypted_link
    return None


def _crypt4_link_cache(settings: Settings) -> AsyncTTLCache | None:
    ttl_seconds = int(settings.CRYPT4_LINK_CACHE_TTL_SECONDS or 0)
    if ttl_seconds <= 0:
        return None
    cache_key = (id(settings), ttl_seconds)
    cache = _CRYPT4_LINK_CACHES.get(cache_key)
    if cache is None:
        cache = AsyncTTLCache(
            ttl_seconds=ttl_seconds,
            settings=settings,
            namespace="crypt4:links",
        )
        _CRYPT4_LINK_CACHES[cache_key] = cache
    return cache


async def _encrypt_raw_link_cached(settings: Settings, raw_link: str) -> str | None:
    cache = _crypt4_link_cache(settings)
    if cache is None:
        return await _encrypt_raw_link(settings, raw_link)
    key = hashlib.sha256(raw_link.encode("utf-8")).hexdigest()
    encrypted_link = await cache.get_or_load(key, lambda: _encrypt_raw_link(settings, raw_link))
    return encrypted_link if isinstance(encrypted_link, str) else None


async def prepare_config_links(
    settings: Settings, raw_link: str | None
) -> tuple[str | None, str | None]:
    """
    Build the user-facing connection key and the URL for the connect button.

    Returns (display_link, button_link). When CRYPT4 is enabled the display link
    is encrypted and prefixed with happ://crypt4/, and the button link is wrapped
    with CRYPT4_REDIRECT_URL if provided.
    """
    if not raw_link:
        return None, None

    cleaned = raw_link.strip()
    if not cleaned:
        return None, None

    display_link = cleaned
    button_link = cleaned

    if settings.CRYPT4_ENABLED:
        encrypted_payload = await _encrypt_raw_link_cached(settings, cleaned)
        if encrypted_payload:
            display_link = encrypted_payload
            button_link = display_link
        else:
            logger.error("CRYPT4_ENABLED is set but encryption failed; using raw link as fallback.")

    redirect_base = (settings.CRYPT4_REDIRECT_URL or "").strip()
    if redirect_base and settings.CRYPT4_ENABLED and display_link:
        button_link = f"{redirect_base}{display_link}"

    return display_link, button_link
