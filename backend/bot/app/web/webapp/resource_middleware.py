"""Resource protection runs before route handlers and database-backed auditing."""

from aiohttp import web
from aiohttp.typedefs import Handler

from bot.app.web.context import get_settings
from bot.app.web.session import extract_authenticated_user_id
from config.telegram_menu import CUSTOM_EMOJI_ID_RE

from .rate_limits import check_request_limits, client_ip, enforce_action_limit
from .response_helpers import json_response

_CODE_ROUTES = {
    "/api/promo/status",
    "/api/promo/apply",
    "/api/subscription/quote-promo",
    "/api/subscription/quote",
    "/api/payments",
    "/api/tariffs/change-payment",
}
_EMOJI_MEDIA_PREFIX = "/api/admin/telegram-emoji/media/"


@web.middleware
async def api_resource_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    if request.path.startswith("/api/"):
        settings = get_settings(request)
        maximum = max(1, settings.WEBAPP_RATE_LIMIT_MAX_REQUESTS)
        user_id = extract_authenticated_user_id(request)
        quota = "api"
        multiplier = 4
        if (
            user_id is not None
            and request.method == "GET"
            and request.path.startswith(_EMOJI_MEDIA_PREFIX)
            and CUSTOM_EMOJI_ID_RE.fullmatch(request.path.removeprefix(_EMOJI_MEDIA_PREFIX))
        ):
            # A palette loads one protected image per emoji. Keep those bounded
            # reads independent of account actions; admin authorization still
            # runs in the downstream middleware and media route.
            quota = "telegram-emoji-media"
            multiplier = 16
        limits = [(f"{quota}:ip:{client_ip(request)}", maximum * multiplier * 2)]
        if user_id is not None:
            limits.append((f"{quota}:user:{user_id}", maximum * multiplier))
        blocked = await check_request_limits(
            request, limits, window_seconds=settings.WEBAPP_RATE_LIMIT_TTL_SECONDS
        )
        if blocked is not None:
            return blocked
        if user_id is not None:
            action = None
            if request.path in {"/api/tariffs/change", "/api/tariffs/change-payment"}:
                action = (
                    "payments_create"
                    if request.path.endswith("change-payment")
                    else "tariff_change"
                )
            elif request.path.startswith("/api/payments/"):
                action = "payment_status"
            if action:
                blocked = await enforce_action_limit(request, user_id=user_id, action=action)
                if blocked is not None:
                    return blocked
    return await handler(request)


@web.middleware
async def checkout_resource_middleware(
    request: web.Request, handler: Handler
) -> web.StreamResponse:
    if request.path in _CODE_ROUTES and request.can_read_body:
        if request.content_length is not None and request.content_length > 16384:
            return json_response({"ok": False, "error": "payload_too_large"}, status=413)
        request = request.clone(client_max_size=16384)
    if request.path in _CODE_ROUTES:
        user_id = extract_authenticated_user_id(request)
        if user_id is not None:
            blocked = await enforce_action_limit(request, user_id=user_id, action="code_checks")
            if blocked is not None:
                return blocked
    return await handler(request)
