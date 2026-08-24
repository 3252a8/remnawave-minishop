from aiohttp import web

from bot.app.web.context import get_server_status_service

from .common import _require_user_id
from .response_helpers import json_response


async def server_status_route(request: web.Request) -> web.Response:
    _require_user_id(request)
    status = await get_server_status_service(request).get_status()
    return json_response({"ok": True, **status.model_dump(mode="json", by_alias=True)})
