from __future__ import annotations

from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    BOOLEAN_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    STRING_SCHEMA,
    RouteContract,
    ok_envelope_with,
)

from .contract_schemas import (
    AUTH_RESPONSE_SCHEMA,
    EMAIL_REQUEST_RESPONSE_SCHEMA,
    ME_RESPONSE_SCHEMA,
    user_contract,
)
from .payloads import (
    WebAppEmailChangeConfirmPayload,
    WebAppEmailChangeCurrentPayload,
    WebAppEmailChangeNewPayload,
    WebAppEmailCodePayload,
    WebAppEmailPayload,
    WebAppExternalIdentityPayload,
    WebAppLanguagePayload,
    WebAppPasskeyCredentialPayload,
    WebAppPasskeyDeletePayload,
    WebAppSetPasswordPayload,
    WebAppTelegramAuthPayload,
)

ACCOUNT_ROUTE_CONTRACTS: dict[str, RouteContract] = {
    "account_email_change_current_request_route": user_contract(
        response_schema=EMAIL_REQUEST_RESPONSE_SCHEMA
    ),
    "account_email_change_current_verify_route": user_contract(
        request_model=WebAppEmailChangeCurrentPayload,
        response_schema=ok_envelope_with({"change_token": STRING_SCHEMA}),
    ),
    "account_email_change_new_request_route": user_contract(
        request_model=WebAppEmailChangeNewPayload,
        response_schema=EMAIL_REQUEST_RESPONSE_SCHEMA,
    ),
    "account_email_change_confirm_route": user_contract(
        request_model=WebAppEmailChangeConfirmPayload,
        response_schema=AUTH_RESPONSE_SCHEMA,
    ),
    "account_notification_email_route": user_contract(
        request_model=WebAppEmailPayload,
        response_schema=ok_envelope_with({"notification_email": STRING_SCHEMA}),
    ),
    "account_passkey_options_route": user_contract(
        response_schema=ok_envelope_with(
            {"options": {"type": "object", "additionalProperties": True}}
        )
    ),
    "account_passkey_register_route": user_contract(
        request_model=WebAppPasskeyCredentialPayload,
        response_schema=ok_envelope_with(),
    ),
    "account_passkey_delete_route": user_contract(
        request_model=WebAppPasskeyDeletePayload,
        response_schema=ok_envelope_with(),
    ),
    "external_identity_unlink_route": user_contract(
        request_model=WebAppExternalIdentityPayload,
        response_schema=ok_envelope_with(),
    ),
    "me_route": user_contract(response_schema=ME_RESPONSE_SCHEMA),
    "account_avatar_route": user_contract(
        response_schema=BINARY_RESPONSE_SCHEMA,
        response_content_type="image/jpeg",
    ),
    "account_language_route": user_contract(
        request_model=WebAppLanguagePayload,
        response_schema=ok_envelope_with({"language": STRING_SCHEMA}),
    ),
    "account_email_request_route": user_contract(
        request_model=WebAppEmailPayload,
        response_schema=ok_envelope_with(
            {
                "already_linked": BOOLEAN_SCHEMA,
                "retry_after": NULLABLE_INTEGER_SCHEMA,
                "email_code": STRING_SCHEMA,
                "code": STRING_SCHEMA,
            },
            required=[],
        ),
    ),
    "account_email_verify_route": user_contract(
        request_model=WebAppEmailCodePayload,
        response_schema=AUTH_RESPONSE_SCHEMA,
    ),
    "account_password_request_route": user_contract(
        response_schema=ok_envelope_with({"retry_after": NULLABLE_INTEGER_SCHEMA}, required=[]),
    ),
    "account_password_confirm_route": user_contract(
        request_model=WebAppSetPasswordPayload,
        response_schema=ok_envelope_with({"password_auth_enabled": BOOLEAN_SCHEMA}),
    ),
    "account_telegram_link_route": user_contract(
        request_model=WebAppTelegramAuthPayload,
        response_schema=AUTH_RESPONSE_SCHEMA,
    ),
}
