from __future__ import annotations

from typing import Any

from bot.app.web.route_contracts import (
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    NULLABLE_NUMBER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    NUMBER_SCHEMA,
    STRING_SCHEMA,
    USER_SECURITY,
    RouteContract,
    ok_envelope_with,
)

STRING_ARRAY_SCHEMA: dict[str, Any] = {"type": "array", "items": STRING_SCHEMA}
NUMBER_ARRAY_SCHEMA: dict[str, Any] = {"type": "array", "items": NUMBER_SCHEMA}
OBJECT_MAP_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": True}


def public_contract(**kwargs: Any) -> RouteContract:
    return RouteContract(**kwargs)


def user_contract(**kwargs: Any) -> RouteContract:
    return RouteContract(security=USER_SECURITY, **kwargs)


ACCOUNT_MERGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "merged",
        "language",
        "primary_user_id",
        "removed_user_id",
        "primary_panel_user_uuid",
        "removed_panel_user_uuid",
        "final_end_date",
        "final_end_date_text",
    ],
    "properties": {
        "merged": BOOLEAN_SCHEMA,
        "language": STRING_SCHEMA,
        "primary_user_id": INTEGER_SCHEMA,
        "removed_user_id": INTEGER_SCHEMA,
        "primary_panel_user_uuid": NULLABLE_STRING_SCHEMA,
        "removed_panel_user_uuid": NULLABLE_STRING_SCHEMA,
        "final_end_date": NULLABLE_STRING_SCHEMA,
        "final_end_date_text": NULLABLE_STRING_SCHEMA,
    },
}
AUTH_RESPONSE_SCHEMA: dict[str, Any] = ok_envelope_with(
    {
        "user_id": NULLABLE_INTEGER_SCHEMA,
        "telegram_id": NULLABLE_INTEGER_SCHEMA,
        "token": STRING_SCHEMA,
        "csrf_token": STRING_SCHEMA,
        "account_merge": ACCOUNT_MERGE_SCHEMA,
    },
    required=["token", "csrf_token"],
)
EMAIL_REQUEST_RESPONSE_SCHEMA: dict[str, Any] = ok_envelope_with(
    {
        "retry_after": NULLABLE_INTEGER_SCHEMA,
        "email_code": STRING_SCHEMA,
        "code": STRING_SCHEMA,
    },
    required=[],
)

PAYMENT_PROVIDER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "description": "Provider-specific payment payload returned by the selected integration.",
}
PAYMENT_RESPONSE_SCHEMA: dict[str, Any] = ok_envelope_with(
    {
        "payment_id": INTEGER_SCHEMA,
        "status": STRING_SCHEMA,
        "paid": BOOLEAN_SCHEMA,
        "payment": PAYMENT_PROVIDER_SCHEMA,
        "payment_url": NULLABLE_STRING_SCHEMA,
        "confirmation_url": NULLABLE_STRING_SCHEMA,
    },
    required=[],
)

PAYMENT_METHOD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": STRING_SCHEMA,
        "name": STRING_SCHEMA,
        "icon": STRING_SCHEMA,
        "min_amount": NUMBER_SCHEMA,
        "minimum_amount": NUMBER_SCHEMA,
        "minimum_amount_text": STRING_SCHEMA,
        "currency": STRING_SCHEMA,
    },
}
HWID_RENEWAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "available": BOOLEAN_SCHEMA,
        "device_count": INTEGER_SCHEMA,
        "price": NUMBER_SCHEMA,
        "stars_price": INTEGER_SCHEMA,
        "currency": STRING_SCHEMA,
        "valid_from": NULLABLE_STRING_SCHEMA,
        "valid_from_text": NULLABLE_STRING_SCHEMA,
        "valid_until": NULLABLE_STRING_SCHEMA,
        "valid_until_text": NULLABLE_STRING_SCHEMA,
        "active_until": NULLABLE_STRING_SCHEMA,
        "active_until_text": NULLABLE_STRING_SCHEMA,
        "pricing_period_months": INTEGER_SCHEMA,
    },
}
HWID_DEVICE_PACKAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": STRING_SCHEMA,
        "tariff_key": STRING_SCHEMA,
        "tariff_name": STRING_SCHEMA,
        "billing_model": STRING_SCHEMA,
        "sale_mode": STRING_SCHEMA,
        "months": NUMBER_SCHEMA,
        "device_count": INTEGER_SCHEMA,
        "price": NUMBER_SCHEMA,
        "stars_price": INTEGER_SCHEMA,
        "currency": STRING_SCHEMA,
        "title": STRING_SCHEMA,
        "subtitle": STRING_SCHEMA,
    },
}
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": STRING_SCHEMA,
        "tariff_key": STRING_SCHEMA,
        "is_default_tariff": BOOLEAN_SCHEMA,
        "tariff_name": STRING_SCHEMA,
        "billing_model": STRING_SCHEMA,
        "description": STRING_SCHEMA,
        "squad_uuids": STRING_ARRAY_SCHEMA,
        "currency": STRING_SCHEMA,
        "hwid_device_limit": NULLABLE_INTEGER_SCHEMA,
        "hwid_device_packages": {"type": "array", "items": HWID_DEVICE_PACKAGE_SCHEMA},
        "sale_mode": STRING_SCHEMA,
        "months": NUMBER_SCHEMA,
        "traffic_gb": NUMBER_SCHEMA,
        "device_count": INTEGER_SCHEMA,
        "price": NUMBER_SCHEMA,
        "stars_price": INTEGER_SCHEMA,
        "title": STRING_SCHEMA,
        "subtitle": STRING_SCHEMA,
        "monthly_gb": NULLABLE_NUMBER_SCHEMA,
        "valid_from": NULLABLE_STRING_SCHEMA,
        "valid_from_text": NULLABLE_STRING_SCHEMA,
        "valid_until": NULLABLE_STRING_SCHEMA,
        "valid_until_text": NULLABLE_STRING_SCHEMA,
        "proration_ratio": NUMBER_SCHEMA,
        "hwid_renewal": HWID_RENEWAL_SCHEMA,
    },
}
PLAN_LIST_SCHEMA: dict[str, Any] = {"type": "array", "items": PLAN_SCHEMA}
PLAN_OPTIONS_RESPONSE_SCHEMA: dict[str, Any] = ok_envelope_with(
    {
        "plans": PLAN_LIST_SCHEMA,
        "tariff_key": STRING_SCHEMA,
        "tariff_name": STRING_SCHEMA,
        "topup_kind": STRING_SCHEMA,
        "premium_title": STRING_SCHEMA,
        "traffic_percent": INTEGER_SCHEMA,
        "premium_traffic_percent": INTEGER_SCHEMA,
        "premium_limit_bytes": INTEGER_SCHEMA,
        "premium_used_bytes": INTEGER_SCHEMA,
        "premium_baseline_bytes": INTEGER_SCHEMA,
        "premium_topup_balance_bytes": INTEGER_SCHEMA,
        "premium_topup_used_bytes": INTEGER_SCHEMA,
        "premium_bonus_bytes": INTEGER_SCHEMA,
        "premium_unlimited_override": BOOLEAN_SCHEMA,
        "premium_is_limited": BOOLEAN_SCHEMA,
        "premium_squad_labels": STRING_ARRAY_SCHEMA,
        "premium_node_labels": STRING_ARRAY_SCHEMA,
        "warning_levels": NUMBER_ARRAY_SCHEMA,
        "current_limit": NULLABLE_INTEGER_SCHEMA,
        "extra_hwid_devices": INTEGER_SCHEMA,
        "extra_hwid_devices_valid_until": NULLABLE_STRING_SCHEMA,
        "extra_hwid_devices_valid_until_text": NULLABLE_STRING_SCHEMA,
        "renewal_available": BOOLEAN_SCHEMA,
        "renewal_recommended_count": INTEGER_SCHEMA,
    },
    required=[],
)

TARIFF_CHANGE_CURRENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tariff_key", "title", "description", "billing_model"],
    "properties": {
        "tariff_key": STRING_SCHEMA,
        "title": STRING_SCHEMA,
        "description": STRING_SCHEMA,
        "billing_model": STRING_SCHEMA,
    },
}
TARIFF_CHANGE_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mode": STRING_SCHEMA,
        "kind": STRING_SCHEMA,
        "title": STRING_SCHEMA,
        "days_after": INTEGER_SCHEMA,
        "remaining_days": INTEGER_SCHEMA,
        "converted_hwid_value_rub": NUMBER_SCHEMA,
        "converted_hwid_days": INTEGER_SCHEMA,
        "converted_hwid_gb": NUMBER_SCHEMA,
        "converted_gb": NUMBER_SCHEMA,
        "traffic_gb": NUMBER_SCHEMA,
        "months": INTEGER_SCHEMA,
        "price": NUMBER_SCHEMA,
        "currency": STRING_SCHEMA,
    },
}
TARIFF_SWITCH_OPTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "description": "Raw switch calculation details from the subscription service.",
}
TARIFF_CHANGE_TARGET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tariff_key", "title", "description", "billing_model", "actions"],
    "properties": {
        "tariff_key": STRING_SCHEMA,
        "title": STRING_SCHEMA,
        "description": STRING_SCHEMA,
        "billing_model": STRING_SCHEMA,
        "monthly_gb": NULLABLE_NUMBER_SCHEMA,
        "options": TARIFF_SWITCH_OPTIONS_SCHEMA,
        "actions": {"type": "array", "items": TARIFF_CHANGE_ACTION_SCHEMA},
    },
}
TARIFF_CHANGE_OPTIONS_RESPONSE_SCHEMA: dict[str, Any] = ok_envelope_with(
    {
        "current": TARIFF_CHANGE_CURRENT_SCHEMA,
        "targets": {"type": "array", "items": TARIFF_CHANGE_TARGET_SCHEMA},
    },
)
TARIFF_CHANGE_RESPONSE_SCHEMA: dict[str, Any] = ok_envelope_with(
    {
        "subscription_id": INTEGER_SCHEMA,
        "tariff_key": STRING_SCHEMA,
    },
)

WEBAPP_USER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": INTEGER_SCHEMA,
        "username": NULLABLE_STRING_SCHEMA,
        "email": NULLABLE_STRING_SCHEMA,
        "email_verified": BOOLEAN_SCHEMA,
        "password_auth_enabled": BOOLEAN_SCHEMA,
        "telegram_id": NULLABLE_INTEGER_SCHEMA,
        "telegram_linked": BOOLEAN_SCHEMA,
        "telegram_notifications_status": STRING_SCHEMA,
        "telegram_notifications_enabled": BOOLEAN_SCHEMA,
        "telegram_notifications_need_prompt": BOOLEAN_SCHEMA,
        "telegram_notifications_start_link": NULLABLE_STRING_SCHEMA,
        "telegram_photo_url": STRING_SCHEMA,
        "first_name": NULLABLE_STRING_SCHEMA,
        "language_code": STRING_SCHEMA,
        "is_admin": BOOLEAN_SCHEMA,
    },
}
WEBAPP_SUBSCRIPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "active": BOOLEAN_SCHEMA,
        "status": STRING_SCHEMA,
        "end_date": NULLABLE_STRING_SCHEMA,
        "end_date_text": NULLABLE_STRING_SCHEMA,
        "days_left": INTEGER_SCHEMA,
        "remaining_text": STRING_SCHEMA,
        "config_link": NULLABLE_STRING_SCHEMA,
        "connect_url": NULLABLE_STRING_SCHEMA,
        "panel_short_uuid": NULLABLE_STRING_SCHEMA,
        "install_share_token": NULLABLE_STRING_SCHEMA,
        "install_share_url": NULLABLE_STRING_SCHEMA,
        "traffic_limit": STRING_SCHEMA,
        "traffic_used": STRING_SCHEMA,
        "traffic_limit_bytes": NULLABLE_INTEGER_SCHEMA,
        "traffic_used_bytes": NULLABLE_INTEGER_SCHEMA,
        "tariff_key": NULLABLE_STRING_SCHEMA,
        "tariff_name": NULLABLE_STRING_SCHEMA,
        "tariff_description": NULLABLE_STRING_SCHEMA,
        "premium_title": NULLABLE_STRING_SCHEMA,
        "billing_model": NULLABLE_STRING_SCHEMA,
        "traffic_limit_strategy": STRING_SCHEMA,
        "tier_baseline_bytes": NULLABLE_INTEGER_SCHEMA,
        "topup_balance_bytes": NULLABLE_INTEGER_SCHEMA,
        "premium_limit": STRING_SCHEMA,
        "premium_used": STRING_SCHEMA,
        "premium_limit_bytes": NULLABLE_INTEGER_SCHEMA,
        "premium_used_bytes": NULLABLE_INTEGER_SCHEMA,
        "premium_baseline_bytes": NULLABLE_INTEGER_SCHEMA,
        "premium_topup_balance_bytes": NULLABLE_INTEGER_SCHEMA,
        "premium_topup_used_bytes": NULLABLE_INTEGER_SCHEMA,
        "premium_bonus_bytes": INTEGER_SCHEMA,
        "regular_bonus_bytes": INTEGER_SCHEMA,
        "regular_unlimited_override": BOOLEAN_SCHEMA,
        "premium_unlimited_override": BOOLEAN_SCHEMA,
        "premium_is_limited": BOOLEAN_SCHEMA,
        "premium_squad_labels": STRING_ARRAY_SCHEMA,
        "premium_node_labels": STRING_ARRAY_SCHEMA,
        "can_topup_traffic": BOOLEAN_SCHEMA,
        "can_topup_regular_traffic": BOOLEAN_SCHEMA,
        "can_topup_premium_traffic": BOOLEAN_SCHEMA,
        "can_topup_devices": BOOLEAN_SCHEMA,
        "period_start_at": NULLABLE_STRING_SCHEMA,
        "is_throttled": BOOLEAN_SCHEMA,
        "max_devices": NULLABLE_INTEGER_SCHEMA,
        "base_hwid_device_limit": NULLABLE_INTEGER_SCHEMA,
        "extra_hwid_devices": INTEGER_SCHEMA,
        "extra_hwid_devices_valid_until": NULLABLE_STRING_SCHEMA,
        "extra_hwid_devices_valid_until_text": NULLABLE_STRING_SCHEMA,
        "extra_hwid_devices_next_valid_from": NULLABLE_STRING_SCHEMA,
        "device_topup_renewal_available": BOOLEAN_SCHEMA,
        "auto_renew_enabled": BOOLEAN_SCHEMA,
        "auto_renew_available": BOOLEAN_SCHEMA,
        "auto_renew_can_enable": BOOLEAN_SCHEMA,
        "auto_renew_provider_label": NULLABLE_STRING_SCHEMA,
        "provider": NULLABLE_STRING_SCHEMA,
    },
}
REFERRAL_BONUS_DETAIL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": STRING_SCHEMA,
        "type": STRING_SCHEMA,
        "tariff_key": STRING_SCHEMA,
        "tariff_name": STRING_SCHEMA,
        "months": INTEGER_SCHEMA,
        "title": STRING_SCHEMA,
        "inviter_days": INTEGER_SCHEMA,
        "friend_days": INTEGER_SCHEMA,
        "inviter_min_days": INTEGER_SCHEMA,
        "inviter_max_days": INTEGER_SCHEMA,
        "friend_min_days": INTEGER_SCHEMA,
        "friend_max_days": INTEGER_SCHEMA,
        "details": {"type": "array", "items": OBJECT_MAP_SCHEMA},
    },
}
WEBAPP_REFERRAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "code": NULLABLE_STRING_SCHEMA,
        "bot_link": NULLABLE_STRING_SCHEMA,
        "webapp_link": NULLABLE_STRING_SCHEMA,
        "invited_count": INTEGER_SCHEMA,
        "purchased_count": INTEGER_SCHEMA,
        "welcome_bonus_days": INTEGER_SCHEMA,
        "welcome_bonus_without_telegram_enabled": BOOLEAN_SCHEMA,
        "welcome_bonus_requires_telegram": BOOLEAN_SCHEMA,
        "welcome_bonus_block_reason": NULLABLE_STRING_SCHEMA,
        "one_bonus_per_referee": BOOLEAN_SCHEMA,
        "bonus_details": {"type": "array", "items": REFERRAL_BONUS_DETAIL_SCHEMA},
    },
}
THEME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "key": STRING_SCHEMA,
        "label": STRING_SCHEMA,
        "enabled": BOOLEAN_SCHEMA,
        "default": BOOLEAN_SCHEMA,
    },
}
THEMES_CATALOG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "default_theme": STRING_SCHEMA,
        "themes": {"type": "array", "items": THEME_SCHEMA},
    },
}
WEBAPP_SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "support_url": NULLABLE_STRING_SCHEMA,
        "server_status_url": NULLABLE_STRING_SCHEMA,
        "support_tickets_enabled": BOOLEAN_SCHEMA,
        "support_ticket_max_body_length": INTEGER_SCHEMA,
        "support_ticket_max_subject_length": INTEGER_SCHEMA,
        "traffic_mode": BOOLEAN_SCHEMA,
        "my_devices_enabled": BOOLEAN_SCHEMA,
        "user_hwid_device_limit": NULLABLE_INTEGER_SCHEMA,
        "trial_enabled": BOOLEAN_SCHEMA,
        "trial_available": BOOLEAN_SCHEMA,
        "trial_without_telegram_enabled": BOOLEAN_SCHEMA,
        "trial_requires_telegram": BOOLEAN_SCHEMA,
        "trial_block_reason": NULLABLE_STRING_SCHEMA,
        "trial_duration_days": INTEGER_SCHEMA,
        "trial_traffic_limit_gb": NUMBER_SCHEMA,
        "trial_traffic_strategy": STRING_SCHEMA,
        "subscription_purchase_description": STRING_SCHEMA,
        "subscription_guides_enabled": BOOLEAN_SCHEMA,
        "email_auth_enabled": BOOLEAN_SCHEMA,
    },
}
ME_RESPONSE_SCHEMA: dict[str, Any] = ok_envelope_with(
    {
        "user": WEBAPP_USER_SCHEMA,
        "subscription": WEBAPP_SUBSCRIPTION_SCHEMA,
        "referral": WEBAPP_REFERRAL_SCHEMA,
        "plans": PLAN_LIST_SCHEMA,
        "payment_methods": {"type": "array", "items": PAYMENT_METHOD_SCHEMA},
        "themes_catalog": THEMES_CATALOG_SCHEMA,
        "support_unread_count": INTEGER_SCHEMA,
        "settings": WEBAPP_SETTINGS_SCHEMA,
    },
)
