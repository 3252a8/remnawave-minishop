from aiohttp import web

from ..shared.app_context import app_required
from .service import StripeService


async def stripe_webhook_route(request: web.Request) -> web.Response:
    service = app_required(request, "stripe_service", StripeService)
    return await service.webhook_route(request)
