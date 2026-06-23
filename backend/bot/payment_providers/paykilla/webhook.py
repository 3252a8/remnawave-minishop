from aiohttp import web

from ..shared.app_context import app_required
from .service import PaykillaService


async def paykilla_webhook_route(request: web.Request) -> web.Response:
    service = app_required(request, "paykilla_service", PaykillaService)
    return await service.webhook_route(request)
