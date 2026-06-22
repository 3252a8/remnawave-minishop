import hashlib
from html import escape as html_escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.orm import aliased

from bot.app.web.webapp.cache_helpers import invalidate_webapp_user_caches
from bot.infra.redis import cache_delete_pattern, redis_key
from bot.utils.ttl_cache import AsyncTTLCache

from ._runtime import (
    BINARY_RESPONSE_SCHEMA,
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    NULLABLE_NUMBER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    NUMBER_SCHEMA,
    STRING_SCHEMA,
    AdminUserBanBody,
    AdminUserExtendBody,
    AdminUserHwidDeviceLimitBody,
    AdminUserMessageBody,
    AdminUserPremiumOverrideBody,
    AdminUserRegularTrafficOverrideBody,
    AdminUserTariffBody,
    AdminUserTrafficGrantBody,
    Any,
    AsyncSession,
    Dict,
    Float,
    List,
    MessageContent,
    Optional,
    Payment,
    ReferralService,
    RouteContract,
    Settings,
    Subscription,
    Tuple,
    User,
    UserTelegramAvatar,
    and_,
    case,
    cast,
    datetime,
    get_queue_manager,
    json,
    logger,
    loose_array_schema,
    loose_object_schema,
    message_log_dal,
    ok_envelope_with,
    or_,
    parse_body_or_400,
    payment_dal,
    register_contract,
    sa_func,
    select,
    send_message_via_queue,
    sessionmaker,
    subscription_dal,
    timezone,
    user_dal,
    web,
)
from .auth import _require_admin_user_id
from .common import (
    _build_admin_webapp_referral_link,
    _error,
    _ok,
    _panel_user_connection_activity,
    _premium_traffic_list_payload,
    _serialize_payment,
    _serialize_subscription,
    _serialize_user,
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
)
from .users_detail import (
    _bulk_user_payment_summaries,
    _bulk_user_referral_counts,
    _filter_and_sort_users,
    _serialize_trial_summary,
    admin_user_avatar_route,
    admin_user_detail_route,
    admin_user_referrals_route,
)
from .users_listing import (
    _bulk_user_avatar_keys,
    _invalidate_after_admin_user_mutation,
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
        response_schema=ok_envelope_with(
            {
                "user": loose_object_schema(),
                "active_subscription": loose_object_schema(),
                "subscriptions": loose_array_schema(),
                "trial": loose_object_schema(),
                "total_paid": NUMBER_SCHEMA,
                "recent_payments": loose_array_schema(),
                "log_count": INTEGER_SCHEMA,
                "subscription_url": NULLABLE_STRING_SCHEMA,
                "last_vpn_connected_at": NULLABLE_STRING_SCHEMA,
                "vpn_connection_status": STRING_SCHEMA,
                "referral": loose_object_schema(),
            }
        )
    ),
)
register_contract(
    "admin_user_referrals_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "user": loose_object_schema(),
                "inviter": loose_object_schema(),
                "invitees": loose_array_schema(),
                "total": INTEGER_SCHEMA,
                "page": INTEGER_SCHEMA,
                "page_size": INTEGER_SCHEMA,
            }
        )
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
    ),
)
register_contract(
    "admin_user_regular_traffic_override_route",
    RouteContract(
        request_model=AdminUserRegularTrafficOverrideBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
    ),
)
register_contract(
    "admin_user_hwid_device_limit_route",
    RouteContract(
        request_model=AdminUserHwidDeviceLimitBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
    ),
)
register_contract(
    "admin_user_traffic_grant_route",
    RouteContract(
        request_model=AdminUserTrafficGrantBody,
        response_schema=ok_envelope_with(
            {"subscription": loose_object_schema(), "grant": loose_object_schema()},
            required=["grant"],
        ),
    ),
)
register_contract(
    "admin_user_extend_route",
    RouteContract(
        request_model=AdminUserExtendBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
    ),
)
register_contract(
    "admin_user_tariff_route",
    RouteContract(
        request_model=AdminUserTariffBody,
        response_schema=_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA,
    ),
)

