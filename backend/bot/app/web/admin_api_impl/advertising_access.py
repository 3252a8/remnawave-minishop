"""Access to the optional advertising workspace; legacy routes remain available."""

from aiohttp import web

from bot.app.web.context import get_settings

from .auth import _require_admin_user_id


def require_advertising_admin(request: web.Request) -> int:
    actor = _require_admin_user_id(request)
    if not get_settings(request).ADVERTISING_ENABLED:
        raise web.HTTPNotFound(
            text='{"ok":false,"error":"advertising_disabled"}',
            content_type="application/json",
        )
    return actor
