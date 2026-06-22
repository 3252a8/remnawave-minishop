from aiohttp import web


async def wata_webhook_route(request: web.Request) -> web.Response:
    return await request.app["wata_service"].webhook_route(request)
