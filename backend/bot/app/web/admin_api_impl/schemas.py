"""Typed HTTP contracts for admin API endpoints.

Request body models use pydantic v2 ``BaseModel`` with ``extra="ignore"`` while
the API is being migrated. That preserves compatibility with clients that send
extra fields today; individual domains can move to ``extra="forbid"`` once their
frontend contracts are fully typed.

Response models describe the inner payload objects only. Handlers still wrap
them with the existing ``{"ok": true, ...}`` envelope via ``_ok`` and must build
objects through explicit classmethods such as ``from_orm_*``. Avoid pydantic
``from_attributes`` for ORM rows: explicit scalar reads prevent accidental lazy
loads after the SQLAlchemy session scope has closed.

Template for migrated domains:
1. Add request models and parse them with ``parse_body``.
2. Add response models with explicit ``from_orm_*`` constructors.
3. Add parity tests proving the serialized JSON matches the legacy dict helper.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from pydantic import ConfigDict, Field, field_validator, model_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.services.promo_effects import PromoEffects, summarize_effects, validate_effects


class PromoCreateBody(HttpBodyModel):
    code: str | None = None
    bonus_days: int = Field(default=0, ge=0)
    discount_percent: float | None = Field(default=None, gt=0, le=100)
    duration_multiplier: float | None = Field(default=None, ge=1)
    traffic_multiplier: float | None = Field(default=None, ge=1)
    bonus_requires_payment: bool = False
    applies_to: str = "all"
    min_subscription_months: int | None = Field(default=None, gt=0)
    min_traffic_gb: float | None = Field(default=None, gt=0)
    max_activations: int = Field(gt=0)
    valid_days: Any = None
    origin: str = "admin"

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: Any) -> str | None:
        code = str(value or "").strip().upper()
        return code or None

    @field_validator("applies_to", "origin", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return str(value or "").strip().lower()

    @model_validator(mode="after")
    def _validate_effects(self) -> PromoCreateBody:
        validate_effects(self.to_effects())
        return self

    def to_effects(self) -> PromoEffects:
        return PromoEffects(
            bonus_days=int(self.bonus_days or 0),
            discount_percent=self.discount_percent,
            duration_multiplier=float(self.duration_multiplier or 1.0),
            traffic_multiplier=float(self.traffic_multiplier or 1.0),
            bonus_requires_payment=bool(self.bonus_requires_payment),
            applies_to=self.applies_to or "all",
            min_subscription_months=self.min_subscription_months,
            min_traffic_gb=self.min_traffic_gb,
        )


class PromoUpdateBody(HttpBodyModel):
    is_active: Any = None
    bonus_days: int | None = Field(default=None, ge=0)
    discount_percent: float | None = Field(default=None, gt=0, le=100)
    duration_multiplier: float | None = Field(default=None, ge=1)
    traffic_multiplier: float | None = Field(default=None, ge=1)
    bonus_requires_payment: bool | None = None
    applies_to: str | None = None
    min_subscription_months: int | None = Field(default=None, gt=0)
    min_traffic_gb: float | None = Field(default=None, gt=0)
    max_activations: int | None = Field(default=None, gt=0)
    origin: str | None = None
    valid_until: datetime | None = None
    clear_valid_until: Any = None

    @field_validator("applies_to", "origin", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value or "").strip().lower()
        return text or None


def _strip_text(value: Any) -> str:
    return str(value or "").strip()


class AdminSettingsPatchBody(HttpBodyModel):
    updates: Any = Field(default_factory=dict)
    deletes: Any = Field(default_factory=list)


class AdminTranslationsPatchBody(HttpBodyModel):
    updates: Any = Field(default_factory=dict)
    deletes: Any = Field(default_factory=list)


class TariffsSaveBody(HttpBodyModel):
    model_config = ConfigDict(extra="allow")

    catalog: Any = None

    def catalog_payload(self) -> Any:
        if "catalog" in self.model_fields_set:
            return self.catalog
        return self.model_extra or {}


class ThemesSaveBody(HttpBodyModel):
    model_config = ConfigDict(extra="allow")

    catalog: Any = None

    def catalog_payload(self) -> Any:
        if "catalog" in self.model_fields_set:
            return self.catalog
        return self.model_extra or {}


class ImageUrlUploadBody(HttpBodyModel):
    url: Any = ""


class AdminBackupRestoreBody(HttpBodyModel):
    archive_name: Any = ""
    restore_database: Any = False
    restore_compose: Any = False
    confirm: Any = False


class AdminBroadcastBody(HttpBodyModel):
    text: Any = ""
    target: Any = "all"

    @field_validator("text", "target", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return _strip_text(value)


class AdminUserBanBody(HttpBodyModel):
    banned: Any = False


class AdminUserMessageBody(HttpBodyModel):
    text: Any = ""

    @field_validator("text", mode="before")
    @classmethod
    def _normalize_text(cls, value: Any) -> str:
        return _strip_text(value)


class AdminUserPremiumOverrideBody(HttpBodyModel):
    unlimited: Any = False
    bonus_bytes: Any = None
    bonus_gb: Any = None


class AdminUserRegularTrafficOverrideBody(HttpBodyModel):
    unlimited: Any = False
    regular_bonus_bytes: Any = None
    regular_bonus_gb: Any = None


class AdminUserHwidDeviceLimitBody(HttpBodyModel):
    unlimited: Any = False
    use_default: Any = False
    reset_to_default: Any = False
    hwid_device_limit: Any = None
    limit: Any = None


class AdminUserTrafficGrantBody(HttpBodyModel):
    kind: Any = "regular"
    bytes: Any = None
    gb: Any = None

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, value: Any) -> str:
        return _strip_text(value).lower() or "regular"


class AdminUserExtendBody(HttpBodyModel):
    days: Any = None
    tariff_key: Any = None
    extend_hwid_devices: Any = None


class AdminUserTariffBody(HttpBodyModel):
    tariff_key: Any = None


class PromoOut(HttpResponseModel):
    id: int
    code: str
    bot_link: str | None = None
    webapp_link: str | None = None
    bonus_days: int
    discount_percent: float | None = None
    duration_multiplier: float | None = None
    traffic_multiplier: float | None = None
    bonus_requires_payment: bool = False
    applies_to: str
    min_subscription_months: int | None = None
    min_traffic_gb: float | None = None
    origin: str
    effect_summary: str
    max_activations: int
    current_activations: int
    is_active: bool
    valid_until: datetime | None = None
    created_at: datetime | None = None
    created_by_admin_id: int | None = None

    @classmethod
    def from_orm_promo(
        cls,
        promo: Any,
        *,
        bot_link: str | None = None,
        webapp_link: str | None = None,
    ) -> PromoOut:
        effects = PromoEffects.from_model(promo)
        return cls(
            id=int(promo.promo_code_id),
            code=promo.code,
            bot_link=bot_link,
            webapp_link=webapp_link,
            bonus_days=int(promo.bonus_days),
            discount_percent=effects.discount_percent,
            duration_multiplier=(
                effects.duration_multiplier if effects.duration_multiplier != 1.0 else None
            ),
            traffic_multiplier=(
                effects.traffic_multiplier if effects.traffic_multiplier != 1.0 else None
            ),
            bonus_requires_payment=bool(effects.bonus_requires_payment),
            applies_to=effects.applies_to,
            min_subscription_months=effects.min_subscription_months,
            min_traffic_gb=effects.min_traffic_gb,
            origin=str(getattr(promo, "origin", None) or "admin"),
            effect_summary=summarize_effects(effects),
            max_activations=int(promo.max_activations),
            current_activations=int(promo.current_activations or 0),
            is_active=bool(promo.is_active),
            valid_until=promo.valid_until,
            created_at=promo.created_at,
            created_by_admin_id=int(promo.created_by_admin_id)
            if promo.created_by_admin_id
            else None,
        )


class AdminMeOut(HttpResponseModel):
    user_id: int
    admin_ids: list[int]


class AdminPanelSyncOut(HttpResponseModel):
    status: str
    last_sync_time: datetime | None = None
    details: Any = None
    users_processed: int
    subscriptions_synced: int

    @classmethod
    def from_sync_status(cls, sync_status: Any) -> AdminPanelSyncOut:
        return cls(
            status=sync_status.status if sync_status else "never_run",
            last_sync_time=sync_status.last_sync_time
            if sync_status and sync_status.last_sync_time
            else None,
            details=sync_status.details if sync_status else None,
            users_processed=sync_status.users_processed_from_panel if sync_status else 0,
            subscriptions_synced=sync_status.subscriptions_synced if sync_status else 0,
        )


def _traffic_gb_split(payment: Any) -> tuple[float | None, float | None]:
    if payment.purchased_gb is None:
        return None, None
    try:
        gb = float(payment.purchased_gb)
    except (TypeError, ValueError):
        return None, None
    sale_mode = (payment.sale_mode or "").strip()
    if not sale_mode:
        return None, None
    base = sale_mode.split("@", 1)[0].split("|", 1)[0].lower()
    if base == "premium_topup":
        return None, gb
    if base in {"traffic", "traffic_package", "topup"}:
        return gb, None
    return None, None


def _display_label(
    loaded_user: Any,
    fallback_user_id: int | None,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    email: str | None = None,
) -> str | None:
    telegram_id = getattr(loaded_user, "telegram_id", None)
    if loaded_user is not None and telegram_id is not None:
        first = (getattr(loaded_user, "first_name", None) or "").strip()
        last = (getattr(loaded_user, "last_name", None) or "").strip()
        full_name = f"{first} {last}".strip()
        if full_name:
            return full_name
        loaded_username = (getattr(loaded_user, "username", None) or "").strip()
        if loaded_username:
            return loaded_username if loaded_username.startswith("@") else f"@{loaded_username}"
    elif loaded_user is not None:
        loaded_email = (getattr(loaded_user, "email", None) or "").strip()
        if loaded_email:
            return loaded_email
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    full_name = f"{first} {last}".strip()
    if full_name:
        return full_name
    username_value = (username or "").strip()
    if username_value:
        return username_value if username_value.startswith("@") else f"@{username_value}"
    email_value = (email or "").strip()
    if email_value:
        return email_value
    if fallback_user_id is None:
        return None
    return str(fallback_user_id)


def _payment_user_display_label(loaded_user: Any, payment_user_id: int) -> str:
    label = _display_label(loaded_user, payment_user_id)
    return label or str(payment_user_id)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float_or_none(*values: Any) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


class PromoActivationOut(HttpResponseModel):
    activation_id: int
    promo_id: int
    user_id: int
    user_label: str
    telegram_id: int | None = None
    activated_at: datetime | None = None
    payment_id: int | None = None
    payment_amount: float | None = None
    payment_currency: str | None = None
    payment_status: str | None = None
    payment_provider: str | None = None
    payment_sale_mode: str | None = None
    payment_description: str | None = None
    payment_created_at: datetime | None = None
    effect_summary: str | None = None
    bonus_days: int | None = None
    discount_percent: float | None = None
    duration_multiplier: float | None = None
    traffic_multiplier: float | None = None
    applies_to: str | None = None
    base_amount: float | None = None
    discount_amount: float | None = None
    charged_months: int | None = None
    charged_gb: float | None = None
    granted_days: int | None = None
    granted_gb: float | None = None

    @classmethod
    def from_orm_activation(cls, activation: Any) -> PromoActivationOut:
        loaded_user = activation.__dict__.get("user")
        loaded_payment = activation.__dict__.get("payment")
        user_label = _display_label(loaded_user, int(activation.user_id)) or str(activation.user_id)
        telegram_id = None
        if loaded_user is not None and getattr(loaded_user, "telegram_id", None) is not None:
            try:
                telegram_id = int(loaded_user.telegram_id)
            except (TypeError, ValueError):
                telegram_id = None
        return cls(
            activation_id=int(activation.activation_id),
            promo_id=int(activation.promo_code_id),
            user_id=int(activation.user_id),
            user_label=user_label,
            telegram_id=telegram_id,
            activated_at=activation.activated_at,
            payment_id=int(activation.payment_id) if activation.payment_id else None,
            payment_amount=(
                float(loaded_payment.amount)
                if loaded_payment is not None and loaded_payment.amount is not None
                else None
            ),
            payment_currency=loaded_payment.currency if loaded_payment is not None else None,
            payment_status=loaded_payment.status if loaded_payment is not None else None,
            payment_provider=loaded_payment.provider if loaded_payment is not None else None,
            payment_sale_mode=loaded_payment.sale_mode if loaded_payment is not None else None,
            payment_description=loaded_payment.description if loaded_payment is not None else None,
            payment_created_at=loaded_payment.created_at if loaded_payment is not None else None,
            effect_summary=getattr(activation, "effect_summary", None),
            bonus_days=(
                int(activation.bonus_days)
                if getattr(activation, "bonus_days", None) is not None
                else None
            ),
            discount_percent=_float_or_none(getattr(activation, "discount_percent", None)),
            duration_multiplier=_float_or_none(getattr(activation, "duration_multiplier", None)),
            traffic_multiplier=_float_or_none(getattr(activation, "traffic_multiplier", None)),
            applies_to=getattr(activation, "applies_to", None),
            base_amount=_first_float_or_none(
                getattr(activation, "base_amount", None),
                getattr(loaded_payment, "checkout_base_amount", None)
                if loaded_payment is not None
                else None,
            ),
            discount_amount=_first_float_or_none(
                getattr(activation, "discount_amount", None),
                getattr(loaded_payment, "checkout_discount_amount", None)
                if loaded_payment is not None
                else None,
            ),
            charged_months=(
                int(getattr(activation, "charged_months", 0) or 0)
                if getattr(activation, "charged_months", None) is not None
                else (
                    int(getattr(loaded_payment, "checkout_charged_months", 0) or 0)
                    if loaded_payment is not None
                    and getattr(loaded_payment, "checkout_charged_months", None) is not None
                    else None
                )
            ),
            charged_gb=_first_float_or_none(
                getattr(activation, "charged_gb", None),
                getattr(loaded_payment, "checkout_charged_gb", None)
                if loaded_payment is not None
                else None,
            ),
            granted_days=(
                int(getattr(activation, "granted_days", 0) or 0)
                if getattr(activation, "granted_days", None) is not None
                else None
            ),
            granted_gb=_float_or_none(getattr(activation, "granted_gb", None)),
        )


class PaymentOut(HttpResponseModel):
    payment_id: int
    user_id: int
    user_label: str
    telegram_id: int | None = None
    traffic_regular_gb: float | None = None
    traffic_premium_gb: float | None = None
    provider: str | None = None
    provider_payment_id: str | None = None
    amount: float
    currency: str | None = None
    status: str | None = None
    description: str | None = None
    subscription_duration_months: int | None = None
    sale_mode: str | None = None
    tariff_key: str | None = None
    purchased_gb: Any = None
    purchased_hwid_devices: int | None = None
    created_at: datetime | None = None

    @classmethod
    def from_orm_payment(cls, payment: Any) -> PaymentOut:
        telegram_id = None
        loaded_user = payment.__dict__.get("user")
        user_label = _payment_user_display_label(loaded_user, int(payment.user_id))
        if loaded_user is not None:
            raw_telegram_id = getattr(loaded_user, "telegram_id", None)
            if raw_telegram_id is not None:
                try:
                    telegram_id = int(raw_telegram_id)
                except (TypeError, ValueError):
                    telegram_id = None
        regular_gb, premium_gb = _traffic_gb_split(payment)
        return cls(
            payment_id=int(payment.payment_id),
            user_id=int(payment.user_id),
            user_label=user_label,
            telegram_id=telegram_id,
            traffic_regular_gb=regular_gb,
            traffic_premium_gb=premium_gb,
            provider=payment.provider,
            provider_payment_id=payment.provider_payment_id,
            amount=float(payment.amount),
            currency=payment.currency,
            status=payment.status,
            description=payment.description,
            subscription_duration_months=payment.subscription_duration_months,
            sale_mode=payment.sale_mode,
            tariff_key=payment.tariff_key,
            purchased_gb=payment.purchased_gb,
            purchased_hwid_devices=payment.purchased_hwid_devices,
            created_at=payment.created_at,
        )


class PaymentDetailOut(PaymentOut):
    yookassa_payment_id: str | None = None
    idempotence_key: str | None = None
    promo_code: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_orm_payment_detail(cls, payment: Any) -> PaymentDetailOut:
        payload = PaymentOut.from_orm_payment(payment).model_dump(mode="json")
        payload.update(
            {
                "yookassa_payment_id": payment.yookassa_payment_id,
                "idempotence_key": payment.idempotence_key,
                "promo_code": (
                    payment.promo_code_used.code if payment.promo_code_used is not None else None
                ),
                "updated_at": payment.updated_at,
            }
        )
        return cast("PaymentDetailOut", cls.model_validate(payload))


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
    display_label: str | None = None
    is_trial: bool
    auto_renew_enabled: bool
    provider: str | None = None
    is_throttled: bool

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
            display_label=display_label,
            is_trial=is_trial,
            auto_renew_enabled=bool(sub.auto_renew_enabled),
            provider=provider,
            is_throttled=bool(sub.is_throttled),
        )


class AdminStatsOut(HttpResponseModel):
    users: dict[str, Any]
    financial: dict[str, Any]
    panel_sync: AdminPanelSyncOut
    recent_payments: list[PaymentOut]
    currency_symbol: str
    panel: dict[str, Any] | None = None
    queue: dict[str, Any] | None = None


class AdminHealthOut(HttpResponseModel):
    alerts: list[dict[str, Any]]
    checked_at: datetime


class AdStatsOut(HttpResponseModel):
    starts: int = 0
    trials: int = 0
    payers: int = 0
    revenue: float = 0.0


class AdOut(HttpResponseModel):
    id: int
    source: str | None = None
    start_param: str | None = None
    cost: float
    is_active: bool
    created_at: datetime | None = None
    stats: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_orm_ad(cls, campaign: Any, totals: dict[str, Any] | None = None) -> AdOut:
        return cls(
            id=int(campaign.ad_campaign_id),
            source=campaign.source,
            start_param=campaign.start_param,
            cost=float(campaign.cost or 0),
            is_active=bool(campaign.is_active),
            created_at=campaign.created_at,
            stats=totals or {},
        )


class AdminAdsListOut(HttpResponseModel):
    campaigns: list[AdOut]
    totals: dict[str, float]


class AdCreateBody(HttpBodyModel):
    source: str
    start_param: str
    cost: float = 0.0

    @field_validator("source", "start_param", mode="before")
    @classmethod
    def _strip_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("empty")
        return text

    @field_validator("cost", mode="before")
    @classmethod
    def _coerce_cost(cls, value: Any) -> float:
        return float(value or 0.0)


class AdToggleBody(HttpBodyModel):
    is_active: Any = True


class LogOut(HttpResponseModel):
    log_id: int
    user_id: int | None = None
    user_label: str | None = None
    telegram_username: str | None = None
    telegram_first_name: str | None = None
    email: str | None = None
    event_type: str | None = None
    content: str | None = None
    is_admin_event: bool
    target_user_id: int | None = None
    target_user_label: str | None = None
    timestamp: datetime | None = None

    @classmethod
    def from_orm_log(cls, entry: Any) -> LogOut:
        author_user = entry.__dict__.get("author_user")
        target_user = entry.__dict__.get("target_user")
        user_id = int(entry.user_id) if entry.user_id is not None else None
        target_user_id = int(entry.target_user_id) if entry.target_user_id is not None else None
        return cls(
            log_id=int(entry.log_id),
            user_id=user_id,
            user_label=_display_label(
                author_user,
                user_id,
                first_name=entry.telegram_first_name,
                username=entry.telegram_username,
            ),
            telegram_username=entry.telegram_username,
            telegram_first_name=entry.telegram_first_name,
            email=getattr(author_user, "email", None),
            event_type=entry.event_type,
            content=entry.content,
            is_admin_event=bool(entry.is_admin_event),
            target_user_id=target_user_id,
            target_user_label=_display_label(target_user, target_user_id),
            timestamp=entry.timestamp,
        )


class AdminLogsListOut(HttpResponseModel):
    logs: list[LogOut]
    page: int
    page_size: int
    total: int


class AdminPaymentsListOut(HttpResponseModel):
    payments: list[PaymentOut]
    page: int
    page_size: int
    total: int
