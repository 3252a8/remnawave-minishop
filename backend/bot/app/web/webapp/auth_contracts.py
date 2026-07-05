from __future__ import annotations

from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    NULLABLE_NUMBER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    STRING_SCHEMA,
    RouteContract,
    ok_envelope_with,
)

from .contract_schemas import (
    AUTH_RESPONSE_SCHEMA,
    EMAIL_REQUEST_RESPONSE_SCHEMA,
    public_contract,
    user_contract,
)
from .payloads import (
    WebAppEmailCodeAuthPayload,
    WebAppEmailMagicAuthPayload,
    WebAppEmailPasswordPayload,
    WebAppEmailRequestPayload,
    WebAppPromoApplyPayload,
    WebAppTelegramAuthPayload,
)

AUTH_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "telegram_oauth_nonce_route": public_contract(
        response_schema=ok_envelope_with(
            {
                "nonce": STRING_SCHEMA,
                "client_id": STRING_SCHEMA,
                "request_access": STRING_SCHEMA,
            }
        )
    ),
    "auth_token_route": public_contract(
        request_model=WebAppTelegramAuthPayload,
        response_schema=AUTH_RESPONSE_SCHEMA,
    ),
    "email_auth_request_route": public_contract(
        request_model=WebAppEmailRequestPayload,
        response_schema=EMAIL_REQUEST_RESPONSE_SCHEMA,
    ),
    "email_auth_verify_route": public_contract(
        request_model=WebAppEmailCodeAuthPayload,
        response_schema=AUTH_RESPONSE_SCHEMA,
    ),
    "email_auth_magic_route": public_contract(
        request_model=WebAppEmailMagicAuthPayload,
        response_schema=AUTH_RESPONSE_SCHEMA,
    ),
    "email_password_auth_route": public_contract(
        request_model=WebAppEmailPasswordPayload,
        response_schema=AUTH_RESPONSE_SCHEMA,
    ),
    "logout_route": public_contract(response_schema=ok_envelope_with()),
    "referral_welcome_bonus_claim_route": user_contract(
        response_schema=ok_envelope_with(
            {
                "claimed": BOOLEAN_SCHEMA,
                "end_date": NULLABLE_STRING_SCHEMA,
                "end_date_text": NULLABLE_STRING_SCHEMA,
            }
        )
    ),
    "promo_status_route": user_contract(
        request_model=WebAppPromoApplyPayload,
        response_schema=ok_envelope_with(
            {
                "status": STRING_SCHEMA,
                "code": STRING_SCHEMA,
                "message": STRING_SCHEMA,
                "effect_summary": STRING_SCHEMA,
                "applies_to": STRING_SCHEMA,
                "min_subscription_months": NULLABLE_INTEGER_SCHEMA,
                "min_traffic_gb": NULLABLE_NUMBER_SCHEMA,
                "bonus_days": INTEGER_SCHEMA,
                "end_date_text": NULLABLE_STRING_SCHEMA,
            },
            required=["status", "code"],
        ),
    ),
    "apply_promo_route": user_contract(
        request_model=WebAppPromoApplyPayload,
        response_schema=ok_envelope_with(
            {
                "end_date": NULLABLE_STRING_SCHEMA,
                "end_date_text": NULLABLE_STRING_SCHEMA,
                "requires_checkout": BOOLEAN_SCHEMA,
                "code": STRING_SCHEMA,
                "effect_summary": STRING_SCHEMA,
                "applies_to": STRING_SCHEMA,
                "min_subscription_months": NULLABLE_INTEGER_SCHEMA,
                "min_traffic_gb": NULLABLE_NUMBER_SCHEMA,
            },
            required=[],
        ),
    ),
    "activate_trial_route": user_contract(
        response_schema=ok_envelope_with(
            {
                "activated": BOOLEAN_SCHEMA,
                "days": INTEGER_SCHEMA,
                "end_date": NULLABLE_STRING_SCHEMA,
                "end_date_text": NULLABLE_STRING_SCHEMA,
                "traffic_gb": {"type": ["number", "null"]},
                "config_link": NULLABLE_STRING_SCHEMA,
                "connect_url": NULLABLE_STRING_SCHEMA,
            }
        )
    ),
}
