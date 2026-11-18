"""Renewal consent for a trial or administrator-granted subscription."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, case, func

from db.models import Subscription

GRANT_PROVIDERS = frozenset({"trial", "admin"})
BALANCE_RECURRING_PROVIDERS = frozenset({"user_balance", "partner_balance"})


class GrantBalanceRenewalCycleStarted(ValueError):
    """The current cycle already has its immutable payment terms."""


@dataclass(frozen=True, slots=True)
class GrantBalanceRenewal:
    provider: str
    tariff_key: str
    duration_days: int


def subscription_provider(subscription: Any) -> str:
    return str(getattr(subscription, "provider", "") or "").strip().lower()


def grant_balance_renewal(subscription: Any) -> GrantBalanceRenewal | None:
    if subscription_provider(subscription) not in GRANT_PROVIDERS:
        return None
    provider = getattr(subscription, "balance_renewal_provider", None)
    tariff_key = getattr(subscription, "balance_renewal_tariff_key", None)
    duration_days = getattr(subscription, "balance_renewal_duration_days", None)
    if (
        provider in BALANCE_RECURRING_PROVIDERS
        and isinstance(tariff_key, str)
        and (tariff_key or provider == "user_balance")
        and isinstance(duration_days, int)
        and duration_days > 0
    ):
        return GrantBalanceRenewal(provider, tariff_key, duration_days)
    return None


def renewal_provider(subscription: Any) -> str:
    plan = grant_balance_renewal(subscription)
    return plan.provider if plan else subscription_provider(subscription)


def renewal_provider_column() -> ColumnElement[str]:
    provider = func.lower(func.trim(Subscription.provider))
    return case(
        (
            provider.in_(GRANT_PROVIDERS)
            & Subscription.balance_renewal_provider.in_(BALANCE_RECURRING_PROVIDERS)
            & Subscription.balance_renewal_tariff_key.is_not(None)
            & (
                (Subscription.balance_renewal_tariff_key != "")
                | (Subscription.balance_renewal_provider == "user_balance")
            )
            & (Subscription.balance_renewal_duration_days > 0),
            Subscription.balance_renewal_provider,
        ),
        else_=provider,
    )
