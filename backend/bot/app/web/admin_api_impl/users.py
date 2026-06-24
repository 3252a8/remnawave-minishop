from db.dal import message_log_dal, payment_dal, subscription_dal, user_dal

from ._runtime import (
    BINARY_RESPONSE_SCHEMA,
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    NUMBER_SCHEMA,
    STRING_SCHEMA,
    AdminSubscriptionOut,
    AdminUserBanBody,
    AdminUserExtendBody,
    AdminUserHwidDeviceLimitBody,
    AdminUserMessageBody,
    AdminUserOut,
    AdminUserPremiumOverrideBody,
    AdminUserRegularTrafficOverrideBody,
    AdminUserTariffBody,
    AdminUserTrafficGrantBody,
    AdminUserTrialOut,
    AdminUserWithAvatarOut,
    PaymentOut,
    RouteContract,
    loose_array_schema,
    ok_envelope_with,
    register_contract,
    schema_ref,
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
    admin_user_tariff_route,
    admin_user_telegram_profile_link_route,
    admin_user_traffic_grant_route,
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

register_contract(
    "admin_users_list_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "users": loose_array_schema(),
                "page": INTEGER_SCHEMA,
                "page_size": INTEGER_SCHEMA,
                "total": INTEGER_SCHEMA,
            }
        )
    ),
)
register_contract(
    "admin_user_detail_route",
    RouteContract(
        models=(AdminUserWithAvatarOut, AdminSubscriptionOut, AdminUserTrialOut, PaymentOut),
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
                "subscription_url": NULLABLE_STRING_SCHEMA,
                "last_vpn_connected_at": NULLABLE_STRING_SCHEMA,
                "vpn_connection_status": STRING_SCHEMA,
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
    "admin_user_ban_route",
    "admin_user_delete_route",
    "admin_user_detail_route",
    "admin_user_extend_route",
    "admin_user_hwid_device_limit_route",
    "admin_user_message_preview_route",
    "admin_user_message_route",
    "admin_user_premium_override_route",
    "admin_user_referrals_route",
    "admin_user_regular_traffic_override_route",
    "admin_user_reset_trial_route",
    "admin_user_tariff_route",
    "admin_user_telegram_profile_link_route",
    "admin_user_traffic_grant_route",
    "admin_users_list_route",
    "message_log_dal",
    "payment_dal",
    "subscription_dal",
    "user_dal",
]
