from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bot.services.trial_days import (
    TRIAL_DAYS_ADD_REMAINING,
    TrialDaysStrategy,
    normalize_trial_days_strategy,
)


@dataclass(frozen=True)
class CheckoutAddonGrants:
    tariff_key: str | None = None
    months: int | None = None
    duration_days: int | None = None
    base_subscription_amount: float | None = None
    addons_amount: float = 0.0
    device_count: int = 0
    device_traffic_bonus_gb: float = 0.0
    regular_limit_gb: float | None = None
    premium_limit_gb: float | None = None
    regular_monthly_amount: float = 0.0
    premium_monthly_amount: float = 0.0
    regular_monthly_stars: int = 0
    premium_monthly_stars: int = 0
    regular_immediate_applies: bool = False
    premium_immediate_applies: bool = False
    legacy_regular_topup_gb: float = 0.0
    legacy_premium_topup_gb: float = 0.0
    active_context_present: bool = False
    active_subscription_id: int | None = None
    active_end_at: datetime | None = None
    trial_days_strategy: TrialDaysStrategy = TRIAL_DAYS_ADD_REMAINING

    @property
    def has_addons(self) -> bool:
        return bool(
            self.device_count > 0
            or self.regular_limit_gb is not None
            or self.premium_limit_gb is not None
            or self.legacy_regular_topup_gb > 0
            or self.legacy_premium_topup_gb > 0
        )


def parse_checkout_bundle_snapshot(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("version") not in {1, 2, 3}:
        return None
    if not isinstance(payload.get("items"), list):
        return None
    return payload


def _finite_non_negative(value: Any) -> float:
    try:
        parsed = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) and parsed >= 0 else 0.0


def checkout_addon_grants(value: str | None) -> CheckoutAddonGrants:
    snapshot = parse_checkout_bundle_snapshot(value)
    if snapshot is None:
        return CheckoutAddonGrants()

    device_count = 0
    device_traffic_bonus_gb = 0.0
    version = int(snapshot.get("version") or 1)
    regular_limit_gb = None
    premium_limit_gb = None
    regular_future_amount = 0.0
    premium_future_amount = 0.0
    regular_future_stars = 0
    premium_future_stars = 0
    regular_immediate_applies = False
    premium_immediate_applies = False
    legacy_regular_topup_gb = 0.0
    legacy_premium_topup_gb = 0.0
    seen_kinds: set[str] = set()
    for raw_item in snapshot["items"]:
        if not isinstance(raw_item, dict):
            continue
        kind = str(raw_item.get("kind") or "")
        if kind in seen_kinds:
            continue
        seen_kinds.add(kind)
        units = _finite_non_negative(raw_item.get("extra_units"))
        if kind == "devices" and units.is_integer():
            device_count = int(units)
            device_traffic_bonus_gb = _finite_non_negative(raw_item.get("traffic_bonus_gb"))
        elif kind == "traffic":
            if version >= 2:
                regular_limit_gb = _finite_non_negative(raw_item.get("total_units"))
                regular_future_amount = _finite_non_negative(raw_item.get("future_amount"))
                regular_future_stars = int(
                    _finite_non_negative(raw_item.get("future_stars_amount"))
                )
                regular_immediate_applies = bool(raw_item.get("immediate_applies"))
            else:
                legacy_regular_topup_gb = units
        elif kind == "premium_traffic":
            if version >= 2:
                premium_limit_gb = _finite_non_negative(raw_item.get("total_units"))
                premium_future_amount = _finite_non_negative(raw_item.get("future_amount"))
                premium_future_stars = int(
                    _finite_non_negative(raw_item.get("future_stars_amount"))
                )
                premium_immediate_applies = bool(raw_item.get("immediate_applies"))
            else:
                legacy_premium_topup_gb = units

    active_context = snapshot.get("active_context")
    active_context_present = version >= 2 and "active_context" in snapshot
    active_subscription_id = None
    active_end_at = None
    if isinstance(active_context, dict):
        try:
            raw_subscription_id = active_context.get("subscription_id")
            active_subscription_id = (
                int(raw_subscription_id) if raw_subscription_id is not None else None
            )
        except (TypeError, ValueError):
            active_subscription_id = None
        raw_end_at = active_context.get("end_at")
        if raw_end_at:
            try:
                active_end_at = datetime.fromisoformat(str(raw_end_at).replace("Z", "+00:00"))
                if active_end_at.tzinfo is None:
                    active_end_at = active_end_at.replace(tzinfo=UTC)
            except ValueError:
                active_end_at = None

    raw_base_amount = snapshot.get("base_subscription_amount")
    base_subscription_amount = (
        _finite_non_negative(raw_base_amount) if raw_base_amount is not None else None
    )
    try:
        raw_months = snapshot.get("months")
        months = int(raw_months) if raw_months is not None else None
    except (TypeError, ValueError):
        months = None
    if months is not None and months <= 0:
        months = None
    tariff_key = str(snapshot.get("tariff_key") or "").strip() or None
    duration_days = int(snapshot["duration_days"]) if version >= 3 else None
    factor = (
        float(snapshot.get("addon_period_factor") or 0) if version >= 3 else max(1, months or 1)
    )
    if factor <= 0 or (duration_days is not None and duration_days <= 0):
        raise ValueError("invalid checkout billing period")
    return CheckoutAddonGrants(
        duration_days=duration_days,
        tariff_key=tariff_key,
        months=months,
        base_subscription_amount=base_subscription_amount,
        addons_amount=_finite_non_negative(snapshot.get("addons_amount")),
        device_count=device_count,
        device_traffic_bonus_gb=device_traffic_bonus_gb,
        regular_limit_gb=regular_limit_gb,
        premium_limit_gb=premium_limit_gb,
        regular_monthly_amount=regular_future_amount / factor,
        premium_monthly_amount=premium_future_amount / factor,
        regular_monthly_stars=round(regular_future_stars / factor),
        premium_monthly_stars=round(premium_future_stars / factor),
        regular_immediate_applies=regular_immediate_applies,
        premium_immediate_applies=premium_immediate_applies,
        legacy_regular_topup_gb=legacy_regular_topup_gb,
        legacy_premium_topup_gb=legacy_premium_topup_gb,
        active_context_present=active_context_present,
        active_subscription_id=active_subscription_id,
        active_end_at=active_end_at,
        trial_days_strategy=normalize_trial_days_strategy(snapshot.get("trial_days_strategy")),
    )
