from aiohttp import web

from ..shared.app_context import app_required
from .service import WataService


async def wata_webhook_route(request: web.Request) -> web.Response:
    service = app_required(request, "wata_service", WataService)
    return await service.webhook_route(request)
