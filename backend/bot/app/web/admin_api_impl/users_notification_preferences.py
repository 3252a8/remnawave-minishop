from __future__ import annotations

from aiohttp import web

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.webapp.notification_preference_schemas import (
    NotificationPreferencesOut,
    NotificationPreferencesPatchBody,
)
from bot.services.user_notification_preferences import apply_user_notification_preferences
from db.dal import user_dal

from .auth import _require_admin_user_id
from .common import _error, _ok
from .users_listing import _invalidate_after_admin_user_mutation


async def admin_user_notification_preferences_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, NotificationPreferencesPatchBody)
    settings = get_settings(request)
    async with get_session_factory(request)() as session, session.begin():
        user = await user_dal.lock_user_by_id(session, target_id)
        if user is None:
            return _error(404, "not_found", "User not found")
        apply_user_notification_preferences(user, body.to_preferences())
        preferences = NotificationPreferencesOut.from_user(user).model_dump(mode="json")
    await _invalidate_after_admin_user_mutation(settings, target_id, include_devices=False)
    return _ok({"notification_preferences": preferences})
