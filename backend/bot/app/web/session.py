from __future__ import annotations

from typing import Optional

from aiohttp import web

from bot.app.web.context import (
    get_settings,
)
from bot.app.web.webapp_auth import verify_webapp_session_token
from config.settings import Settings

WEBAPP_SESSION_COOKIE_NAME = "rw_webapp_session"


def extract_authenticated_user_id(request: web.Request) -> Optional[int]:
    settings: Settings = get_settings(request)

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        user_id = verify_webapp_session_token(
            settings,
            auth_header.removeprefix("Bearer ").strip(),
        )
        if user_id:
            return user_id

    session_cookie = request.cookies.get(WEBAPP_SESSION_COOKIE_NAME)
    if session_cookie:
        return verify_webapp_session_token(settings, session_cookie)

    return None
