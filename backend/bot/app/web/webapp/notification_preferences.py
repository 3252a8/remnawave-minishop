from __future__ import annotations

from typing import Any

from aiohttp import web

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.request_parsing import parse_body_or_400
from bot.services.user_notification_preferences import (
    UserNotificationPreferences,
    apply_user_notification_preferences,
    notification_email_for_user,
    token_matches_user_email,
    user_notification_preferences_enabled,
    verify_email_preferences_token,
)
from db.dal import user_dal

from .common import _invalidate_webapp_user_caches, _json_error, _require_user_id
from .notification_preference_schemas import (
    EmailNotificationPreferencesPatchBody,
    NotificationPreferencesOut,
    NotificationPreferencesPatchBody,
)
from .response_helpers import json_response


def _preferences_payload(user: Any) -> dict[str, bool]:
    return NotificationPreferencesOut.from_user(user).model_dump(mode="json")


async def _valid_unsubscribe_user(
    session: Any,
    settings: Any,
    token: str,
    *,
    lock: bool,
) -> Any | None:
    verified = verify_email_preferences_token(settings, token)
    if verified is None:
        return None
    user_id, email_digest = verified
    user = (
        await user_dal.lock_user_by_id(session, user_id)
        if lock
        else await user_dal.get_user_by_id(session, user_id)
    )
    if user is None or not token_matches_user_email(user, email_digest):
        return None
    return user


async def account_notification_preferences_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings = get_settings(request)
    if not user_notification_preferences_enabled(settings):
        return _json_error(404, "notification_preferences_disabled", "Not found")
    body = await parse_body_or_400(request, NotificationPreferencesPatchBody)
    async with get_session_factory(request)() as session, session.begin():
        user = await user_dal.lock_user_by_id(session, user_id)
        if user is None or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        apply_user_notification_preferences(user, body.to_preferences())
        preferences = _preferences_payload(user)
    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True, "notification_preferences": preferences})


async def email_notification_preferences_route(request: web.Request) -> web.Response:
    token = str(request.query.get("token") or "")
    settings = get_settings(request)
    if not user_notification_preferences_enabled(settings):
        return _json_error(404, "notification_preferences_disabled", "Not found")
    async with get_session_factory(request)() as session:
        user = await _valid_unsubscribe_user(session, settings, token, lock=False)
        if user is None:
            return _json_error(404, "invalid_unsubscribe_link", "Link is invalid or outdated")
        return json_response(
            {
                "ok": True,
                "email": notification_email_for_user(user),
                "language": str(user.language_code or settings.DEFAULT_LANGUAGE or "ru"),
                "notification_preferences": _preferences_payload(user),
            }
        )


async def email_notification_preferences_update_route(request: web.Request) -> web.Response:
    settings = get_settings(request)
    if not user_notification_preferences_enabled(settings):
        return _json_error(404, "notification_preferences_disabled", "Not found")
    body = await parse_body_or_400(request, EmailNotificationPreferencesPatchBody)
    async with get_session_factory(request)() as session, session.begin():
        user = await _valid_unsubscribe_user(session, settings, body.token, lock=True)
        if user is None:
            return _json_error(404, "invalid_unsubscribe_link", "Link is invalid or outdated")
        current = UserNotificationPreferences.from_user(user)
        apply_user_notification_preferences(
            user,
            UserNotificationPreferences(
                marketing_email=body.marketing_email,
                marketing_telegram=current.marketing_telegram,
                system_email=body.system_email,
                system_telegram=current.system_telegram,
            ),
        )
        user_id = int(user.user_id)
        email = notification_email_for_user(user)
        preferences = _preferences_payload(user)
    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response(
        {
            "ok": True,
            "email": email,
            "language": str(user.language_code or settings.DEFAULT_LANGUAGE or "ru"),
            "notification_preferences": preferences,
        }
    )
