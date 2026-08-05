from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.pricing import PriceContext, resolve_effective_price
from bot.infra.promo_policies import PromoRedemptionContext, evaluate_promo_redemption
from bot.services.promo_effects import PromoEffects, summarize_effects, validate_effects
from config.settings import Settings
from config.tariffs_config import default_payment_currency_code_for_settings
from db.dal import promo_code_dal


@dataclass(frozen=True)
class CheckoutPromoResult:
    promo_code_id: int
    code: str
    effects: PromoEffects
    base_amount: float
    effective_amount: float
    effective_stars: int | None
    discount_percent: float
    discount_amount: float
    effect_summary: str
    charged_months: int | None
    charged_gb: float | None
    quoted_at: datetime


@dataclass(frozen=True)
class CheckoutPromoError:
    status: int
    code: str
    message: str


def _sale_mode_base(sale_mode: str) -> str:
    return str(sale_mode or "").split("@", 1)[0].split("|", 1)[0]


def _sale_mode_tariff_key(sale_mode: str) -> str | None:
    if "@" not in str(sale_mode or ""):
        return None
    return str(sale_mode).split("@", 1)[1].split("|", 1)[0] or None


def _sale_mode_is_traffic(sale_mode: str) -> bool:
    return _sale_mode_base(sale_mode) in {
        "traffic",
        "traffic_package",
        "topup",
        "premium_topup",
    }


async def _promo_model(
    session: AsyncSession,
    settings: Settings,
    *,
    code_input: Any = None,
    promo_code_id: int | None = None,
    lock_for_checkout: bool = False,
) -> Any | None:
    if promo_code_id is not None:
        promo = await promo_code_dal.get_promo_code_by_id(
            session,
            int(promo_code_id),
            for_update=lock_for_checkout,
        )
        if promo is None or getattr(promo, "archived_at", None) is not None:
            return None
        return promo

    code = str(code_input or "").strip()
    if not code:
        return None
    preserve_case = bool(settings.MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED)
    lookup_code = code if preserve_case else code.upper()
    return await promo_code_dal.get_active_promo_code_by_code_str(
        session,
        lookup_code,
        preserve_case=preserve_case,
        for_update=lock_for_checkout,
    )


async def resolve_checkout_promo(
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    sale_mode: str,
    payment_units: int | float,
    traffic_gb: float | None,
    method: str,
    base_amount: float,
    base_stars: int | None,
    code_input: Any = None,
    promo_code_id: int | None = None,
    lock_for_checkout: bool = False,
) -> tuple[CheckoutPromoResult | None, CheckoutPromoError | None]:
    code = str(code_input or "").strip()
    if not code and promo_code_id is None:
        return None, None
    promo = await _promo_model(
        session,
        settings,
        code_input=code,
        promo_code_id=promo_code_id,
        lock_for_checkout=lock_for_checkout,
    )
    if promo is None:
        return None, CheckoutPromoError(400, "promo_code_not_found", "Code is not available")

    effects = PromoEffects.from_model(promo)
    try:
        validate_effects(
            effects,
            max_duration_multiplier=float(settings.PROMO_DURATION_MULTIPLIER_MAX),
            max_traffic_multiplier=float(settings.PROMO_TRAFFIC_MULTIPLIER_MAX),
        )
    except ValueError:
        return None, CheckoutPromoError(400, "promo_code_invalid", "Code is not available")

    if effects.can_apply_standalone:
        return None, CheckoutPromoError(
            400,
            "promo_code_direct_activation_required",
            "Activate this code outside checkout",
        )

    sale_base = _sale_mode_base(sale_mode)
    months = int(payment_units) if sale_base == "subscription" else None
    traffic_units = traffic_gb if _sale_mode_is_traffic(sale_mode) else None
    if not effects.applies_to_sale_mode(sale_base):
        return None, CheckoutPromoError(
            400,
            "promo_code_not_applicable",
            "Code does not apply to this purchase",
        )
    if effects.is_bonus_days_only and sale_base != "subscription":
        return None, CheckoutPromoError(
            400,
            "promo_code_not_applicable",
            "Code does not apply to this purchase",
        )

    decision = await evaluate_promo_redemption(
        PromoRedemptionContext(
            session=session,
            user_id=user_id,
            promo_model=promo,
            effects=effects,
            sale_mode_base=sale_base,
            months=months,
            traffic_gb=traffic_units,
        )
    )
    if not decision.allowed:
        reason_key = decision.reason_key or "promo_code_not_applicable"
        message = reason_key
        if reason_key == "promo_code_min_period_required":
            message = f"Code applies from {effects.min_subscription_months} months"
        elif reason_key == "promo_code_min_traffic_required":
            required_gb = float(effects.min_traffic_gb or 0)
            message = f"Code applies from {required_gb:g} GB"
        elif reason_key == "promo_code_pending_payment_exists":
            message = "A pending payment already uses this code"
        elif reason_key == "promo_code_already_used_by_user":
            message = "This code has already been used"
        return None, CheckoutPromoError(400, reason_key, message)

    effective = resolve_effective_price(
        PriceContext(
            sale_mode=sale_mode,
            sale_mode_base=sale_base,
            tariff_key=_sale_mode_tariff_key(sale_mode),
            units=payment_units,
            currency=(
                "XTR" if method == "stars" else default_payment_currency_code_for_settings(settings)
            ),
            is_stars=method == "stars",
            user_id=user_id,
            base_amount=base_amount,
            base_stars=base_stars,
            promo=effects,
            promo_code_id=int(promo.promo_code_id),
            months=months,
            traffic_gb=traffic_units,
        )
    )
    return (
        CheckoutPromoResult(
            promo_code_id=int(promo.promo_code_id),
            code=str(promo.code or code),
            effects=effects,
            base_amount=base_amount,
            effective_amount=effective.amount,
            effective_stars=effective.stars,
            discount_percent=effective.total_discount_percent,
            discount_amount=effective.discount_amount,
            effect_summary=summarize_effects(effects),
            charged_months=months,
            charged_gb=traffic_units,
            quoted_at=datetime.now(UTC),
        ),
        None,
    )


async def resolve_best_checkout_promo(
    candidate_codes: Sequence[str],
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    sale_mode: str,
    payment_units: int | float,
    base_amount: float,
    base_stars: int | None = None,
    method: str = "telegram",
) -> CheckoutPromoResult | None:
    """Return the payable candidate with the largest monetary reduction."""

    best: CheckoutPromoResult | None = None
    for code in candidate_codes:
        result, error = await resolve_checkout_promo(
            session=session,
            settings=settings,
            user_id=user_id,
            code_input=code,
            sale_mode=sale_mode,
            payment_units=payment_units,
            traffic_gb=None,
            method=method,
            base_amount=base_amount,
            base_stars=base_stars,
        )
        if error is not None or result is None or result.discount_amount <= 0:
            continue
        if method == "stars":
            if result.effective_stars is None or result.effective_stars <= 0:
                continue
        elif result.effective_amount <= 0:
            continue
        if best is None or (
            result.discount_amount,
            result.discount_percent,
        ) > (
            best.discount_amount,
            best.discount_percent,
        ):
            best = result
    return best


def checkout_promo_payment_fields(promo: CheckoutPromoResult | None) -> Mapping[str, Any]:
    if promo is None:
        return {}
    return {
        "promo_code_id": promo.promo_code_id,
        "promo_effect_summary": promo.effect_summary,
        "promo_bonus_days": promo.effects.bonus_days,
        "promo_discount_percent": promo.effects.discount_percent,
        "promo_duration_multiplier": (
            promo.effects.duration_multiplier if promo.effects.duration_multiplier != 1.0 else None
        ),
        "promo_traffic_multiplier": (
            promo.effects.traffic_multiplier if promo.effects.traffic_multiplier != 1.0 else None
        ),
        "promo_applies_to": promo.effects.applies_to,
        "promo_min_subscription_months": promo.effects.min_subscription_months,
        "promo_min_traffic_gb": promo.effects.min_traffic_gb,
        "checkout_base_amount": promo.base_amount,
        "checkout_discount_amount": promo.discount_amount,
        "checkout_charged_months": promo.charged_months,
        "checkout_charged_gb": promo.charged_gb,
        "checkout_quoted_at": promo.quoted_at,
    }
