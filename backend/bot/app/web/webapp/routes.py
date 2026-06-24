from typing import Any

from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    JSON_OBJECT_SCHEMA,
    USER_SECURITY,
    RouteContract,
    loose_array_schema,
    loose_object_schema,
    ok_envelope_with,
    register_contract,
    schema_ref,
)
from bot.app.web.support_schemas import SupportCountsOut, SupportMessageOut, SupportTicketOut

from ._runtime import (
    WEBAPP_DEFAULT_LOGO_PATH,
    WEBAPP_FAVICON_PATH,
    WEBAPP_LOGO_PROXY_PATH,
    WEBAPP_UPLOADED_LOGO_PATH,
    setup_admin_routes,
    web,
)
from .account import (
    account_avatar_route,
    account_email_request_route,
    account_email_verify_route,
    account_language_route,
    account_password_confirm_route,
    account_password_request_route,
    account_telegram_link_route,
    me_route,
)
from .assets import (
    admin_css_asset_route,
    admin_js_asset_route,
    app_deeplink_route,
    bootstrap_route,
    css_asset_route,
    health_route,
    i18n_route,
    index_route,
    js_asset_route,
    robots_txt_route,
    theme_asset_route,
    theme_css_asset_route,
    webapp_current_favicon_route,
    webapp_default_logo_route,
    webapp_favicon_route,
    webapp_logo_route,
    webapp_uploaded_logo_route,
)
from .auth import (
    auth_token_route,
    email_auth_magic_route,
    email_auth_request_route,
    email_auth_verify_route,
    email_password_auth_route,
    logout_route,
    referral_welcome_bonus_claim_route,
    telegram_oauth_callback_route,
    telegram_oauth_nonce_route,
    telegram_oauth_start_route,
)
from .billing import (
    activate_trial_route,
    apply_promo_route,
    create_payment_route,
    device_topup_options_route,
    payment_status_route,
    subscription_auto_renew_route,
    tariff_change_options_route,
    tariff_change_payment_route,
    tariff_change_route,
    tariff_topup_options_route,
)
from .devices import (
    WebAppDeviceOut,
    devices_route,
    disconnect_device_route,
)
from .guides import (
    public_subscription_guides_route,
    subscription_guides_route,
)
from .payloads import (
    CreateTicketPayload,
    TicketReplyPayload,
    WebAppAutoRenewPayload,
    WebAppDeviceDisconnectPayload,
    WebAppEmailCodeAuthPayload,
    WebAppEmailCodePayload,
    WebAppEmailMagicAuthPayload,
    WebAppEmailPasswordPayload,
    WebAppEmailPayload,
    WebAppEmailRequestPayload,
    WebAppLanguagePayload,
    WebAppPaymentCreatePayload,
    WebAppPromoApplyPayload,
    WebAppSetPasswordPayload,
    WebAppTariffChangePayload,
    WebAppTelegramAuthPayload,
)
from .support import (
    support_create_ticket_route,
    support_ticket_detail_route,
    support_ticket_read_route,
    support_ticket_reply_route,
    support_tickets_route,
    support_unread_route,
)
from .telegram_notifications import (
    account_telegram_notifications_probe_route,
)

_STRING_SCHEMA = {"type": "string"}
_INTEGER_SCHEMA = {"type": "integer"}
_NUMBER_SCHEMA = {"type": "number"}
_BOOLEAN_SCHEMA = {"type": "boolean"}
_NULLABLE_STRING_SCHEMA = {"type": ["string", "null"]}
_NULLABLE_INTEGER_SCHEMA = {"type": ["integer", "null"]}
_NULLABLE_NUMBER_SCHEMA = {"type": ["number", "null"]}

_TELEGRAM_AUTH_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "init_data": _STRING_SCHEMA,
        "id_token": _STRING_SCHEMA,
        "nonce": _STRING_SCHEMA,
        "auth_data": JSON_OBJECT_SCHEMA,
        "referral_code": _STRING_SCHEMA,
        "start_param": _STRING_SCHEMA,
    },
}
_PROMO_APPLY_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "required": ["code"],
    "properties": {"code": _STRING_SCHEMA},
}


def _public_contract(**kwargs: Any) -> RouteContract:
    return RouteContract(**kwargs)


def _user_contract(**kwargs: Any) -> RouteContract:
    return RouteContract(security=USER_SECURITY, **kwargs)


_AUTH_RESPONSE_SCHEMA = ok_envelope_with(
    {
        "user_id": _NULLABLE_INTEGER_SCHEMA,
        "telegram_id": _NULLABLE_INTEGER_SCHEMA,
        "csrf_token": _STRING_SCHEMA,
        "account_merge": loose_object_schema(),
    },
    required=[],
)
_EMAIL_REQUEST_RESPONSE_SCHEMA = ok_envelope_with(
    {
        "retry_after": _NULLABLE_INTEGER_SCHEMA,
        "email_code": _STRING_SCHEMA,
        "code": _STRING_SCHEMA,
    },
    required=[],
)
_PAYMENT_RESPONSE_SCHEMA = ok_envelope_with(
    {
        "payment_id": _INTEGER_SCHEMA,
        "status": _STRING_SCHEMA,
        "paid": _BOOLEAN_SCHEMA,
        "payment": loose_object_schema(),
        "payment_url": _NULLABLE_STRING_SCHEMA,
        "confirmation_url": _NULLABLE_STRING_SCHEMA,
    },
    required=[],
)
_PLAN_OPTIONS_RESPONSE_SCHEMA = ok_envelope_with(
    {
        "plans": loose_array_schema(),
        "tariff_key": _STRING_SCHEMA,
        "tariff_name": _STRING_SCHEMA,
    },
    required=[],
)

_ROUTE_CONTRACTS = {
    "telegram_oauth_nonce_route": _public_contract(
        response_schema=ok_envelope_with(
            {
                "nonce": _STRING_SCHEMA,
                "client_id": _STRING_SCHEMA,
                "request_access": _STRING_SCHEMA,
            }
        )
    ),
    "auth_token_route": _public_contract(
        request_model=WebAppTelegramAuthPayload,
        response_schema=_AUTH_RESPONSE_SCHEMA,
    ),
    "email_auth_request_route": _public_contract(
        request_model=WebAppEmailRequestPayload,
        response_schema=_EMAIL_REQUEST_RESPONSE_SCHEMA,
    ),
    "email_auth_verify_route": _public_contract(
        request_model=WebAppEmailCodeAuthPayload,
        response_schema=_AUTH_RESPONSE_SCHEMA,
    ),
    "email_auth_magic_route": _public_contract(
        request_model=WebAppEmailMagicAuthPayload,
        response_schema=_AUTH_RESPONSE_SCHEMA,
    ),
    "email_password_auth_route": _public_contract(
        request_model=WebAppEmailPasswordPayload,
        response_schema=_AUTH_RESPONSE_SCHEMA,
    ),
    "logout_route": _public_contract(response_schema=ok_envelope_with()),
    "bootstrap_route": _public_contract(
        response_schema=ok_envelope_with(
            {"config": loose_object_schema(), "i18n": loose_object_schema()},
        )
    ),
    "i18n_route": _public_contract(
        response_schema=ok_envelope_with(
            {"scope": _STRING_SCHEMA, "i18n": loose_object_schema()},
        )
    ),
    "me_route": _user_contract(response_schema=ok_envelope_with(required=[])),
    "subscription_guides_route": _user_contract(
        response_schema=ok_envelope_with(
            {
                "enabled": _BOOLEAN_SCHEMA,
                "config": loose_object_schema(),
                "source": _NULLABLE_STRING_SCHEMA,
            },
            required=["enabled"],
        )
    ),
    "public_subscription_guides_route": _public_contract(
        response_schema=ok_envelope_with(
            {
                "enabled": _BOOLEAN_SCHEMA,
                "config": loose_object_schema(),
                "source": _NULLABLE_STRING_SCHEMA,
                "subscription": loose_object_schema(),
            },
            required=["enabled"],
        )
    ),
    "account_avatar_route": _user_contract(
        response_schema=BINARY_RESPONSE_SCHEMA,
        response_content_type="image/jpeg",
    ),
    "account_language_route": _user_contract(
        request_model=WebAppLanguagePayload,
        response_schema=ok_envelope_with({"language": _STRING_SCHEMA}),
    ),
    "account_email_request_route": _user_contract(
        request_model=WebAppEmailPayload,
        response_schema=ok_envelope_with(
            {
                "already_linked": _BOOLEAN_SCHEMA,
                "retry_after": _NULLABLE_INTEGER_SCHEMA,
                "email_code": _STRING_SCHEMA,
                "code": _STRING_SCHEMA,
            },
            required=[],
        ),
    ),
    "account_email_verify_route": _user_contract(
        request_model=WebAppEmailCodePayload,
        response_schema=_AUTH_RESPONSE_SCHEMA,
    ),
    "account_password_request_route": _user_contract(
        response_schema=ok_envelope_with({"retry_after": _NULLABLE_INTEGER_SCHEMA}, required=[]),
    ),
    "account_password_confirm_route": _user_contract(
        request_model=WebAppSetPasswordPayload,
        response_schema=ok_envelope_with({"password_auth_enabled": _BOOLEAN_SCHEMA}),
    ),
    "account_telegram_link_route": _user_contract(
        request_model=WebAppTelegramAuthPayload,
        response_schema=_AUTH_RESPONSE_SCHEMA,
    ),
    "account_telegram_notifications_probe_route": _user_contract(
        response_schema=ok_envelope_with({"telegram_notifications": loose_object_schema()}),
    ),
    "referral_welcome_bonus_claim_route": _user_contract(
        response_schema=ok_envelope_with(
            {
                "claimed": _BOOLEAN_SCHEMA,
                "end_date": _NULLABLE_STRING_SCHEMA,
                "end_date_text": _NULLABLE_STRING_SCHEMA,
            }
        )
    ),
    "apply_promo_route": _user_contract(
        request_model=WebAppPromoApplyPayload,
        response_schema=ok_envelope_with(
            {
                "end_date": _NULLABLE_STRING_SCHEMA,
                "end_date_text": _NULLABLE_STRING_SCHEMA,
            },
            required=[],
        ),
    ),
    "activate_trial_route": _user_contract(
        response_schema=ok_envelope_with(
            {
                "activated": _BOOLEAN_SCHEMA,
                "days": _INTEGER_SCHEMA,
                "end_date": _NULLABLE_STRING_SCHEMA,
                "end_date_text": _NULLABLE_STRING_SCHEMA,
                "traffic_gb": _NULLABLE_NUMBER_SCHEMA,
                "config_link": _NULLABLE_STRING_SCHEMA,
                "connect_url": _NULLABLE_STRING_SCHEMA,
            }
        )
    ),
    "subscription_auto_renew_route": _user_contract(
        request_model=WebAppAutoRenewPayload,
        response_schema=ok_envelope_with(
            {
                "auto_renew_enabled": _BOOLEAN_SCHEMA,
                "provider": _STRING_SCHEMA,
                "provider_label": _STRING_SCHEMA,
            }
        ),
    ),
    "devices_route": _user_contract(
        models=(WebAppDeviceOut,),
        response_schema=ok_envelope_with(
            {
                "enabled": _BOOLEAN_SCHEMA,
                "subscription_active": _BOOLEAN_SCHEMA,
                "current_devices": _INTEGER_SCHEMA,
                "max_devices": _NULLABLE_INTEGER_SCHEMA,
                "max_devices_label": _NULLABLE_STRING_SCHEMA,
                "devices": {"type": "array", "items": schema_ref(WebAppDeviceOut)},
            },
            required=[],
        ),
    ),
    "disconnect_device_route": _user_contract(
        request_model=WebAppDeviceDisconnectPayload,
        response_schema=ok_envelope_with(),
    ),
    "device_topup_options_route": _user_contract(response_schema=_PLAN_OPTIONS_RESPONSE_SCHEMA),
    "support_tickets_route": _user_contract(
        response_schema=ok_envelope_with(
            {
                "tickets": {
                    "type": "array",
                    "items": schema_ref(SupportTicketOut),
                },
                "counts": schema_ref(SupportCountsOut),
            }
        ),
        models=(SupportCountsOut, SupportTicketOut),
    ),
    "support_create_ticket_route": _user_contract(
        request_model=CreateTicketPayload,
        response_schema=ok_envelope_with({"ticket": schema_ref(SupportTicketOut)}),
        models=(CreateTicketPayload, SupportTicketOut),
    ),
    "support_ticket_detail_route": _user_contract(
        response_schema=ok_envelope_with(
            {
                "ticket": schema_ref(SupportTicketOut),
                "messages": {
                    "type": "array",
                    "items": schema_ref(SupportMessageOut),
                },
            }
        ),
        models=(SupportMessageOut, SupportTicketOut),
    ),
    "support_ticket_reply_route": _user_contract(
        request_model=TicketReplyPayload,
        response_schema=ok_envelope_with(
            {
                "ticket": schema_ref(SupportTicketOut),
                "message": schema_ref(SupportMessageOut),
            }
        ),
        models=(SupportMessageOut, SupportTicketOut, TicketReplyPayload),
    ),
    "support_ticket_read_route": _user_contract(response_schema=ok_envelope_with()),
    "support_unread_route": _user_contract(
        response_schema=ok_envelope_with({"unread": _INTEGER_SCHEMA}),
    ),
    "tariff_topup_options_route": _user_contract(response_schema=_PLAN_OPTIONS_RESPONSE_SCHEMA),
    "tariff_change_options_route": _user_contract(
        response_schema=ok_envelope_with(
            {"current": loose_object_schema(), "targets": loose_array_schema()},
        )
    ),
    "tariff_change_route": _user_contract(
        request_model=WebAppTariffChangePayload,
        response_schema=ok_envelope_with({"subscription": loose_object_schema()}, required=[]),
    ),
    "tariff_change_payment_route": _user_contract(
        request_model=WebAppPaymentCreatePayload,
        response_schema=_PAYMENT_RESPONSE_SCHEMA,
    ),
    "create_payment_route": _user_contract(
        request_model=WebAppPaymentCreatePayload,
        response_schema=_PAYMENT_RESPONSE_SCHEMA,
    ),
    "payment_status_route": _user_contract(response_schema=_PAYMENT_RESPONSE_SCHEMA),
}

for _handler_name, _contract in _ROUTE_CONTRACTS.items():
    register_contract(_handler_name, _contract)


def setup_subscription_webapp_routes(app: web.Application) -> None:
    app.router.add_get("/robots.txt", robots_txt_route)
    app.router.add_get("/", index_route)
    app.router.add_get("/login/password", index_route)
    app.router.add_get("/home", index_route)
    app.router.add_get("/install", index_route)
    app.router.add_get("/trial", index_route)
    app.router.add_get("/open-app", app_deeplink_route)
    app.router.add_get(r"/s/{share_token:[a-f0-9]{32}}", index_route)
    app.router.add_get("/invite", index_route)
    app.router.add_get("/devices", index_route)
    app.router.add_get("/settings", index_route)
    app.router.add_get("/support", index_route)
    app.router.add_get("/support/{ticket_id:\\d+}", index_route)
    app.router.add_get("/admin", index_route)
    app.router.add_get(
        (
            "/admin/{section:stats|users|payments|promos|ads|broadcast|logs|tariffs|"
            "appearance|settings|translations|support|backups}"
        ),
        index_route,
    )
    app.router.add_get(r"/admin/settings/{settings_path:.+}", index_route)
    app.router.add_get("/admin/users/{user_id:-?[0-9]+}", index_route)
    app.router.add_get("/admin/payments/users/{user_id:-?[0-9]+}", index_route)
    app.router.add_get("/admin/payments/{payment_id:\\d+}", index_route)
    app.router.add_get("/admin/support/{ticket_id:\\d+}", index_route)
    app.router.add_get("/auth/telegram/start", telegram_oauth_start_route)
    app.router.add_get("/auth/telegram/callback", telegram_oauth_callback_route)
    app.router.add_get("/health", health_route)
    app.router.add_get("/favicon.ico", webapp_current_favicon_route)
    app.router.add_get("/apple-touch-icon.png", webapp_current_favicon_route)
    app.router.add_get("/apple-touch-icon-precomposed.png", webapp_current_favicon_route)
    app.router.add_get("/icon-192.png", webapp_current_favicon_route)
    app.router.add_get("/icon-512.png", webapp_current_favicon_route)
    app.router.add_get(WEBAPP_DEFAULT_LOGO_PATH, webapp_default_logo_route)
    app.router.add_get(WEBAPP_LOGO_PROXY_PATH, webapp_logo_route)
    app.router.add_get(
        rf"{WEBAPP_UPLOADED_LOGO_PATH}/{{filename:[A-Za-z0-9_.-]+}}",
        webapp_uploaded_logo_route,
    )
    app.router.add_get(
        rf"{WEBAPP_FAVICON_PATH}/{{digest:[0-9a-f]{{16}}}}/{{filename:[A-Za-z0-9_.-]+}}",
        webapp_favicon_route,
    )
    app.router.add_get("/subscription_webapp.{asset_hash:[0-9a-f]{8}}.css", css_asset_route)
    app.router.add_get("/subscription_webapp.css", css_asset_route)
    app.router.add_get(
        "/subscription_webapp_admin.{asset_hash:[0-9a-f]{8}}.css",
        admin_css_asset_route,
    )
    app.router.add_get("/subscription_webapp_admin.css", admin_css_asset_route)
    app.router.add_get(r"/webapp-theme-css/{path:.+}", theme_css_asset_route)
    app.router.add_get(r"/webapp-theme-assets/{path:.+}", theme_asset_route)
    app.router.add_get("/subscription_webapp.min.{asset_hash}.js", js_asset_route)
    app.router.add_get("/subscription_webapp.js", js_asset_route)
    app.router.add_get("/subscription_webapp_admin.min.{asset_hash}.js", admin_js_asset_route)
    app.router.add_get("/subscription_webapp_admin.js", admin_js_asset_route)
    app.router.add_post("/api/auth/telegram/nonce", telegram_oauth_nonce_route)
    app.router.add_post("/api/auth/token", auth_token_route)
    app.router.add_post("/api/auth/email/request", email_auth_request_route)
    app.router.add_post("/api/auth/email/verify", email_auth_verify_route)
    app.router.add_post("/api/auth/email/magic", email_auth_magic_route)
    app.router.add_post("/api/auth/email/password", email_password_auth_route)
    app.router.add_post("/api/auth/logout", logout_route)
    app.router.add_get("/api/bootstrap", bootstrap_route)
    app.router.add_get("/api/i18n", i18n_route)
    app.router.add_get("/api/me", me_route)
    app.router.add_get("/api/subscription-guides", subscription_guides_route)
    app.router.add_get(
        r"/api/subscription-guides/public/{share_token:[a-f0-9]{32}}",
        public_subscription_guides_route,
    )
    app.router.add_get("/api/account/avatar", account_avatar_route)
    app.router.add_post("/api/account/language", account_language_route)
    app.router.add_post("/api/account/email/request", account_email_request_route)
    app.router.add_post("/api/account/email/verify", account_email_verify_route)
    app.router.add_post("/api/account/password/request", account_password_request_route)
    app.router.add_post("/api/account/password/confirm", account_password_confirm_route)
    app.router.add_post("/api/account/telegram/link", account_telegram_link_route)
    app.router.add_post(
        "/api/account/telegram/notifications/probe",
        account_telegram_notifications_probe_route,
    )
    app.router.add_post("/api/referral/welcome-bonus/claim", referral_welcome_bonus_claim_route)
    app.router.add_post("/api/promo/apply", apply_promo_route)
    app.router.add_post("/api/trial/activate", activate_trial_route)
    app.router.add_post("/api/subscription/auto-renew", subscription_auto_renew_route)
    app.router.add_get("/api/devices", devices_route)
    app.router.add_post("/api/devices/disconnect", disconnect_device_route)
    app.router.add_get("/api/devices/topup-options", device_topup_options_route)
    app.router.add_get("/api/support/tickets", support_tickets_route)
    app.router.add_post("/api/support/tickets", support_create_ticket_route)
    app.router.add_get("/api/support/tickets/{id:\\d+}", support_ticket_detail_route)
    app.router.add_post("/api/support/tickets/{id:\\d+}/messages", support_ticket_reply_route)
    app.router.add_post("/api/support/tickets/{id:\\d+}/read", support_ticket_read_route)
    app.router.add_get("/api/support/unread", support_unread_route)
    app.router.add_get("/api/tariffs/topup-options", tariff_topup_options_route)
    app.router.add_get("/api/tariffs/change-options", tariff_change_options_route)
    app.router.add_post("/api/tariffs/change", tariff_change_route)
    app.router.add_post("/api/tariffs/change-payment", tariff_change_payment_route)
    app.router.add_post("/api/payments", create_payment_route)
    app.router.add_get("/api/payments/{payment_id}", payment_status_route)
    setup_admin_routes(app)
