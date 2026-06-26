import json
from collections.abc import Awaitable, Callable

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
    get_settings,
)
from config.settings import Settings
from db.dal import user_dal


def _require_admin_user_id(request: web.Request) -> int:
    """Return the authenticated user id, or raise 401/403 for non-admins."""

    from bot.app.web.session import extract_authenticated_user_id

    settings: Settings = get_settings(request)
    user_id = extract_authenticated_user_id(request)
    if not user_id:
        raise web.HTTPUnauthorized(
            text=json.dumps({"ok": False, "error": "unauthorized"}),
            content_type="application/json",
        )

    admin_ids = settings.ADMIN_IDS or []
    db_user_telegram_id = request.get("admin_telegram_id")
    if db_user_telegram_id is None:
        raise web.HTTPForbidden(
            text=json.dumps({"ok": False, "error": "forbidden"}),
            content_type="application/json",
        )

    if int(db_user_telegram_id) not in {int(x) for x in admin_ids}:
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
    """Resolve the Telegram id of the current user and stash it on the request.

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
        if db_user and db_user.telegram_id:
            request["admin_telegram_id"] = int(db_user.telegram_id)
        elif db_user:
            # No telegram_id yet (email-only user) — can't be an admin
            request["admin_telegram_id"] = None

    return await handler(request)
