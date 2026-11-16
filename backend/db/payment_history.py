"""Payment lifecycle states used by the account history."""

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from db.models import Payment

PaymentHistoryState = Literal[
    "awaiting_payment", "processing", "crediting", "review", "completed", "refunded", "failed"
]

CONFIRMED_PAYMENT_STATUSES = frozenset(
    {
        "succeeded",
        "succeeded_pending_finalization",
        "succeeded_pending_review",
        "refunded",
        "reversed",
    }
)
PROCESSING_PAYMENT_STATUSES = frozenset(
    {
        "process",
        "processing",
        "paying",
        "authorized",
        "awaitingauthentication",
        "waiting_for_capture",
        "underpaid",
        "refunding",
    }
)
AWAITING_PAYMENT_STATUSES = frozenset({"pending", "active", "created", "new", "open", "waiting"})


def payment_history_state(payment: Payment) -> PaymentHistoryState:
    status = str(payment.status or "").strip().lower()
    if status == "succeeded_pending_finalization":
        return "crediting"
    if status == "succeeded_pending_review":
        return "review"
    if status in {"refunded", "reversed"}:
        return "refunded"
    if status == "succeeded":
        return "completed"
    if status in PROCESSING_PAYMENT_STATUSES:
        return "processing"
    if status in AWAITING_PAYMENT_STATUSES or status.startswith("pending_"):
        return "awaiting_payment"
    return "failed"


def active_checkout_url(payment: Payment, state: PaymentHistoryState) -> str | None:
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
