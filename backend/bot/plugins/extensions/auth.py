"""Server-side sign-in helpers for trusted cabinet login providers."""

import re
import secrets
from urllib.parse import urlencode, urlsplit

from aiohttp import web

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.webapp.auth_common import _set_webapp_auth_cookies
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.plugins.packages import generation_is_current
from config.settings import Settings
from db.dal import user_dal

from .contracts import LoginProvider
from .registry import get_registry

LOGIN_PROVIDER_START_ROUTE = (
    r"/auth/plugins/{owner:[a-z][a-z0-9_-]{0,63}}/{provider:[a-z][a-z0-9_-]{0,63}}/start"
)
_CABINET_PATH = re.compile(r"(?:/[A-Za-z0-9_-]+)*")


def _cabinet_prefix(settings: Settings) -> str:
    try:
        path = urlsplit(settings.SUBSCRIPTION_MINI_APP_URL or "").path.rstrip("/")
    except ValueError:
        return ""
    return path if _CABINET_PATH.fullmatch(path) else ""


def public_login_providers(settings: Settings) -> list[dict[str, str]]:
    owners = get_registry().owners()
    if not any(entry.contributions.login_providers for entry in owners.values()):
        return []
    if not generation_is_current():
        return []
    prefix = _cabinet_prefix(settings)
    return [
        {
            "id": f"{owner}:{provider.id}",
            "name": provider.name.strip(),
            "startPath": f"{prefix}/auth/plugins/{owner}/{provider.id}/start",
        }
        for owner, entry in owners.items()
        for provider in entry.contributions.login_providers
    ]


def _active_provider(owner: str, provider: str) -> LoginProvider:
    if not generation_is_current():
        raise web.HTTPServiceUnavailable()
    entry = get_registry().owners().get(owner)
    if entry is not None:
        for candidate in entry.contributions.login_providers:
            if candidate.id == provider:
                return candidate
    raise web.HTTPNotFound()


async def login_provider_start_route(request: web.Request) -> web.StreamResponse:
    try:
        provider = _active_provider(request.match_info["owner"], request.match_info["provider"])
        response = await provider.start(request)
    except web.HTTPException as exc:
        exc.headers["Cache-Control"] = "no-store"
        raise
    response.headers["Cache-Control"] = "no-store"
    return response


async def complete_login(
    request: web.Request, *, owner: str, provider: str, user_id: int
) -> web.Response:
    """Create a cabinet session for an already verified, mapped Core account.

    Call only after consuming the provider's browser-bound state and validating its
    response server-side. The account ID must come from the plugin's trusted mapping.
    """
    _active_provider(owner, provider)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None or user.is_banned:
            raise web.HTTPForbidden()

    # The provider may have been disabled while the callback was awaiting the DB.
    _active_provider(owner, provider)
    settings = get_settings(request)
    prefix = _cabinet_prefix(settings)
    query = urlencode({"external_auth": f"{owner}/{provider}:success"})
    response = web.Response(
        status=303,
        headers={"Location": f"{prefix}/?{query}", "Cache-Control": "no-store"},
    )
    _set_webapp_auth_cookies(
        response, settings, create_webapp_session_token(settings, user_id), secrets.token_hex(32)
    )
    return response
