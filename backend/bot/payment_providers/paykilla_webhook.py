from aiohttp import web


async def paykilla_webhook_route(request: web.Request) -> web.Response:
    return await request.app["paykilla_service"].webhook_route(request)
