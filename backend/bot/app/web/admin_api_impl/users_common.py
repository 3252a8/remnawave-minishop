from typing import Any, Dict, List

from schemas import AdminSubscriptionOut, AdminUserOut
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    NULLABLE_NUMBER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    STRING_SCHEMA,
    ok_envelope_with,
    schema_ref,
)
from bot.utils.ttl_cache import AsyncTTLCache
from db.models import User, UserTelegramAvatar

from .common import (
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
_ADMIN_USER_RESPONSE_SCHEMA = ok_envelope_with({"user": schema_ref(AdminUserOut)})
_ADMIN_SUBSCRIPTION_RESPONSE_SCHEMA = ok_envelope_with(
    {"subscription": schema_ref(AdminSubscriptionOut)}, required=[]
)


async def _bulk_user_avatar_keys(session: AsyncSession, user_ids: List[int]) -> Dict[int, str]:
    """Return ``{user_id: cache_key}`` for users with a cached Telegram avatar."""

    if not user_ids:
        return {}
    stmt = select(UserTelegramAvatar.user_id, UserTelegramAvatar.updated_at).where(
        UserTelegramAvatar.user_id.in_(user_ids)
    )
    rows = (await session.execute(stmt)).all()
    return {int(uid): (updated_at.isoformat() if updated_at else "") for uid, updated_at in rows}


def _serialize_admin_user_with_avatar(user: User, avatar_keys: Dict[int, str]) -> Dict[str, Any]:
    payload = _serialize_user(user)
    user_id = int(user.user_id)
    payload["avatar_url"] = (
        f"/api/admin/users/{user_id}/avatar?v={avatar_keys[user_id]}"
        if user_id in avatar_keys
        else None
    )
    return payload
