"""Assign the configured first owner before authorization and maintenance checks."""

from aiohttp import web
from aiohttp.typedefs import Handler

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.session import extract_authenticated_user_id
from bot.services.account_roles import bootstrap_configured_owner


@web.middleware
async def owner_bootstrap_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    settings = get_settings(request)
    telegram_id = settings.BOOTSTRAP_OWNER_TELEGRAM_ID
    email = settings.BOOTSTRAP_OWNER_EMAIL
    if request.path.startswith("/api/") and (telegram_id is not None or email):
        user_id = extract_authenticated_user_id(request)
        if user_id is not None:
            async with get_session_factory(request)() as session:
                if await bootstrap_configured_owner(
                    session, user_id, telegram_id=telegram_id, email=email
                ):
                    await session.commit()
    return await handler(request)
