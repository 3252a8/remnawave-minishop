from __future__ import annotations

from bot.app.web.route_contracts import RouteContract, ok_envelope_for

from .contract_schemas import InformationPageOut, public_contract

PAGES_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "information_page_content_route": public_contract(
        response_schema=ok_envelope_for(InformationPageOut),
        models=(InformationPageOut,),
    ),
}
