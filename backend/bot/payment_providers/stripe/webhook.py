from typing import cast

from aiohttp import web


async def stripe_webhook_route(request: web.Request) -> web.Response:
    return cast(web.Response, await request.app["stripe_service"].webhook_route(request))
