"""Typed payload contracts for the in-process domain event bus.

Event models are pydantic v2 ``BaseModel`` classes with ``extra="forbid"``:
emit sites construct a model first, then publish ``model.to_payload()`` through
``events.emit``. The bus itself stays deliberately unvalidated so subscriber
failures and validation mistakes cannot change its never-raise contract.

Datetimes should be typed as ``datetime`` on concrete models and serialized via
``model_dump(mode="json")``; this keeps the wire payload as the same flat dict of
primitives and ISO-8601 strings that the existing ``events.iso`` helper emits.
Optional event keys should be declared as ``Optional[...] = None`` when the
current contract allows ``None`` for unknown values.

``model_construct`` is available for trusted internal data only after profiling
shows validation overhead on a hot path. The default is normal validation at the
emit call site, because catching drift there is the point of these contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, field_serializer

AutoRenewFailureReason = Literal[
    "provider_unavailable",
    "saved_payment_method_missing",
    "renewal_quote_unavailable",
    "provider_request_failed",
    "provider_rejected",
    "provider_webhook_failed",
]


class EventPayload(BaseModel):
    """Base class for validated event payload models."""

    model_config = ConfigDict(extra="forbid")

    EVENT_NAME: ClassVar[str]

    @field_serializer("*", when_used="json")
    def _serialize_payload_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def to_payload(
        self,
        *,
        exclude_unset: bool = False,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        """Return the flat JSON-compatible dict passed to ``events.emit``."""
        payload = self.model_dump(
            mode="json",
            exclude_unset=exclude_unset,
            exclude_none=exclude_none,
        )
        for key in ("duration_days", "purchased_subscription_days"):
            if payload.get(key) is None:
                payload.pop(key, None)
        return payload


class PaymentSucceededPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "payment.succeeded"

    user_id: int
    payment_db_id: int
    provider: str
    notification_provider: str
    amount: float
    currency: str
    sale_mode: str
    tariff_key: str | None = None
    months: int | None = None
    duration_days: int | None = None
    traffic_gb: float | None = None
    purchased_hwid_devices: int | None = None
    promo_code_id: int | None = None
    base_amount: float | None = None
    discount_amount: float | None = None
    end_date: datetime | None = None
    is_auto_renew: bool
    renewal_subscription_id: int | None = None


class SubscriptionAutoRenewFailedPayload(EventPayload):
    """A normalized failed attempt to extend an existing subscription.

    This intentionally records only stable, provider-neutral identifiers and
    reason codes. Provider responses may contain customer or credential data
    and must stay in provider logs rather than in the event contract.
    """

    EVENT_NAME: ClassVar[str] = "subscription.auto_renew_failed"

    user_id: int
    subscription_id: int
    provider: str
    reason_code: AutoRenewFailureReason
    payment_db_id: int | None = None
    provider_payment_id: str | None = None
    renewal_cycle_end: datetime | None = None
    retryable: bool
    occurred_at: datetime


class SubscriptionExpiredPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "subscription.expired"

    user_id: int
    subscription_id: int | None = None
    tariff_key: str | None = None
    end_date: datetime | None = None


class SubscriptionLapsedPayload(SubscriptionExpiredPayload):
    EVENT_NAME: ClassVar[str] = "subscription.lapsed"


class PaymentCanceledPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "payment.canceled"

    user_id: int
    payment_db_id: int | None = None
    provider: str | None = None
    provider_payment_id: str | None = None
    status: str | None = None
    message_key: str | None = None
    cancellation_party: str | None = None
    cancellation_reason: str | None = None
    auto_renew_cycle_id: int | None = None
    auto_renew_retry_scheduled: bool = False
    retry_at: datetime | None = None


class SubscriptionCreatedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "subscription.created"

    user_id: int
    subscription_id: int | None = None
    tariff_key: str | None = None
    end_date: datetime | None = None
    provider: str | None = None
    months: int | None = None
    duration_days: int | None = None
    payment_db_id: int | None = None


class SubscriptionExtendedPayload(SubscriptionCreatedPayload):
    EVENT_NAME: ClassVar[str] = "subscription.extended"


class TrialActivatedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "trial.activated"

    user_id: int
    end_date: datetime | None = None
    days: int
    traffic_gb: float | None = None


class PlansViewedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "plans.viewed"

    user_id: int
    source: Literal["webapp", "bot"]
    plans_count: int
    tariff_key: str | None = None


class BotStartedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "bot.started"

    user_id: int
    returning: bool
    source: Literal["direct", "referral", "promo", "ad", "ticket", "notifications"]
    start_param: str | None = None


class UserRegisteredPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "user.registered"

    user_id: int
    account_id: str | None = None
    minishop_id: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    email: str | None = None
    language: str | None = None
    referred_by_id: int | None = None
    registered_via: Literal[
        "telegram",
        "email",
        "discord_oauth",
        "google_oauth",
        "yandex_oauth",
        "panel_sync",
        "unknown",
    ]

    def to_payload(
        self,
        *,
        exclude_unset: bool = False,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        payload = super().to_payload(exclude_unset=exclude_unset, exclude_none=exclude_none)
        for field in ("account_id", "minishop_id"):
            if payload.get(field) is None:
                payload.pop(field, None)
        return payload


class AccountEmailLinkedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "account.email_linked"

    user_id: int
    email: str
    first_link: bool
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None


class AccountTelegramLinkedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "account.telegram_linked"

    user_id: int
    telegram_id: int | None = None
    first_link: bool
    email: str | None = None
    username: str | None = None
    first_name: str | None = None


class AccountExternalIdentityLinkedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "account.external_identity_linked"

    user_id: int
    provider: Literal["discord", "google", "yandex"]
    link_source: Literal["settings", "email_confirmation", "provider_verified_email"]
    email: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None


class AccountMergedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "account.merged"

    source_user_id: int
    target_user_id: int
    source_minishop_id: str | None = None
    target_minishop_id: str | None = None
    reason: str
    send_user_email: bool
    source_panel_user_uuid: str | None = None
    target_panel_user_uuid: str | None = None
    email: str | None = None
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    language: str | None = None
    final_end_date: datetime | None = None

    def to_payload(
        self,
        *,
        exclude_unset: bool = False,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        payload = super().to_payload(exclude_unset=exclude_unset, exclude_none=exclude_none)
        for key in ("source_minishop_id", "target_minishop_id"):
            if payload.get(key) is None:
                payload.pop(key, None)
        return payload


class PromoCodeAppliedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "promo_code.applied"

    user_id: int
    code: str
    bonus_days: int
    regular_traffic_gb: float = 0
    premium_traffic_gb: float = 0
    new_end_date: datetime | None = None


class ReferralBonusGrantedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "referral.bonus_granted"

    referee_user_id: int
    referee_bonus_days: int | None = None
    referee_new_end_date: datetime | None = None
    inviter_bonus_applied: bool
    inviter_user_id: int | None = None
    inviter_bonus_days: int | None = None
    inviter_bonus_end_date: datetime | None = None
    inviter_bonus_kind: Literal["extended", "new_sub"] | None = None
    referee_name: str | None = None
    payment_db_id: int | None = None
    purchased_subscription_months: int | None = None
    purchased_subscription_days: int | None = None
    tariff_key: str | None = None
    one_bonus_per_referee: bool | None = None
    reason: Literal["payment", "welcome"]


class SupportTicketCreatedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "support.ticket_created"

    user_id: int
    ticket_id: int
    category: str
    priority: str


class PanelWebhookReceivedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "panel.webhook_received"

    event: str
    panel_user_uuid: str | None = None
    telegram_id: int | str | None = None


class DeviceConnectedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "device.connected"

    user_id: int
    subscription_id: int
    panel_user_uuid: str | None = None
    device_label: str
    platform: str | None = None
    os_version: str | None = None
    current_devices: int | None = None
    device_limit: int | None = None
    occurred_at: datetime


class DeviceLimitReachedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "device.limit_reached"

    user_id: int
    subscription_id: int
    tariff_key: str | None = None
    current_devices: int
    device_limit: int
    device_topup_available: bool
    occurred_at: datetime


class PartnerApplicationSubmittedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.application_submitted"

    application_id: int
    user_id: int
    status: str
    submitted_at: datetime


class PartnerApplicationDecidedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.application_decided"

    application_id: int
    partner_id: int | None = None
    user_id: int | None = None
    status: str
    decided_at: datetime


class PartnerStatusChangedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.status_changed"

    partner_id: int
    user_id: int | None = None
    old_status: str
    status: str
    changed_at: datetime


class PartnerClientAttributedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.client_attributed"

    partner_id: int
    partner_client_id: int
    client_user_id: int
    source: str
    attributed_at: datetime


class PartnerCommissionRecordedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.commission_recorded"

    partner_id: int
    commission_id: int
    payment_db_id: int
    status: str
    currency: str
    gross_amount_minor: int
    commission_amount_minor: int
    available_at: datetime


class PartnerCommissionAvailablePayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.commission_available"

    partner_id: int
    commission_id: int
    currency: str
    commission_amount_minor: int
    available_at: datetime


class PartnerCommissionReversedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.commission_reversed"

    partner_id: int
    commission_id: int
    payment_db_id: int | None = None
    currency: str
    commission_amount_minor: int
    reversed_at: datetime


class PartnerWithdrawalRequestedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.withdrawal_requested"

    partner_id: int
    user_id: int
    withdrawal_id: int
    status: str
    currency: str
    currency_scale: int
    amount_minor: int
    requested_at: datetime


class PartnerWithdrawalStatusChangedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.withdrawal_status_changed"

    partner_id: int
    user_id: int | None = None
    withdrawal_id: int
    old_status: str
    status: str
    status_version: int
    currency: str
    currency_scale: int
    amount_minor: int
    settlement_amount: str | None = None
    external_reference: str | None = None
    changed_at: datetime


class PartnerBalanceAdjustedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.balance_adjusted"

    partner_id: int
    currency: str
    amount_minor: int
    balance_minor: int
    adjusted_at: datetime


class PartnerBalanceSpentPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "partner.balance_spent"

    partner_id: int
    payment_db_id: int
    currency: str
    amount_minor: int
    spent_at: datetime
