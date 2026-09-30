"""Resource protection runs before route handlers and database-backed auditing."""

from aiohttp import web
from aiohttp.typedefs import Handler

from bot.app.web.session import extract_authenticated_user_id

from .rate_limits import enforce_action_limit

_CODE_ROUTES = {
    "/api/promo/status",
    "/api/promo/apply",
    "/api/subscription/quote-promo",
    "/api/subscription/quote",
    "/api/payments",
    "/api/tariffs/change-payment",
}


@web.middleware
async def checkout_resource_middleware(
    request: web.Request, handler: Handler
) -> web.StreamResponse:
    if request.path in _CODE_ROUTES:
        user_id = extract_authenticated_user_id(request)
        if user_id is not None:
            blocked = await enforce_action_limit(request, user_id=user_id, action="code_checks")
            if blocked is not None:
                return blocked
    return await handler(request)
