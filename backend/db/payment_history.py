"""Payment lifecycle states used by the account history."""

from typing import Literal

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
