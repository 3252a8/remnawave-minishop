"""Public instruction payload; access is checked fresh on every request."""

from typing import Any

from aiohttp import web

from bot.app.web.context import get_settings
from bot.utils.config_link import prepare_config_links
from bot.utils.mini_app_url import subscription_public_install_url

SUBSCRIPTION_GUIDES_PUBLIC_CACHE_TTL_SECONDS = 0


async def _public_subscription_payload_cached(
    request: web.Request, share_token: str
) -> dict[str, Any]:
    # Kept as a compatibility import. Public credentials must never use a TTL
    # cache because a panel-side reissue can revoke them at any moment.
    return await _public_subscription_payload_uncached(request, share_token)


async def _public_subscription_payload_uncached(
    request: web.Request, share_token: str
) -> dict[str, Any]:
    from .subscription_access import resolve_subscription_access

    settings = get_settings(request)
    access = await resolve_subscription_access(request, share_token)
    if access is None:
        return {"active": False}
    raw_link = access.panel_url
    selected_link = raw_link
    if settings.SUBSCRIPTION_GATEWAY_ENABLED and settings.SUBSCRIPTION_LINK_MODE == "minishop":
        selected_link = _public_install_url(request, share_token)
        if not selected_link:
            selected_link = raw_link
    display_link, connect_url = await prepare_config_links(settings, selected_link)
    return {
        "active": bool(display_link),
        "config_link": display_link,
        "connect_url": connect_url or display_link,
        "http_url": selected_link,
        "link_mode": ("minishop" if selected_link != raw_link else "panel"),
        "panel_short_uuid": access.panel_short_uuid,
        "install_share_token": share_token,
        "username": access.username,
        "share_url": _public_install_url(request, share_token),
        "_panel_user_uuid": access.panel_user_uuid,
    }


def _public_install_url(request: web.Request, share_token: str) -> str:
    return subscription_public_install_url(get_settings(request), share_token) or ""
