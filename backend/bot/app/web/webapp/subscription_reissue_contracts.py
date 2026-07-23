from __future__ import annotations

from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    RouteContract,
    ok_envelope_with,
)

from .contract_schemas import user_contract
from .payloads import WebAppSubscriptionReissuePayload

SUBSCRIPTION_REISSUE_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "subscription_reissue_route": user_contract(
        request_model=WebAppSubscriptionReissuePayload,
        response_schema=ok_envelope_with(
            {
                "email_sent": BOOLEAN_SCHEMA,
            },
        ),
    ),
}
