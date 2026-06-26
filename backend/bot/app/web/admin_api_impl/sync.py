from aiohttp import web

from bot.app.web.context import (
    get_settings,
)
from bot.app.web.route_contracts import (
    RouteContract,
    loose_object_schema,
    ok_envelope_with,
    register_contract,
)
from bot.infra.webhook_queue import enqueue_webhook_event
from config.settings import Settings

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
)

register_contract(
    "admin_sync_route",
    RouteContract(response_schema=ok_envelope_with({"result": loose_object_schema()})),
)


async def admin_sync_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    settings: Settings = get_settings(request)
    queued = await enqueue_webhook_event(
        settings,
        "panel_sync",
        {"requested_by": _require_admin_user_id(request)},
        event_id=None,
    )
    if queued:
        return _ok({"result": {"status": "queued"}})
    return _error(503, "queue_unavailable")
