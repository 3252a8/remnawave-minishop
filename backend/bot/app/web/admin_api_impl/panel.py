from bot.app.web.context import (
    get_panel_service,
)

from ._runtime import (
    RouteContract,
    logger,
    loose_array_schema,
    ok_envelope_with,
    register_contract,
    web,
)
from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
)

register_contract(
    "admin_panel_internal_squads_route",
    RouteContract(response_schema=ok_envelope_with({"squads": loose_array_schema()})),
)


async def admin_panel_internal_squads_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    panel_service = get_panel_service(request)
    if panel_service is None:
        return _error(503, "panel_unavailable", "Panel service unavailable")
    try:
        squads = await panel_service.get_internal_squads()
    except Exception as exc:
        logger.exception("Failed to load internal squads from panel")
        return _error(502, "panel_request_failed", str(exc))
    if squads is None:
        return _error(502, "panel_request_failed", "Unable to load internal squads")
    items = []
    for squad in squads:
        if not isinstance(squad, dict):
            continue
        uuid = squad.get("uuid") or squad.get("id")
        if not uuid:
            continue
        items.append(
            {
                "uuid": str(uuid),
                "name": squad.get("name") or squad.get("title") or str(uuid),
                "members_count": squad.get("membersCount")
                or squad.get("usersCount")
                or squad.get("members_count"),
                "active_inbounds_count": squad.get("activeInboundsCount")
                or squad.get("active_inbounds_count"),
            }
        )
    return _ok({"squads": items})
