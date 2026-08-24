from bot.app.web.route_contracts import USER_SECURITY, RouteContract, ok_envelope_for
from bot.services.server_status import ServerStatus

SERVER_STATUS_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "server_status_route": RouteContract(
        response_schema=ok_envelope_for(ServerStatus),
        models=(ServerStatus,),
        security=USER_SECURITY,
    )
}
