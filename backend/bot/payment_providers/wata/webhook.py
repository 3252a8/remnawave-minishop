from typing import cast

from aiohttp import web


async def wata_webhook_route(request: web.Request) -> web.Response:
    return cast(web.Response, await request.app["wata_service"].webhook_route(request))
