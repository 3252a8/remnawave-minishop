"""Verified account email address management for the Security screen."""

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import get_session_factory, get_settings
from config.settings import Settings
from db.dal import user_dal, user_email_dal

from .common import (
    _invalidate_webapp_user_caches,
    _json_error,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import WebAppEmailPayload
from .response_helpers import json_response


async def account_notification_email_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    settings: Settings = get_settings(request)
    payload = await _parse_model_payload(request, WebAppEmailPayload)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned:
            return _json_error(403, "access_denied", "Access denied")
        address = await user_email_dal.set_user_notification_email(session, user, payload.email)
        if address is None:
            await session.rollback()
            return _json_error(
                400,
                "email_not_verified",
                "Choose a verified email address from this account",
            )
        await session.commit()
    await _invalidate_webapp_user_caches(settings, user_id)
    return json_response({"ok": True, "notification_email": str(address.email)})
