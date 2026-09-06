from bot.app.web.route_contracts import (
    GENERIC_OK_RESPONSE,
    RouteContract,
    ok_envelope_for,
    ok_envelope_with,
)

from .contract_schemas import PLAN_LIST_SCHEMA, user_contract
from .gifts import GiftTokenBody, GiftView

GIFT_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "gift_options_route": user_contract(
        response_schema=ok_envelope_with(
            {
                "plans": PLAN_LIST_SCHEMA,
                "email_available": {"type": "boolean"},
                "enabled": {"type": "boolean"},
            }
        )
    ),
    "gifts_route": user_contract(
        response_schema=ok_envelope_with(
            {
                "gifts": {"type": "array", "items": {"$ref": "#/components/schemas/GiftView"}},
                "enabled": {"type": "boolean"},
            }
        ),
        models=(GiftView,),
    ),
    "gift_preview_route": user_contract(
        request_model=GiftTokenBody,
        response_schema=ok_envelope_for(GiftView, key="gift"),
        models=(GiftView,),
    ),
    "gift_claim_route": user_contract(
        request_model=GiftTokenBody, response_schema=GENERIC_OK_RESPONSE
    ),
}
