# ruff: noqa: F401, I001
from datetime import datetime, timezone, UTC


from aiohttp import web
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from .schemas import AdminHealthOut, AdminPanelCompatibilityOut
from .auth import _require_admin_user_id
from .common import _ok
from bot.services.config_health_service import collect_config_alerts
from bot.app.web.context import get_app_panel_service


register_contract(
    "admin_health_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminHealthOut),
        models=(AdminHealthOut, AdminPanelCompatibilityOut),
    ),
)


async def admin_health_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    refresh = str(request.query.get("refresh", "")).strip().lower() in {"1", "true", "yes"}
    alerts = await collect_config_alerts(request, refresh=refresh)
    panel_compatibility = None
    panel_service = get_app_panel_service(request.app)
    diagnostics_method = getattr(panel_service, "panel_compatibility_diagnostics", None)
    if callable(diagnostics_method):
        try:
            diagnostics = await diagnostics_method()
            if isinstance(diagnostics, dict):
                panel_compatibility = AdminPanelCompatibilityOut.model_validate(diagnostics)
        except Exception:
            panel_compatibility = None
    return _ok(
        AdminHealthOut(
            alerts=alerts,
            checked_at=datetime.now(UTC),
            panel_compatibility=panel_compatibility,
        ).model_dump(mode="json")
    )
