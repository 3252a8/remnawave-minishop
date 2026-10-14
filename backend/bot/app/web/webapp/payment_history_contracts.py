from bot.app.web.payment_purchases import PaymentPurchaseOut
from bot.app.web.route_contracts import (
    INTEGER_SCHEMA,
    USER_SECURITY,
    RouteContract,
    ok_envelope_with,
    schema_ref,
)

from .payment_history_schemas import PaymentHistoryItemOut

PAYMENT_HISTORY_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "payment_history_route": RouteContract(
        response_schema=ok_envelope_with(
            {
                "items": {"type": "array", "items": schema_ref(PaymentHistoryItemOut)},
                "total": INTEGER_SCHEMA,
                "limit": INTEGER_SCHEMA,
                "offset": INTEGER_SCHEMA,
            }
        ),
        models=(PaymentHistoryItemOut, PaymentPurchaseOut),
        security=USER_SECURITY,
    ),
}
