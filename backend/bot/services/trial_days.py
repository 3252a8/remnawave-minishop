from datetime import datetime
from typing import Any, Literal

TrialDaysStrategy = Literal["add_remaining", "start_from_payment"]

TRIAL_DAYS_ADD_REMAINING: TrialDaysStrategy = "add_remaining"
TRIAL_DAYS_START_FROM_PAYMENT: TrialDaysStrategy = "start_from_payment"


def normalize_trial_days_strategy(value: object) -> TrialDaysStrategy:
    if value == TRIAL_DAYS_START_FROM_PAYMENT:
        return TRIAL_DAYS_START_FROM_PAYMENT
    return TRIAL_DAYS_ADD_REMAINING


def paid_subscription_period_start(
    now: datetime,
    active_subscription: Any | None,
    active_billing_model: str | None,
    active_is_trial: bool,
    strategy: TrialDaysStrategy,
) -> datetime:
    active_end_at = getattr(active_subscription, "end_date", None)
    if (
        active_subscription is not None
        and active_billing_model != "traffic"
        and active_end_at is not None
        and active_end_at > now
        and not (active_is_trial and strategy == TRIAL_DAYS_START_FROM_PAYMENT)
    ):
        return active_end_at
    return now
