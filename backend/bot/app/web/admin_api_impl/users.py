from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    JSON_OBJECT_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    NUMBER_SCHEMA,
    STRING_SCHEMA,
    RouteContract,
    ok_envelope_with,
    register_contract,
    schema_ref,
)
from bot.app.web.webapp.contract_schemas import BALANCE_SCHEMA
from bot.app.web.webapp.notification_preference_schemas import (
    NotificationPreferencesOut,
    NotificationPreferencesPatchBody,
)
from db.dal import message_log_dal, payment_dal, subscription_dal, user_dal

from .schemas import (
    AdminSubscriptionOut,
    AdminTelegramNotificationsOut,
    AdminUserBalanceAdjustmentBody,
    AdminUserBalanceConversionBody,
    AdminUserBanBody,
    AdminUserExtendBody,
    AdminUserHwidDeviceLimitBody,
    AdminUserHwidDevicesOut,
    AdminUserMessageBody,
    AdminUserOut,
    AdminUserPremiumOverrideBody,
    AdminUserRegularTrafficOverrideBody,
    AdminUserTariffBody,
    AdminUserTrafficGrantBody,
    AdminUserTrafficStrategyBody,
    AdminUserTrialOut,
    AdminUserWithAvatarOut,
    PaymentOut,
)
from .squad_override_schemas import (
    AdminPanelSquadOverridesOut,
    AdminUserSquadOverridesPatchBody,
)
from .users_actions import (
    admin_user_ban_route,
    admin_user_delete_route,
    admin_user_extend_route,
    admin_user_hwid_device_limit_route,
    admin_user_message_preview_route,
    admin_user_message_route,
    admin_user_premium_override_route,
    admin_user_regular_traffic_override_route,
    admin_user_reset_trial_route,
    admin_user_subscription_reissue_route,
    admin_user_tariff_route,
    admin_user_telegram_profile_link_route,
    admin_user_traffic_grant_route,
    admin_user_traffic_strategy_route,
)
from .users_balance import (
    admin_user_balance_adjustment_route,
    admin_user_balance_conversion_route,
)
from .users_common import (
    _ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
    _ADMIN_USER_RESPONSE_SCHEMA,
    _bulk_user_avatar_keys,
    _serialize_admin_user_with_avatar,
)
from .users_detail import (
    _bulk_active_subscriptions_for_users,
    _bulk_user_payment_summaries,
    _bulk_user_referral_counts,
    _filter_and_sort_users,
    _serialize_trial_summary,
    admin_user_avatar_route,
    admin_user_detail_route,
    admin_user_referrals_route,
)
from .users_listing import (
    _bulk_user_statuses,
    _invalidate_after_admin_user_mutation,
    _load_admin_users_list_payload,
    _load_admin_users_list_payload_uncached,
    admin_users_list_route,
)
from .users_notification_preferences import admin_user_notification_preferences_route
from .users_squad_overrides import (
    admin_user_squad_overrides_refresh_route,
    admin_user_squad_overrides_route,
)

register_contract(
    "admin_users_list_route",
    RouteContract(
        models=(AdminUserWithAvatarOut,),
        response_schema=ok_envelope_with(
            {
                "users": {
                    "type": "array",
                    # Base admin user (+ avatar_url) enriched per-row by the list
                    # endpoint; panel_status_expired_at is only present for expired
                    # subscriptions, so it stays out of ``required``.
                    "items": {
                        "allOf": [
                            schema_ref(AdminUserWithAvatarOut),
                            {
                                "type": "object",
                                "properties": {
                                    "panel_status": NULLABLE_STRING_SCHEMA,
                                    "subscription_expires_at": NULLABLE_STRING_SCHEMA,
                                    "panel_status_expired_at": NULLABLE_STRING_SCHEMA,
                                    "premium_traffic": JSON_OBJECT_SCHEMA,
                                    "payments_total_amount": NUMBER_SCHEMA,
                                    "payments_count": INTEGER_SCHEMA,
                                    "payments_currency": NULLABLE_STRING_SCHEMA,
                                    "invited_users_count": INTEGER_SCHEMA,
                                    "user_balance_amount_minor": INTEGER_SCHEMA,
                                    "partner_balance_amount_minor": INTEGER_SCHEMA,
                                },
                                "required": [
                                    "panel_status",
                                    "subscription_expires_at",
                                    "premium_traffic",
                                    "payments_total_amount",
                                    "payments_count",
                                    "payments_currency",
                                    "invited_users_count",
                                    "user_balance_amount_minor",
                                    "partner_balance_amount_minor",
                                ],
                            },
                        ],
                    },
                },
                "page": INTEGER_SCHEMA,
                "page_size": INTEGER_SCHEMA,
                "total": INTEGER_SCHEMA,
                "user_balance_enabled": BOOLEAN_SCHEMA,
                "partner_balance_enabled": BOOLEAN_SCHEMA,
                "balance_currency": STRING_SCHEMA,
                "balance_currency_scale": INTEGER_SCHEMA,
            }
        ),
    ),
)
register_contract(
    "admin_user_detail_route",
    RouteContract(
        models=(
            AdminUserWithAvatarOut,
            AdminSubscriptionOut,
            AdminUserTrialOut,
            AdminUserHwidDevicesOut,
            PaymentOut,
            AdminPanelSquadOverridesOut,
            AdminTelegramNotificationsOut,
            NotificationPreferencesOut,
        ),
        response_schema=ok_envelope_with(
            {
                "user": schema_ref(AdminUserWithAvatarOut),
                "active_subscription": {
                    "anyOf": [schema_ref(AdminSubscriptionOut), {"type": "null"}]
                },
                "subscriptions": {"type": "array", "items": schema_ref(AdminSubscriptionOut)},
                "trial": schema_ref(AdminUserTrialOut),
                "total_paid": NUMBER_SCHEMA,
                "recent_payments": {"type": "array", "items": schema_ref(PaymentOut)},
                "log_count": INTEGER_SCHEMA,
                "balance": BALANCE_SCHEMA,
                "subscription_url": NULLABLE_STRING_SCHEMA,
                "panel_user_url": NULLABLE_STRING_SCHEMA,
                "install_share_url": NULLABLE_STRING_SCHEMA,
                "last_vpn_connected_at": NULLABLE_STRING_SCHEMA,
                "vpn_connection_status": STRING_SCHEMA,
                "hwid_devices": schema_ref(AdminUserHwidDevicesOut),
                "telegram_notifications": schema_ref(AdminTelegramNotificationsOut),
                "notification_preferences": schema_ref(NotificationPreferencesOut),
                "panel_squad_overrides": {
                    "anyOf": [schema_ref(AdminPanelSquadOverridesOut), {"type": "null"}]
                },
                "partner_attribution": {
                    "anyOf": [
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "partner_id",
                                "partner_user_id",
                                "display_label",
                                "public_client_id",
                                "source",
                                "attributed_at",
                            ],
                            "properties": {
                                "partner_id": INTEGER_SCHEMA,
                                "partner_user_id": NULLABLE_INTEGER_SCHEMA,
                                "display_label": STRING_SCHEMA,
                                "public_client_id": STRING_SCHEMA,
                                "source": STRING_SCHEMA,
                                "attributed_at": STRING_SCHEMA,
                            },
                        },
                        {"type": "null"},
                    ]
                },
                "referral": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["code", "bot_link", "webapp_link", "inviter", "invitees_total"],
                    "properties": {
                        "code": NULLABLE_STRING_SCHEMA,
                        "bot_link": NULLABLE_STRING_SCHEMA,
                        "webapp_link": NULLABLE_STRING_SCHEMA,
                        "inviter": {
                            "anyOf": [schema_ref(AdminUserWithAvatarOut), {"type": "null"}]
                        },
                        "invitees_total": INTEGER_SCHEMA,
                    },
                },
            }
        ),
    ),
)
register_contract(
    "admin_user_squad_overrides_route",
    RouteContract(
        request_model=AdminUserSquadOverridesPatchBody,
        response_schema=ok_envelope_with(
            {"panel_squad_overrides": schema_ref(AdminPanelSquadOverridesOut)}
        ),
        models=(AdminPanelSquadOverridesOut,),
    ),
)
register_contract(
    "admin_user_notification_preferences_route",
    RouteContract(
        request_model=NotificationPreferencesPatchBody,
        response_schema=ok_envelope_with(
            {"notification_preferences": schema_ref(NotificationPreferencesOut)}
        ),
        models=(NotificationPreferencesOut,),
    ),
)
register_contract(
    "admin_user_squad_overrides_refresh_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {"panel_squad_overrides": schema_ref(AdminPanelSquadOverridesOut)}
        ),
        models=(AdminPanelSquadOverridesOut,),
    ),
)
register_contract(
    "admin_user_referrals_route",
    RouteContract(
        models=(AdminUserWithAvatarOut,),
        response_schema=ok_envelope_with(
            {
                "user": schema_ref(AdminUserWithAvatarOut),
                "inviter": {"anyOf": [schema_ref(AdminUserWithAvatarOut), {"type": "null"}]},
                "invitees": {"type": "array", "items": schema_ref(AdminUserWithAvatarOut)},
                "total": INTEGER_SCHEMA,
                "page": INTEGER_SCHEMA,
                "page_size": INTEGER_SCHEMA,
            }
        ),
    ),
)
register_contract(
    "admin_user_avatar_route",
    RouteContract(response_schema=BINARY_RESPONSE_SCHEMA, response_content_type="image/jpeg"),
)
register_contract(
    "admin_user_balance_adjustment_route",
    RouteContract(
        request_model=AdminUserBalanceAdjustmentBody,
        response_schema=ok_envelope_with({"balance": BALANCE_SCHEMA}),
    ),
)
register_contract(
    "admin_user_balance_conversion_route",
    RouteContract(
        request_model=AdminUserBalanceConversionBody,
        response_schema=ok_envelope_with({"balance": BALANCE_SCHEMA}),
    ),
)
register_contract(
    "admin_user_ban_route",
    RouteContract(
        request_model=AdminUserBanBody,
        response_schema=_ADMIN_USER_RESPONSE_SCHEMA,
        models=(AdminUserOut,),
    ),
)
register_contract(
    "admin_user_message_route",
    RouteContract(
        request_model=AdminUserMessageBody,
        response_schema=ok_envelope_with(),
    ),
)
register_contract(
    "admin_user_message_preview_route",
    RouteContract(
        request_model=AdminUserMessageBody,
        response_schema=ok_envelope_with(),
    ),
)
register_contract(
    "admin_user_telegram_profile_link_route",
    RouteContract(response_schema=ok_envelope_with({"queued": BOOLEAN_SCHEMA})),
)
register_contract("admin_user_delete_route", RouteContract(response_schema=ok_envelope_with()))
register_contract("admin_user_reset_trial_route", RouteContract(response_schema=ok_envelope_with()))
register_contract(
    "admin_user_subscription_reissue_route",
    RouteContract(response_schema=ok_envelope_with({"email_sent": BOOLEAN_SCHEMA})),
)
register_contract(
    "admin_user_premium_override_route",
    RouteContract(
        request_model=AdminUserPremiumOverrideBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
        models=(AdminSubscriptionOut,),
    ),
)
register_contract(
    "admin_user_regular_traffic_override_route",
    RouteContract(
        request_model=AdminUserRegularTrafficOverrideBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
        models=(AdminSubscriptionOut,),
    ),
)
register_contract(
    "admin_user_traffic_strategy_route",
    RouteContract(
        request_model=AdminUserTrafficStrategyBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
        models=(AdminSubscriptionOut,),
    ),
)
register_contract(
    "admin_user_hwid_device_limit_route",
    RouteContract(
        request_model=AdminUserHwidDeviceLimitBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
        models=(AdminSubscriptionOut,),
    ),
)
register_contract(
    "admin_user_traffic_grant_route",
    RouteContract(
        request_model=AdminUserTrafficGrantBody,
        models=(AdminSubscriptionOut,),
        response_schema=ok_envelope_with(
            {
                "subscription": {"anyOf": [schema_ref(AdminSubscriptionOut), {"type": "null"}]},
                "grant": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "granted_bytes", "granted_gb"],
                    "properties": {
                        "kind": STRING_SCHEMA,
                        "granted_bytes": INTEGER_SCHEMA,
                        "granted_gb": NUMBER_SCHEMA,
                    },
                },
            },
            required=["grant"],
        ),
    ),
)
register_contract(
    "admin_user_extend_route",
    RouteContract(
        request_model=AdminUserExtendBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
        models=(AdminSubscriptionOut,),
    ),
)
register_contract(
    "admin_user_tariff_route",
    RouteContract(
        request_model=AdminUserTariffBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
        models=(AdminSubscriptionOut,),
    ),
)

__all__ = [
    "_bulk_active_subscriptions_for_users",
    "_bulk_user_avatar_keys",
    "_bulk_user_payment_summaries",
    "_bulk_user_referral_counts",
    "_bulk_user_statuses",
    "_filter_and_sort_users",
    "_invalidate_after_admin_user_mutation",
    "_load_admin_users_list_payload",
    "_load_admin_users_list_payload_uncached",
    "_serialize_admin_user_with_avatar",
    "_serialize_trial_summary",
    "admin_user_avatar_route",
    "admin_user_balance_adjustment_route",
    "admin_user_balance_conversion_route",
    "admin_user_ban_route",
    "admin_user_delete_route",
    "admin_user_detail_route",
    "admin_user_extend_route",
    "admin_user_hwid_device_limit_route",
    "admin_user_message_preview_route",
    "admin_user_message_route",
    "admin_user_notification_preferences_route",
    "admin_user_premium_override_route",
    "admin_user_referrals_route",
    "admin_user_regular_traffic_override_route",
    "admin_user_reset_trial_route",
    "admin_user_squad_overrides_refresh_route",
    "admin_user_squad_overrides_route",
    "admin_user_subscription_reissue_route",
    "admin_user_tariff_route",
    "admin_user_telegram_profile_link_route",
    "admin_user_traffic_grant_route",
    "admin_user_traffic_strategy_route",
    "admin_users_list_route",
    "message_log_dal",
    "payment_dal",
    "subscription_dal",
    "user_dal",
]
