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

from pydantic import ConfigDict, Field, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel


class PromoCreateBody(HttpBodyModel):
    code: str
    bonus_days: int = Field(gt=0)
    max_activations: int = Field(gt=0)
    valid_days: Any = None

    @field_validator("code", mode="before")
    @classmethod
    def _normalize_code(cls, value: Any) -> str:
        code = str(value or "").strip().upper()
        if not code:
            raise ValueError("empty_code")
        return code


class PromoUpdateBody(HttpBodyModel):
    is_active: Any = None
    bonus_days: int | None = Field(default=None, gt=0)
    max_activations: int | None = Field(default=None, gt=0)


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
    bonus_days: int
    max_activations: int
    current_activations: int
    is_active: bool
    valid_until: datetime | None = None
    created_at: datetime | None = None
    created_by_admin_id: int | None = None

    @classmethod
    def from_orm_promo(cls, promo: Any) -> "PromoOut":
        return cls(
            id=int(promo.promo_code_id),
            code=promo.code,
            bonus_days=int(promo.bonus_days),
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
    def from_sync_status(cls, sync_status: Any) -> "AdminPanelSyncOut":
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
    def from_orm_payment(cls, payment: Any) -> "PaymentOut":
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
    def from_orm_payment_detail(cls, payment: Any) -> "PaymentDetailOut":
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
    def from_orm_ad(cls, campaign: Any, totals: dict[str, Any] | None = None) -> "AdOut":
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
    def from_orm_log(cls, entry: Any) -> "LogOut":
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
