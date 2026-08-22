"""Typed admin API response contracts for users and subscriptions."""

from __future__ import annotations

from typing import Any

from bot.app.web.http_contracts import HttpResponseModel
from bot.services.telegram_notifications import normalize_telegram_notification_status


class AdminUserOut(HttpResponseModel):
    # Field order mirrors the legacy ``_serialize_user`` dict so
    # ``model_dump(mode="json")`` is byte-identical; the parity test guards it.
    user_id: int
    telegram_id: int | None = None
    telegram_photo_url: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    language_code: str | None = None
    is_banned: bool
    registration_date: str | None = None
    panel_user_uuid: str | None = None
    referral_code: str | None = None
    referred_by_id: int | None = None

    @classmethod
    def from_orm_user(cls, user: Any) -> AdminUserOut:
        return cls(
            user_id=int(user.user_id),
            telegram_id=int(user.telegram_id) if user.telegram_id else None,
            telegram_photo_url=user.telegram_photo_url,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            language_code=user.language_code,
            is_banned=bool(user.is_banned),
            registration_date=(
                user.registration_date.isoformat() if user.registration_date else None
            ),
            panel_user_uuid=user.panel_user_uuid,
            referral_code=user.referral_code,
            referred_by_id=int(user.referred_by_id) if user.referred_by_id else None,
        )


class AdminUserWithAvatarOut(AdminUserOut):
    # Schema for the admin user object enriched with the avatar URL
    # (``_serialize_admin_user_with_avatar`` appends ``avatar_url`` last).
    avatar_url: str | None = None


class AdminTelegramNotificationsOut(HttpResponseModel):
    status: str
    checked_at: str | None = None
    enabled_at: str | None = None
    blocked_at: str | None = None

    @classmethod
    def from_orm_user(cls, user: Any) -> AdminTelegramNotificationsOut:
        def iso(attribute: str) -> str | None:
            value = getattr(user, attribute, None)
            return value.isoformat() if value else None

        return cls(
            status=normalize_telegram_notification_status(
                getattr(user, "telegram_notifications_status", None)
            ),
            checked_at=iso("telegram_notifications_checked_at"),
            enabled_at=iso("telegram_notifications_enabled_at"),
            blocked_at=iso("telegram_notifications_blocked_at"),
        )


class AdminUserTrialOut(HttpResponseModel):
    # Field order mirrors the legacy ``_serialize_trial_summary`` dict.
    used: bool
    count: int
    first_activated_at: str | None = None
    latest_activated_at: str | None = None
    latest_end_date: str | None = None
    active: bool
    last_reset_at: str | None = None

    @classmethod
    def from_orm_trial(cls, user: Any, trial_subs: Any) -> AdminUserTrialOut:
        first_trial_sub = trial_subs[0] if trial_subs else None
        latest_trial_sub = trial_subs[-1] if trial_subs else None
        first_start = getattr(first_trial_sub, "start_date", None)
        latest_start = getattr(latest_trial_sub, "start_date", None)
        latest_end = getattr(latest_trial_sub, "end_date", None)
        reset_at = getattr(user, "trial_eligibility_reset_at", None)
        return cls(
            used=bool(trial_subs),
            count=len(trial_subs),
            first_activated_at=first_start.isoformat() if first_start else None,
            latest_activated_at=latest_start.isoformat() if latest_start else None,
            latest_end_date=latest_end.isoformat() if latest_end else None,
            active=bool(latest_trial_sub and getattr(latest_trial_sub, "is_active", False)),
            last_reset_at=reset_at.isoformat() if reset_at else None,
        )


class AdminSubscriptionOut(HttpResponseModel):
    # Field order mirrors the legacy ``_serialize_subscription`` dict so
    # ``model_dump(mode="json")`` is byte-identical; the parity test guards it.
    subscription_id: int
    panel_user_uuid: str | None = None
    panel_subscription_uuid: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    duration_months: int | None = None
    is_active: bool
    status_from_panel: str | None = None
    traffic_limit_bytes: int | None = None
    traffic_used_bytes: int | None = None
    tier_baseline_bytes: int | None = None
    topup_balance_bytes: int | None = None
    premium_used_bytes: int | None = None
    premium_limit_bytes: int
    premium_baseline_bytes: int | None = None
    premium_topup_balance_bytes: int | None = None
    premium_topup_used_bytes: int | None = None
    premium_bonus_bytes: int
    regular_bonus_bytes: int
    regular_unlimited_override: bool
    premium_unlimited_override: bool
    premium_is_limited: bool
    hwid_device_limit: int | None = None
    extra_hwid_devices: int
    tariff_key: str | None = None
    tariff_binding_source: str | None = None
    tariff_bound_at: str | None = None
    tariff_binding_note: str | None = None
    display_label: str | None = None
    is_trial: bool
    auto_renew_enabled: bool
    provider: str | None = None
    is_throttled: bool
    billing_model: str | None = None
    traffic_limit_strategy: str | None = None
    traffic_strategy_editable: bool = False
    traffic_strategy_lock_reason: str | None = None

    @classmethod
    def from_orm_subscription(cls, sub: Any) -> AdminSubscriptionOut:
        premium_bonus_bytes = int(getattr(sub, "premium_bonus_bytes", 0) or 0)
        regular_bonus_bytes = int(getattr(sub, "regular_bonus_bytes", 0) or 0)
        premium_limit_bytes = (
            int(sub.premium_baseline_bytes or 0)
            + int(sub.premium_topup_balance_bytes or 0)
            + int(getattr(sub, "premium_topup_used_bytes", 0) or 0)
            + premium_bonus_bytes
        )
        provider = sub.provider
        is_trial = str(provider or "").strip().lower() == "trial"
        display_label = "Trial" if is_trial else sub.tariff_key
        return cls(
            subscription_id=int(sub.subscription_id),
            panel_user_uuid=sub.panel_user_uuid,
            panel_subscription_uuid=sub.panel_subscription_uuid,
            start_date=sub.start_date.isoformat() if sub.start_date else None,
            end_date=sub.end_date.isoformat() if sub.end_date else None,
            duration_months=sub.duration_months,
            is_active=bool(sub.is_active),
            status_from_panel=sub.status_from_panel,
            traffic_limit_bytes=sub.traffic_limit_bytes,
            traffic_used_bytes=sub.traffic_used_bytes,
            tier_baseline_bytes=sub.tier_baseline_bytes,
            topup_balance_bytes=sub.topup_balance_bytes,
            premium_used_bytes=sub.premium_used_bytes,
            premium_limit_bytes=premium_limit_bytes,
            premium_baseline_bytes=sub.premium_baseline_bytes,
            premium_topup_balance_bytes=sub.premium_topup_balance_bytes,
            premium_topup_used_bytes=getattr(sub, "premium_topup_used_bytes", 0),
            premium_bonus_bytes=premium_bonus_bytes,
            regular_bonus_bytes=regular_bonus_bytes,
            regular_unlimited_override=bool(getattr(sub, "regular_unlimited_override", False)),
            premium_unlimited_override=bool(getattr(sub, "premium_unlimited_override", False)),
            premium_is_limited=bool(sub.premium_is_limited),
            hwid_device_limit=getattr(sub, "hwid_device_limit", None),
            extra_hwid_devices=int(getattr(sub, "extra_hwid_devices", 0) or 0),
            tariff_key=sub.tariff_key,
            tariff_binding_source=getattr(sub, "tariff_binding_source", None),
            tariff_bound_at=(
                sub.tariff_bound_at.isoformat() if getattr(sub, "tariff_bound_at", None) else None
            ),
            tariff_binding_note=getattr(sub, "tariff_binding_note", None),
            display_label=display_label,
            is_trial=is_trial,
            auto_renew_enabled=bool(sub.auto_renew_enabled),
            provider=provider,
            is_throttled=bool(sub.is_throttled),
            billing_model=getattr(sub, "billing_model", None),
            traffic_limit_strategy=getattr(sub, "traffic_limit_strategy", None),
            traffic_strategy_editable=bool(getattr(sub, "traffic_strategy_editable", False)),
            traffic_strategy_lock_reason=getattr(sub, "traffic_strategy_lock_reason", None),
        )
