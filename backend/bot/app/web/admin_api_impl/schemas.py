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
from typing import Any, Literal, cast

from pydantic import ConfigDict, Field, field_validator, model_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.payment_providers.base import PaymentProviderPresentation, PaymentProviderSpec
from bot.services.promo_effects import (
    PROMO_TRAFFIC_GRANT_MAX_GB,
    PromoEffects,
    summarize_effects,
    validate_effects,
)
from config.settings import Settings
from config.tariffs_config import PackageSet, Tariff, TariffsConfig

from .activity_schemas import (
    AdCreateBody as AdCreateBody,
)
from .activity_schemas import (
    AdminAdsListOut as AdminAdsListOut,
)
from .activity_schemas import (
    AdminLogsListOut as AdminLogsListOut,
)
from .activity_schemas import (
    AdOut as AdOut,
)
from .activity_schemas import (
    AdStatsOut as AdStatsOut,
)
from .activity_schemas import (
    AdToggleBody as AdToggleBody,
)
from .activity_schemas import (
    LogOut as LogOut,
)
from .payment_schemas import (
    AdminPaymentFinalizeBody as AdminPaymentFinalizeBody,
)
from .payment_schemas import (
    AdminPaymentReverseBody as AdminPaymentReverseBody,
)
from .payment_schemas import (
    PaymentDetailOut as PaymentDetailOut,
)
from .payment_schemas import (
    PaymentOut as PaymentOut,
)
from .payment_schemas import (
    PaymentPurchaseOut as PaymentPurchaseOut,
)
from .schema_helpers import (
    display_label as _display_label,
)
from .schema_helpers import (
    first_float_or_none as _first_float_or_none,
)
from .schema_helpers import (
    float_or_none as _float_or_none,
)
from .user_schemas import (
    AdminSubscriptionOut as AdminSubscriptionOut,
)
from .user_schemas import (
    AdminTelegramNotificationsOut as AdminTelegramNotificationsOut,
)
from .user_schemas import (
    AdminUserOut as AdminUserOut,
)
from .user_schemas import (
    AdminUserTrialOut as AdminUserTrialOut,
)
from .user_schemas import (
    AdminUserWithAvatarOut as AdminUserWithAvatarOut,
)


class PromoCreateBody(HttpBodyModel):
    code: str | None = None
    bonus_days: int = Field(default=0, ge=0)
    regular_traffic_gb: float = Field(default=0, ge=0, le=PROMO_TRAFFIC_GRANT_MAX_GB)
    premium_traffic_gb: float = Field(default=0, ge=0, le=PROMO_TRAFFIC_GRANT_MAX_GB)
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
            regular_traffic_gb=float(self.regular_traffic_gb or 0),
            premium_traffic_gb=float(self.premium_traffic_gb or 0),
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
    regular_traffic_gb: float | None = Field(default=None, ge=0, le=PROMO_TRAFFIC_GRANT_MAX_GB)
    premium_traffic_gb: float | None = Field(default=None, ge=0, le=PROMO_TRAFFIC_GRANT_MAX_GB)
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


def _normalize_localized_text(value: Any) -> dict[str, str]:
    """One entry per language code, empty variants dropped.

    An empty tab is how the editor says "this language is not written yet";
    storing it would send an empty message to exactly those customers.
    """

    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for language, text in value.items():
        code = str(language or "").strip().lower().replace("_", "-")
        body = _strip_text(text)
        if code and body:
            normalized[code] = body
    return dict(sorted(normalized.items()))


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


class AdminTariffsCatalogOut(HttpResponseModel):
    default_tariff: str
    referral_welcome_bonus_tariff: str | None = None
    default_currency: str = "rub"
    topup_packages_default: PackageSet | None = None
    tariffs: list[Tariff]

    @classmethod
    def empty(cls) -> AdminTariffsCatalogOut:
        return cls(
            default_tariff="",
            default_currency="rub",
            topup_packages_default=PackageSet.model_validate({"rub": [], "stars": []}),
            tariffs=[],
        )

    @classmethod
    def from_config(cls, config: TariffsConfig) -> AdminTariffsCatalogOut:
        return cls.model_validate(config.model_dump(mode="python", exclude_none=True))

    def to_legacy_payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.model_dump(mode="json", exclude_none=True))


class ProviderCurrencySupportOut(HttpResponseModel):
    id: str
    provider_key: str
    provider_label: str
    settings_path: list[str]
    label: str
    telegram_label: str
    icon: str | None = None
    enabled: bool
    configured: bool
    admin_only: bool
    price_source: str
    currencies: list[str] | None = None
    accepts_any_currency: bool
    supports_default_currency: bool
    directly_supports_default_currency: bool
    default_currency: str
    note: str
    docs_url: str | None = None

    @classmethod
    def from_provider_spec(
        cls,
        spec: PaymentProviderSpec,
        presentation: PaymentProviderPresentation,
        *,
        settings: Settings,
        app: object,
        default_currency: str,
    ) -> ProviderCurrencySupportOut:
        supported = spec.supported_currency_codes(settings)
        return cls(
            id=spec.id,
            provider_key=spec.provider_key,
            provider_label=cls._provider_label(spec),
            settings_path=cls._settings_path(spec),
            label=presentation.webapp_label or spec.label,
            telegram_label=presentation.telegram_label,
            icon=presentation.webapp_icon,
            enabled=spec.is_effectively_enabled(settings),
            configured=spec.is_service_configured(app),
            admin_only=spec.is_admin_only_enabled(settings),
            price_source=spec.price_source,
            currencies=list(supported) if supported is not None else None,
            accepts_any_currency=supported is None,
            supports_default_currency=spec.is_usable_for_payment_currency(
                settings,
                default_currency,
            ),
            directly_supports_default_currency=spec.supports_currency(
                settings,
                default_currency,
            ),
            default_currency=default_currency,
            note=spec.currency_support_note,
            docs_url=spec.currency_support_url,
        )

    @staticmethod
    def _provider_label(spec: PaymentProviderSpec) -> str:
        if spec.id == "platega_sbp":
            return "Platega SBP/card"
        if spec.id == "platega_card":
            return "Platega Card"
        if spec.id == "platega_crypto":
            return "Platega Crypto"
        if spec.id == "platega_international":
            return "Platega International"
        if spec.id == "platega_all_methods":
            return "Platega All methods"
        return str(spec.label or spec.id)

    @staticmethod
    def _settings_path(spec: PaymentProviderSpec) -> list[str]:
        if spec.id == "platega_sbp":
            return ["payments", "platega", "sbp"]
        if spec.id == "platega_card":
            return ["payments", "platega", "card"]
        if spec.id == "platega_crypto":
            return ["payments", "platega", "crypto"]
        if spec.id == "platega_international":
            return ["payments", "platega", "international"]
        if spec.id == "platega_all_methods":
            return ["payments", "platega", "all-methods"]
        return ["payments", str(spec.provider_key or spec.id).replace("_", "-")]


class AdminTariffsOut(HttpResponseModel):
    exists: bool
    path: str
    catalog: AdminTariffsCatalogOut
    provider_currency_support: list[ProviderCurrencySupportOut]
    user_hwid_device_limit: int | None = None

    def to_legacy_payload(self) -> dict[str, Any]:
        payload = cast(dict[str, Any], self.model_dump(mode="json"))
        payload["catalog"] = self.catalog.to_legacy_payload()
        return payload


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
    confirmation: Any = ""


class AdminBroadcastButtonBody(HttpBodyModel):
    """One inline button attached to a broadcast.

    ``kind`` selects how the button URL is produced:
    - ``url`` — explicit ``url`` field;
    - ``promo_bot`` — deep link into the bot applying ``promo_code``;
    - ``promo_webapp`` — link into the Mini App checkout with ``promo_code``;
    - ``webapp_section`` — link that opens the Mini App screen named by
      ``section`` (invite, support, devices, …).
    """

    kind: str = "url"
    label: str = ""
    url: str = ""
    promo_code: str = ""
    section: str = ""
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("labels", mode="before")
    @classmethod
    def _normalize_labels(cls, value: Any) -> dict[str, str]:
        return _normalize_localized_text(value)

    @field_validator("kind", "section", mode="before")
    @classmethod
    def _normalize_kind(cls, value: Any) -> str:
        return _strip_text(value).lower()

    @field_validator("label", "url", "promo_code", mode="before")
    @classmethod
    def _normalize_button_text(cls, value: Any) -> str:
        return _strip_text(value)


class AdminBroadcastBody(HttpBodyModel):
    text: Any = ""
    # One message per language code. ``text`` stays the caption written for
    # every language and is what a client that knows nothing about languages
    # keeps sending.
    texts: dict[str, str] = Field(default_factory=dict)
    email_subjects: dict[str, str] = Field(default_factory=dict)
    target: Any = "all"

    @field_validator("texts", "email_subjects", mode="before")
    @classmethod
    def _normalize_localized(cls, value: Any) -> dict[str, str]:
        return _normalize_localized_text(value)

    channels: list[str] = Field(default_factory=lambda: ["telegram"])
    exclude_blocked_telegram: bool = False
    email_subject: Any = ""
    buttons: list[AdminBroadcastButtonBody] = Field(default_factory=list)
    scheduled_at: datetime | None = None

    @field_validator("text", "target", "email_subject", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return _strip_text(value)

    @field_validator("channels", mode="before")
    @classmethod
    def _normalize_channels(cls, value: Any) -> list[str]:
        if value is None:
            return ["telegram"]
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return ["telegram"]
        normalized = [_strip_text(item).lower() for item in value]
        return [item for item in normalized if item]


class AdminBroadcastScheduleBody(HttpBodyModel):
    scheduled_at: datetime


class AdminBroadcastPreviewBody(HttpBodyModel):
    text: Any = ""
    texts: dict[str, str] = Field(default_factory=dict)
    email_subject: Any = ""
    email_subjects: dict[str, str] = Field(default_factory=dict)

    @field_validator("texts", "email_subjects", mode="before")
    @classmethod
    def _normalize_localized(cls, value: Any) -> dict[str, str]:
        return _normalize_localized_text(value)

    user_id: int | None = None
    mode: str = "render"
    buttons: list[AdminBroadcastButtonBody] = Field(default_factory=list)

    @field_validator("text", "email_subject", mode="before")
    @classmethod
    def _normalize_preview_text(cls, value: Any) -> str:
        return _strip_text(value)

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: Any) -> str:
        mode = _strip_text(value).lower()
        return mode if mode in {"render", "send_telegram"} else "render"

    @field_validator("user_id", mode="before")
    @classmethod
    def _coerce_user_id(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


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


class AdminUserTrafficStrategyBody(HttpBodyModel):
    traffic_limit_strategy: Any = None


class AdminUserExtendBody(HttpBodyModel):
    days: Any = None
    tariff_key: Any = None
    extend_hwid_devices: Any = None
    apply_tariff_hwid_limit: Any = False


class AdminUserTariffBody(HttpBodyModel):
    tariff_key: Any = None
    apply_tariff_hwid_limit: Any = False


class AdminUserBalanceAdjustmentBody(HttpBodyModel):
    mode: Literal["add", "subtract", "set"] = "add"
    amount: float = Field(ge=0, allow_inf_nan=False)
    reason: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=128)


class AdminUserBalanceConversionBody(HttpBodyModel):
    direction: Literal["partner_to_user", "user_to_partner"]
    amount: float = Field(gt=0, allow_inf_nan=False)
    reason: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=128)


class PromoOptionOut(HttpResponseModel):
    code: str
    max_activations: int
    current_activations: int
    user_id: int | None = None

    @classmethod
    def from_orm_promo(cls, promo: Any) -> PromoOptionOut:
        return cls(
            code=str(promo.code),
            max_activations=int(promo.max_activations),
            current_activations=int(promo.current_activations or 0),
            user_id=int(promo.user_id) if getattr(promo, "user_id", None) else None,
        )


class PromoOut(HttpResponseModel):
    id: int
    code: str
    bot_link: str | None = None
    webapp_link: str | None = None
    bonus_days: int
    regular_traffic_gb: float = 0
    premium_traffic_gb: float = 0
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
    # Set by whoever issued the code for one customer; the sole personal
    # signal. Read-only here: the admin API never assigns or clears an owner.
    user_id: int | None = None
    user_username: str | None = None
    user_name: str | None = None

    @classmethod
    def from_orm_promo(
        cls,
        promo: Any,
        *,
        bot_link: str | None = None,
        webapp_link: str | None = None,
        owner: tuple[str | None, str | None] | None = None,
    ) -> PromoOut:
        effects = PromoEffects.from_model(promo)
        return cls(
            id=int(promo.promo_code_id),
            code=promo.code,
            bot_link=bot_link,
            webapp_link=webapp_link,
            bonus_days=int(promo.bonus_days),
            regular_traffic_gb=effects.regular_traffic_gb,
            premium_traffic_gb=effects.premium_traffic_gb,
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
            user_id=int(promo.user_id) if getattr(promo, "user_id", None) else None,
            user_username=owner[0] if owner else None,
            user_name=owner[1] if owner else None,
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
    regular_traffic_gb: float | None = None
    premium_traffic_gb: float | None = None
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
    granted_regular_traffic_gb: float | None = None
    granted_premium_traffic_gb: float | None = None

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
            regular_traffic_gb=_float_or_none(getattr(activation, "regular_traffic_gb", None)),
            premium_traffic_gb=_float_or_none(getattr(activation, "premium_traffic_gb", None)),
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
            granted_regular_traffic_gb=_float_or_none(
                getattr(activation, "granted_regular_traffic_gb", None)
            ),
            granted_premium_traffic_gb=_float_or_none(
                getattr(activation, "granted_premium_traffic_gb", None)
            ),
        )


class AdminStatsOut(HttpResponseModel):
    users: dict[str, Any]
    financial: dict[str, Any]
    panel_sync: AdminPanelSyncOut
    recent_payments: list[PaymentOut]
    currency_symbol: str
    panel: dict[str, Any] | None = None
    queue: dict[str, Any] | None = None


class AdminPanelCompatibilityOut(HttpResponseModel):
    version: str | None = None
    generation: str
    support_status: str
    certified_versions: list[str]
    capabilities: list[str]
    observed_capabilities: dict[str, bool]


class AdminHealthOut(HttpResponseModel):
    alerts: list[dict[str, Any]]
    checked_at: datetime
    panel_compatibility: AdminPanelCompatibilityOut | None = None


class AdminPaymentsListOut(HttpResponseModel):
    payments: list[PaymentOut]
    page: int
    page_size: int
    total: int
