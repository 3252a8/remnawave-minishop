"""Immutable tariff and referral terms of a newly issued fixed-day order."""

import json
from dataclasses import dataclass
from typing import Any

from config.subscription_periods import days_to_legacy_months, sale_mode_duration_days
from config.tariffs_config import Tariff


@dataclass(frozen=True)
class SubscriptionOrderTerms:
    duration_days: int
    tariff: Tariff | None
    inviter_days: int
    referee_days: int


def freeze_subscription_terms(settings: Any, sale_mode: str) -> str | None:
    days = sale_mode_duration_days(sale_mode)
    if days is None or sale_mode.split("@", 1)[0].split("|", 1)[0] != "subscription":
        return None
    key = sale_mode.split("@", 1)[1].split("|", 1)[0] if "@" in sale_mode else None
    try:
        config = settings.tariffs_config
    except AttributeError:
        config = None
    tariff = config.get(key) if config is not None and key else None
    if tariff is not None:
        period = tariff.period_for_days(days)
        inviter = tariff.referral_inviter_bonus_days(period) if period is not None else 0
        referee = tariff.referral_referee_bonus_days(period) if period is not None else 0
    else:
        alias = days_to_legacy_months(days)
        try:
            inviter = settings.referral_bonus_inviter.get(alias, 0)
            referee = settings.referral_bonus_referee.get(alias, 0)
        except AttributeError:
            inviter, referee = 0, 0
    return json.dumps(
        {
            "version": 1,
            "duration_days": days,
            "tariff": tariff.model_dump(mode="json") if tariff is not None else None,
            "inviter_days": int(inviter or 0),
            "referee_days": int(referee or 0),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def read_subscription_terms(payment: Any) -> SubscriptionOrderTerms | None:
    raw = getattr(payment, "subscription_terms_snapshot", None)
    if not isinstance(raw, str) or not raw:
        return None
    data = json.loads(raw)
    if data.get("version") != 1 or data.get("duration_days") != payment.subscription_duration_days:
        raise ValueError("Subscription order terms do not match the saved duration")
    tariff = Tariff.model_validate(data["tariff"]) if data.get("tariff") else None
    if tariff is not None and tariff.key != payment.tariff_key:
        raise ValueError("Subscription order terms do not match the saved tariff")
    return SubscriptionOrderTerms(
        data["duration_days"], tariff, int(data["inviter_days"]), int(data["referee_days"])
    )
