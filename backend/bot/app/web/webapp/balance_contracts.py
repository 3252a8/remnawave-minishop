from __future__ import annotations

from bot.app.web.route_contracts import RouteContract

from .contract_schemas import BALANCE_SCHEMA, PAYMENT_RESPONSE_SCHEMA, user_contract
from .payloads import WebAppBalanceTopupPayload

BALANCE_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "balance_route": user_contract(response_schema=BALANCE_SCHEMA),
    "balance_topup_route": user_contract(
        request_model=WebAppBalanceTopupPayload,
        response_schema=PAYMENT_RESPONSE_SCHEMA,
    ),
}
