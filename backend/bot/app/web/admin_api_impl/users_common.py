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

_ADMIN_USERS_LIST_CACHES: Dict[tuple[int, int], AsyncTTLCache] = {}
_ADMIN_USER_MESSAGE_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "required": ["text"],
    "properties": {"text": STRING_SCHEMA},
}
_ADMIN_USER_BAN_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "required": ["banned"],
    "properties": {"banned": BOOLEAN_SCHEMA},
}
_ADMIN_USER_PREMIUM_OVERRIDE_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "unlimited": BOOLEAN_SCHEMA,
        "bonus_bytes": NULLABLE_INTEGER_SCHEMA,
        "bonus_gb": NULLABLE_NUMBER_SCHEMA,
    },
}
_ADMIN_USER_REGULAR_TRAFFIC_OVERRIDE_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "unlimited": BOOLEAN_SCHEMA,
        "regular_bonus_bytes": NULLABLE_INTEGER_SCHEMA,
        "regular_bonus_gb": NULLABLE_NUMBER_SCHEMA,
    },
}
_ADMIN_USER_HWID_LIMIT_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "unlimited": BOOLEAN_SCHEMA,
        "use_default": BOOLEAN_SCHEMA,
        "reset_to_default": BOOLEAN_SCHEMA,
        "hwid_device_limit": NULLABLE_INTEGER_SCHEMA,
        "limit": NULLABLE_INTEGER_SCHEMA,
    },
}
_ADMIN_USER_TRAFFIC_GRANT_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "kind": {"type": "string", "enum": ["regular", "premium"]},
        "bytes": NULLABLE_INTEGER_SCHEMA,
        "gb": NULLABLE_NUMBER_SCHEMA,
    },
}
_ADMIN_USER_EXTEND_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "required": ["days"],
    "properties": {
        "days": INTEGER_SCHEMA,
        "tariff_key": NULLABLE_STRING_SCHEMA,
        "extend_hwid_devices": BOOLEAN_SCHEMA,
    },
}
_ADMIN_USER_TARIFF_BODY_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "required": ["tariff_key"],
    "properties": {"tariff_key": STRING_SCHEMA},
}
_ADMIN_USER_RESPONSE_SCHEMA = ok_envelope_with({"user": loose_object_schema()})
_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA = ok_envelope_with(
    {"subscription": loose_object_schema()}, required=[]
)
