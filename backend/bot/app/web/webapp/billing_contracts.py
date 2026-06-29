from __future__ import annotations

from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    NULLABLE_NUMBER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    NUMBER_SCHEMA,
    STRING_SCHEMA,
    RouteContract,
    ok_envelope_with,
)

from .contract_schemas import (
    PAYMENT_RESPONSE_SCHEMA,
    PLAN_OPTIONS_RESPONSE_SCHEMA,
    TARIFF_CHANGE_OPTIONS_RESPONSE_SCHEMA,
    TARIFF_CHANGE_RESPONSE_SCHEMA,
    user_contract,
)
from .payloads import (
    WebAppAutoRenewPayload,
    WebAppPaymentCreatePayload,
    WebAppPromoQuotePayload,
    WebAppTariffChangePayload,
)

PROMO_QUOTE_RESPONSE_SCHEMA = ok_envelope_with(
    {
        "valid": BOOLEAN_SCHEMA,
        "payable": BOOLEAN_SCHEMA,
        "code": STRING_SCHEMA,
        "promo_code_id": INTEGER_SCHEMA,
        "currency": STRING_SCHEMA,
        "discount_percent": NUMBER_SCHEMA,
        "base_amount": NUMBER_SCHEMA,
        "effective_amount": NUMBER_SCHEMA,
        "base_stars": NULLABLE_INTEGER_SCHEMA,
        "effective_stars": NULLABLE_INTEGER_SCHEMA,
        "discount_amount": NUMBER_SCHEMA,
        "effect_summary": STRING_SCHEMA,
        "applies_to": STRING_SCHEMA,
        "min_subscription_months": NULLABLE_INTEGER_SCHEMA,
        "min_traffic_gb": NULLABLE_NUMBER_SCHEMA,
        "reason": NULLABLE_STRING_SCHEMA,
        "reason_key": NULLABLE_STRING_SCHEMA,
    },
    required=["valid"],
)

BILLING_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "subscription_auto_renew_route": user_contract(
        request_model=WebAppAutoRenewPayload,
        response_schema=ok_envelope_with(
            {
                "auto_renew_enabled": BOOLEAN_SCHEMA,
                "provider": STRING_SCHEMA,
                "provider_label": STRING_SCHEMA,
            }
        ),
    ),
    "device_topup_options_route": user_contract(response_schema=PLAN_OPTIONS_RESPONSE_SCHEMA),
    "tariff_topup_options_route": user_contract(response_schema=PLAN_OPTIONS_RESPONSE_SCHEMA),
    "tariff_change_options_route": user_contract(
        response_schema=TARIFF_CHANGE_OPTIONS_RESPONSE_SCHEMA,
    ),
    "tariff_change_route": user_contract(
        request_model=WebAppTariffChangePayload,
        response_schema=TARIFF_CHANGE_RESPONSE_SCHEMA,
    ),
    "tariff_change_payment_route": user_contract(
        request_model=WebAppPaymentCreatePayload,
        response_schema=PAYMENT_RESPONSE_SCHEMA,
    ),
    "create_payment_route": user_contract(
        request_model=WebAppPaymentCreatePayload,
        response_schema=PAYMENT_RESPONSE_SCHEMA,
    ),
    "quote_promo_route": user_contract(
        request_model=WebAppPromoQuotePayload,
        response_schema=PROMO_QUOTE_RESPONSE_SCHEMA,
    ),
    "payment_status_route": user_contract(response_schema=PAYMENT_RESPONSE_SCHEMA),
}
