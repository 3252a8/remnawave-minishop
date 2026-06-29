from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable

from bot.services.promo_effects import PromoEffects
from bot.utils.date_utils import add_months


@dataclass(frozen=True)
class GrantContext:
    sale_mode_base: str
    tariff_key: str | None
    base_period_days: int
    months: int | None
    charged_gb: float | None
    scope: str
    promo: PromoEffects | None = None
    period_start: datetime | None = None
    base_period_end: datetime | None = None

    @property
    def traffic_gb(self) -> float | None:
        return self.charged_gb


@dataclass(frozen=True)
class GrantAdjustment:
    extra_days: int = 0
    traffic_multiplier: float = 1.0
    source: str = "core"


@dataclass(frozen=True)
class EffectiveGrant:
    extra_days: int
    traffic_multiplier: float
    adjustments: tuple[GrantAdjustment, ...] = field(default_factory=tuple)


GrantModifier = Callable[[GrantContext], Iterable[GrantAdjustment]]

_extra_grant_modifiers: list[GrantModifier] = []


def _duration_multiplier_extra_days(ctx: GrantContext, multiplier: float) -> int:
    if multiplier <= 1.0 or ctx.base_period_days <= 0:
        return 0
    if (
        ctx.period_start is not None
        and ctx.base_period_end is not None
        and ctx.months is not None
        and float(multiplier).is_integer()
    ):
        multiplied_end = add_months(ctx.period_start, ctx.months * int(multiplier))
        return max(0, (multiplied_end - ctx.base_period_end).days)
    return max(0, round(ctx.base_period_days * (multiplier - 1.0)))


def _promo_grant_modifier(ctx: GrantContext) -> Iterable[GrantAdjustment]:
    promo = ctx.promo
    if promo is None:
        return ()
    if not promo.applies_to_sale_mode(ctx.sale_mode_base):
        return ()
    if not promo.meets_threshold(
        sale_mode_base=ctx.sale_mode_base,
        months=ctx.months,
        traffic_gb=ctx.traffic_gb,
    ):
        return ()
    if ctx.sale_mode_base == "subscription":
        extra_days = promo.bonus_days + _duration_multiplier_extra_days(
            ctx,
            promo.duration_multiplier,
        )
        return (GrantAdjustment(extra_days=extra_days, source="promo"),) if extra_days > 0 else ()
    if ctx.sale_mode_base in {"traffic", "traffic_package", "topup", "premium_topup"}:
        return (
            (GrantAdjustment(traffic_multiplier=promo.traffic_multiplier, source="promo"),)
            if promo.traffic_multiplier > 1.0
            else ()
        )
    return ()


_CORE_GRANT_MODIFIERS: tuple[GrantModifier, ...] = (_promo_grant_modifier,)


def register_grant_modifier(modifier: GrantModifier) -> None:
    if not callable(modifier):
        raise TypeError("modifier must be callable")
    if modifier not in _extra_grant_modifiers:
        _extra_grant_modifiers.append(modifier)


def reset_grant_modifiers() -> None:
    _extra_grant_modifiers.clear()


def iter_grant_modifiers() -> tuple[GrantModifier, ...]:
    return (*_CORE_GRANT_MODIFIERS, *_extra_grant_modifiers)


def resolve_effective_grant(ctx: GrantContext) -> EffectiveGrant:
    adjustments: list[GrantAdjustment] = []
    for modifier in iter_grant_modifiers():
        adjustments.extend(modifier(ctx) or ())
    traffic_multiplier = 1.0
    for adjustment in adjustments:
        traffic_multiplier *= max(1.0, float(adjustment.traffic_multiplier))
    return EffectiveGrant(
        extra_days=sum(max(0, int(adjustment.extra_days)) for adjustment in adjustments),
        traffic_multiplier=traffic_multiplier,
        adjustments=tuple(adjustments),
    )
