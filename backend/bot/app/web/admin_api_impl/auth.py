import json
from collections.abc import Awaitable, Callable

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
)
from bot.plugins.packages import package_root, read_state
from bot.services.account_roles import is_admin
from db.dal import user_dal


def _require_admin_user_id(request: web.Request) -> int:
    """Return the authenticated user id, or raise 401/403 for non-admins."""

    from bot.app.web.session import extract_authenticated_user_id

    user_id = extract_authenticated_user_id(request)
    if not user_id:
        raise web.HTTPUnauthorized(
            text=json.dumps({"ok": False, "error": "unauthorized"}),
            content_type="application/json",
        )

    if not request.get("admin_authorized", False):
        raise web.HTTPForbidden(
            text=json.dumps({"ok": False, "error": "forbidden"}),
            content_type="application/json",
        )
    return int(user_id)


@web.middleware
async def admin_auth_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Resolve the current account's role on every admin request.

    Doing this once per request lets every admin route call
    ``_require_admin_user_id`` without re-querying the DB.
    """

    if not request.path.startswith("/api/admin"):
        return await handler(request)

    from bot.app.web.session import extract_authenticated_user_id

    user_id = extract_authenticated_user_id(request)
    if user_id:
        async_session_factory: sessionmaker = get_session_factory(request)
        async with async_session_factory() as session:
            db_user = await user_dal.get_user_by_id(session, user_id)
        if db_user and bool(getattr(db_user, "is_banned", False)):
            raise web.HTTPForbidden(
                text=json.dumps({"ok": False, "error": "forbidden"}),
                content_type="application/json",
            )
        if db_user:
            async with async_session_factory() as session:
                request["admin_authorized"] = await is_admin(session, int(db_user.user_id))

    client_generation = request.headers.get("X-Minishop-Plugin-Generation")
    if client_generation is not None and request.get("admin_authorized", False):
        try:
            generation = read_state(package_root())["generation"]
        except (OSError, ValueError):
            generation = -1
        if client_generation != str(generation):
            raise web.HTTPConflict(
                text=json.dumps({"ok": False, "error": "plugin_generation_changed"}),
                content_type="application/json",
            )

    return await handler(request)
