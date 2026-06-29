from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

PROMO_APPLIES_TO_ALL = "all"
PROMO_APPLIES_TO_SUBSCRIPTION = "subscription"
PROMO_APPLIES_TO_TRAFFIC = "traffic"
PROMO_APPLIES_TO_TRAFFIC_TOPUP = "traffic_topup"
PROMO_APPLIES_TO_HWID = "hwid"

ALLOWED_PROMO_SCOPES = frozenset(
    {
        PROMO_APPLIES_TO_ALL,
        PROMO_APPLIES_TO_SUBSCRIPTION,
        PROMO_APPLIES_TO_TRAFFIC,
        PROMO_APPLIES_TO_TRAFFIC_TOPUP,
        PROMO_APPLIES_TO_HWID,
    }
)


class PromoEffectsValidationError(ValueError):
    """Raised when a bonus-code effect set is not internally consistent."""


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    return int(number)


def sale_mode_bonus_scope(sale_mode_base: str) -> str:
    base = str(sale_mode_base or "subscription").split("@", 1)[0].split("|", 1)[0]
    if base == "subscription":
        return PROMO_APPLIES_TO_SUBSCRIPTION
    if base in {"traffic", "traffic_package"}:
        return PROMO_APPLIES_TO_TRAFFIC
    if base in {"topup", "premium_topup"}:
        return PROMO_APPLIES_TO_TRAFFIC_TOPUP
    if base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
        return PROMO_APPLIES_TO_HWID
    return base


@dataclass(frozen=True)
class PromoEffects:
    bonus_days: int = 0
    discount_percent: float | None = None
    duration_multiplier: float = 1.0
    traffic_multiplier: float = 1.0
    applies_to: str = PROMO_APPLIES_TO_ALL
    min_subscription_months: int | None = None
    min_traffic_gb: float | None = None

    @classmethod
    def from_model(cls, promo: Any) -> "PromoEffects":
        discount = _optional_float(getattr(promo, "discount_percent", None))
        duration_multiplier = _optional_float(getattr(promo, "duration_multiplier", None))
        traffic_multiplier = _optional_float(getattr(promo, "traffic_multiplier", None))
        applies_to = str(getattr(promo, "applies_to", None) or PROMO_APPLIES_TO_ALL).strip()
        min_subscription_months = _optional_int(getattr(promo, "min_subscription_months", None))
        min_traffic_gb = _optional_float(getattr(promo, "min_traffic_gb", None))
        return cls(
            bonus_days=max(0, int(getattr(promo, "bonus_days", 0) or 0)),
            discount_percent=discount if discount and discount > 0 else None,
            duration_multiplier=duration_multiplier if duration_multiplier else 1.0,
            traffic_multiplier=traffic_multiplier if traffic_multiplier else 1.0,
            applies_to=applies_to if applies_to in ALLOWED_PROMO_SCOPES else PROMO_APPLIES_TO_ALL,
            min_subscription_months=min_subscription_months,
            min_traffic_gb=min_traffic_gb,
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PromoEffects":
        model = type("PromoEffectsPayload", (), dict(payload))()
        return cls.from_model(model)

    @classmethod
    def from_payment_snapshot(cls, payment: Any) -> "PromoEffects | None":
        summary = getattr(payment, "promo_effect_summary", None)
        has_snapshot = summary is not None or any(
            getattr(payment, attr, None) is not None
            for attr in (
                "promo_bonus_days",
                "promo_discount_percent",
                "promo_duration_multiplier",
                "promo_traffic_multiplier",
                "promo_applies_to",
                "promo_min_subscription_months",
                "promo_min_traffic_gb",
            )
        )
        if not has_snapshot:
            return None
        discount = _optional_float(getattr(payment, "promo_discount_percent", None))
        applies_to = str(getattr(payment, "promo_applies_to", None) or PROMO_APPLIES_TO_ALL).strip()
        return cls(
            bonus_days=max(0, int(getattr(payment, "promo_bonus_days", 0) or 0)),
            discount_percent=discount if discount and discount > 0 else None,
            duration_multiplier=_optional_float(getattr(payment, "promo_duration_multiplier", None))
            or 1.0,
            traffic_multiplier=_optional_float(getattr(payment, "promo_traffic_multiplier", None))
            or 1.0,
            applies_to=applies_to if applies_to in ALLOWED_PROMO_SCOPES else PROMO_APPLIES_TO_ALL,
            min_subscription_months=_optional_int(
                getattr(payment, "promo_min_subscription_months", None)
            ),
            min_traffic_gb=_optional_float(getattr(payment, "promo_min_traffic_gb", None)),
        )

    @property
    def has_discount(self) -> bool:
        return self.discount_percent is not None and self.discount_percent > 0

    @property
    def has_multiplier(self) -> bool:
        return self.duration_multiplier > 1.0 or self.traffic_multiplier > 1.0

    @property
    def has_threshold(self) -> bool:
        return self.min_subscription_months is not None or self.min_traffic_gb is not None

    @property
    def has_effect(self) -> bool:
        return self.bonus_days > 0 or self.has_discount or self.has_multiplier

    @property
    def is_bonus_days_only(self) -> bool:
        return (
            self.bonus_days > 0
            and not self.has_discount
            and not self.has_multiplier
            and not self.has_threshold
            and self.applies_to in {PROMO_APPLIES_TO_ALL, PROMO_APPLIES_TO_SUBSCRIPTION}
        )

    def applies_to_sale_mode(self, sale_mode_base: str) -> bool:
        scope = sale_mode_bonus_scope(sale_mode_base)
        return self.applies_to == PROMO_APPLIES_TO_ALL or self.applies_to == scope

    def meets_threshold(
        self,
        *,
        sale_mode_base: str,
        months: int | None,
        traffic_gb: float | None,
    ) -> bool:
        scope = sale_mode_bonus_scope(sale_mode_base)
        if scope == PROMO_APPLIES_TO_SUBSCRIPTION and self.min_subscription_months is not None:
            return months is not None and int(months) >= self.min_subscription_months
        if (
            scope
            in {
                PROMO_APPLIES_TO_TRAFFIC,
                PROMO_APPLIES_TO_TRAFFIC_TOPUP,
            }
            and self.min_traffic_gb is not None
        ):
            return traffic_gb is not None and float(traffic_gb) >= self.min_traffic_gb
        return True


def validate_effects(
    effects: PromoEffects,
    *,
    max_duration_multiplier: float = 12.0,
    max_traffic_multiplier: float = 12.0,
) -> None:
    errors: list[str] = []
    if effects.applies_to not in ALLOWED_PROMO_SCOPES:
        errors.append("invalid_applies_to")
    if not effects.has_effect:
        errors.append("empty_effect")
    if effects.bonus_days < 0:
        errors.append("invalid_bonus_days")
    if effects.discount_percent is not None and not (0 < effects.discount_percent <= 100):
        errors.append("invalid_discount_percent")
    if not (1.0 <= effects.duration_multiplier <= max_duration_multiplier):
        errors.append("invalid_duration_multiplier")
    if not (1.0 <= effects.traffic_multiplier <= max_traffic_multiplier):
        errors.append("invalid_traffic_multiplier")
    if effects.min_subscription_months is not None and effects.min_subscription_months <= 0:
        errors.append("invalid_min_subscription_months")
    if effects.min_traffic_gb is not None and effects.min_traffic_gb <= 0:
        errors.append("invalid_min_traffic_gb")
    if effects.min_subscription_months is not None and effects.applies_to not in {
        PROMO_APPLIES_TO_ALL,
        PROMO_APPLIES_TO_SUBSCRIPTION,
    }:
        errors.append("subscription_threshold_scope_mismatch")
    if effects.min_traffic_gb is not None and effects.applies_to not in {
        PROMO_APPLIES_TO_ALL,
        PROMO_APPLIES_TO_TRAFFIC,
        PROMO_APPLIES_TO_TRAFFIC_TOPUP,
    }:
        errors.append("traffic_threshold_scope_mismatch")
    if effects.bonus_days > 0 and effects.applies_to not in {
        PROMO_APPLIES_TO_ALL,
        PROMO_APPLIES_TO_SUBSCRIPTION,
    }:
        errors.append("bonus_days_scope_mismatch")
    if effects.duration_multiplier > 1.0 and effects.applies_to not in {
        PROMO_APPLIES_TO_ALL,
        PROMO_APPLIES_TO_SUBSCRIPTION,
    }:
        errors.append("duration_multiplier_scope_mismatch")
    if effects.traffic_multiplier > 1.0 and effects.applies_to not in {
        PROMO_APPLIES_TO_ALL,
        PROMO_APPLIES_TO_TRAFFIC,
        PROMO_APPLIES_TO_TRAFFIC_TOPUP,
    }:
        errors.append("traffic_multiplier_scope_mismatch")
    if effects.applies_to == PROMO_APPLIES_TO_HWID and not effects.has_discount:
        errors.append("hwid_scope_requires_discount")
    if errors:
        raise PromoEffectsValidationError(",".join(errors))


def summarize_effects(effects: PromoEffects) -> str:
    parts: list[str] = []
    if effects.discount_percent:
        parts.append(f"-{effects.discount_percent:g}%")
    if effects.duration_multiplier > 1.0:
        parts.append(f"x{effects.duration_multiplier:g} duration")
    if effects.traffic_multiplier > 1.0:
        parts.append(f"x{effects.traffic_multiplier:g} traffic")
    if effects.bonus_days > 0:
        parts.append(f"+{effects.bonus_days} days")
    if effects.min_subscription_months:
        parts.append(f"from {effects.min_subscription_months} months")
    if effects.min_traffic_gb:
        parts.append(f"from {effects.min_traffic_gb:g} GB")
    return ", ".join(parts) or "bonus"
