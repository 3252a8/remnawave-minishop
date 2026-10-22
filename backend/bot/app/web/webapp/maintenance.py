"""Maintenance gate for user actions; recovery and payment settlement stay available."""

import re

from aiohttp import web
from aiohttp.typedefs import Handler

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.session import extract_authenticated_user_id
from bot.services.account_roles import is_admin
from db.dal import user_dal

from .response_helpers import json_response

_PUBLIC_PATHS = {
    "/api/bootstrap",
    "/api/i18n",
    "/api/theme-effects",
    "/api/documents",
    "/api/notification-preferences/unsubscribe",
}
_PUBLIC_PREFIXES = (
    "/api/auth/",
    "/api/admin/",
    "/api/theme-effects/assets/",
    "/api/documents/",
    "/api/pages/",
)
_EXISTING_PAYMENT = re.compile(r"/api/payments/[0-9]+(?:/cancel)?")


@web.middleware
async def maintenance_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    path = request.path
    if (
        not path.startswith("/api/")
        or path in _PUBLIC_PATHS
        or path.startswith(_PUBLIC_PREFIXES)
        or not get_settings(request).MAINTENANCE_MODE_ENABLED
        or (request.method in {"GET", "POST"} and _EXISTING_PAYMENT.fullmatch(path))
    ):
        return await handler(request)

    user_id = extract_authenticated_user_id(request)
    authorized = False
    if user_id is not None:
        async with get_session_factory(request)() as session:
            user = await user_dal.get_user_by_id(session, user_id)
            authorized = (
                user is not None and not user.is_banned and await is_admin(session, user_id)
            )
    if authorized:
        return await handler(request)

    response = json_response({"ok": False, "error": "maintenance_mode"}, status=503)
    response.headers["Retry-After"] = "60"
    return response
