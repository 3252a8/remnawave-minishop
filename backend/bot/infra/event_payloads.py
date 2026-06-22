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
        return self.model_dump(
            mode="json",
            exclude_unset=exclude_unset,
            exclude_none=exclude_none,
        )


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
    traffic_gb: float | None = None
    purchased_hwid_devices: int | None = None
    end_date: datetime | None = None
    is_auto_renew: bool


class PaymentCanceledPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "payment.canceled"

    user_id: int
    payment_db_id: int | None = None
    provider: str | None = None
    provider_payment_id: str | None = None
    status: str | None = None
    message_key: str | None = None


class SubscriptionCreatedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "subscription.created"

    user_id: int
    subscription_id: int | None = None
    tariff_key: str | None = None
    end_date: datetime | None = None
    provider: str | None = None
    months: int | None = None
    payment_db_id: int | None = None


class SubscriptionExtendedPayload(SubscriptionCreatedPayload):
    EVENT_NAME: ClassVar[str] = "subscription.extended"


class TrialActivatedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "trial.activated"

    user_id: int
    end_date: datetime | None = None
    days: int
    traffic_gb: float | None = None


class UserRegisteredPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "user.registered"

    user_id: int
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    email: str | None = None
    language: str | None = None
    referred_by_id: int | None = None
    registered_via: Literal["telegram", "email", "panel_sync", "unknown"]


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


class AccountMergedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "account.merged"

    source_user_id: int
    target_user_id: int
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


class PromoCodeAppliedPayload(EventPayload):
    EVENT_NAME: ClassVar[str] = "promo_code.applied"

    user_id: int
    code: str
    bonus_days: int
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
