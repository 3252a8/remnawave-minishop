"""Public account payment summaries without identity or administrator fields."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import Field

from bot.app.web.http_contracts import HttpResponseModel
from bot.app.web.payment_purchases import (
    PaymentPurchaseOut,
    payment_purchases,
    traffic_gb_split,
)
from db.models import Payment
from db.payment_history import PaymentHistoryState, payment_history_state


def _active_checkout_url(payment: Payment, state: PaymentHistoryState) -> str | None:
    expires_at = payment.checkout_expires_at
    if (
        state != "awaiting_payment"
        or expires_at is None
        or payment.fulfilled_at is not None
        or payment.reversed_at is not None
    ):
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    url = str(payment.provider_payment_url or "").strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        return None
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
        ):
            return None
    except ValueError:
        return None
    return url


class PaymentHistoryItemOut(HttpResponseModel):
    payment_id: int
    provider: str | None = None
    funding_source: str = "external"
    amount: float
    currency: str | None = None
    status: str | None = None
    history_state: PaymentHistoryState
    checkout_url: str | None = Field(
        default=None, description="Active checkout link, only for a payment awaiting payment."
    )
    description: str | None = None
    created_at: datetime | None = None
    traffic_regular_gb: float | None = None
    traffic_premium_gb: float | None = None
    checkout_discount_amount: float | None = None
    subscription_duration_months: int | None = None
    subscription_duration_days: int | None = None
    period_semantics: str | None = None
    sale_mode: str | None = None
    purchased_gb: float | None = None
    purchased_hwid_devices: int | None = None
    purchases: list[PaymentPurchaseOut] = Field(default_factory=list)

    @classmethod
    def from_orm_payment(cls, payment: Payment) -> PaymentHistoryItemOut:
        regular_gb, premium_gb = traffic_gb_split(payment)
        state = payment_history_state(payment)
        return cls(
            payment_id=int(payment.payment_id),
            provider=payment.provider,
            funding_source=str(payment.funding_source or "external"),
            amount=float(payment.amount),
            currency=payment.currency,
            status=payment.status,
            history_state=state,
            checkout_url=_active_checkout_url(payment, state),
            description=payment.description,
            created_at=payment.created_at,
            traffic_regular_gb=regular_gb,
            traffic_premium_gb=premium_gb,
            checkout_discount_amount=payment.checkout_discount_amount,
            subscription_duration_months=payment.subscription_duration_months,
            subscription_duration_days=payment.subscription_duration_days,
            period_semantics=payment.period_semantics,
            sale_mode=payment.sale_mode,
            purchased_gb=payment.purchased_gb,
            purchased_hwid_devices=payment.purchased_hwid_devices,
            purchases=payment_purchases(payment),
        )
