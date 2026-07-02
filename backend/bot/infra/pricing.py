from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from bot.services.promo_effects import PromoEffects


@dataclass(frozen=True)
class PriceContext:
    sale_mode: str
    sale_mode_base: str
    tariff_key: str | None
    units: int | float
    currency: str
    is_stars: bool
    user_id: int
    base_amount: float
    base_stars: int | None
    promo: PromoEffects | None = None
    promo_code_id: int | None = None
    months: int | None = None
    traffic_gb: float | None = None


@dataclass(frozen=True)
class PriceAdjustment:
    discount_percent: float
    source: str


@dataclass(frozen=True)
class EffectivePrice:
    amount: float
    stars: int | None
    total_discount_percent: float
    discount_amount: float
    adjustments: tuple[PriceAdjustment, ...] = field(default_factory=tuple)


PriceModifier = Callable[[PriceContext], Iterable[PriceAdjustment]]

_extra_price_modifiers: list[PriceModifier] = []


def _promo_discount_modifier(ctx: PriceContext) -> Iterable[PriceAdjustment]:
    promo = ctx.promo
    if promo is None or not promo.has_discount:
        return ()
    if not promo.applies_to_sale_mode(ctx.sale_mode_base):
        return ()
    if not promo.meets_threshold(
        sale_mode_base=ctx.sale_mode_base,
        months=ctx.months,
        traffic_gb=ctx.traffic_gb,
    ):
        return ()
    return (PriceAdjustment(discount_percent=float(promo.discount_percent or 0), source="promo"),)


_CORE_PRICE_MODIFIERS: tuple[PriceModifier, ...] = (_promo_discount_modifier,)


def register_price_modifier(modifier: PriceModifier) -> None:
    if not callable(modifier):
        raise TypeError("modifier must be callable")
    if modifier not in _extra_price_modifiers:
        _extra_price_modifiers.append(modifier)


def reset_price_modifiers() -> None:
    _extra_price_modifiers.clear()


def iter_price_modifiers() -> tuple[PriceModifier, ...]:
    return (*_CORE_PRICE_MODIFIERS, *_extra_price_modifiers)


def resolve_effective_price(ctx: PriceContext) -> EffectivePrice:
    adjustments: list[PriceAdjustment] = []
    for modifier in iter_price_modifiers():
        adjustments.extend(modifier(ctx) or ())
    total_discount = min(
        100.0,
        sum(max(0.0, float(adjustment.discount_percent)) for adjustment in adjustments),
    )
    multiplier = max(0.0, 1.0 - total_discount / 100.0)
    amount = round(float(ctx.base_amount) * multiplier, 2)
    stars = None
    if ctx.base_stars is not None:
        stars = max(1, round(int(ctx.base_stars) * multiplier))
    return EffectivePrice(
        amount=amount,
        stars=stars,
        total_discount_percent=total_discount,
        discount_amount=round(max(0.0, float(ctx.base_amount) - amount), 2),
        adjustments=tuple(adjustments),
    )
