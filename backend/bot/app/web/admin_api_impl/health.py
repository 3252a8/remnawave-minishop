# ruff: noqa: F401,F403,F405,I001
from datetime import datetime, timezone, UTC


from aiohttp import web
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from .schemas import AdminHealthOut
from .auth import _require_admin_user_id
from .common import _ok
from bot.services.config_health_service import collect_config_alerts


register_contract(
    "admin_health_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminHealthOut),
        models=(AdminHealthOut,),
    ),
)


async def admin_health_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    refresh = str(request.query.get("refresh", "")).strip().lower() in {"1", "true", "yes"}
    alerts = await collect_config_alerts(request, refresh=refresh)
    return _ok(AdminHealthOut(alerts=alerts, checked_at=datetime.now(UTC)).model_dump(mode="json"))
