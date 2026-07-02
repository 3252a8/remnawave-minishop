from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.webapp.common import _json_error
from bot.infra.pricing import PriceContext, resolve_effective_price
from bot.infra.promo_policies import PromoRedemptionContext, evaluate_promo_redemption
from bot.services.promo_effects import PromoEffects, summarize_effects, validate_effects
from config.settings import Settings
from config.tariffs_config import default_payment_currency_code_for_settings
from db.dal import promo_code_dal

from .billing_sale_modes import _sale_mode_base, _sale_mode_is_traffic, _sale_mode_tariff_key


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

    def to_response(self) -> web.Response:
        return _json_error(self.status, self.code, self.message)


async def _resolve_checkout_promo(
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    code_input: Any,
    sale_mode: str,
    payment_units: int | float,
    traffic_gb: float | None,
    method: str,
    base_amount: float,
    base_stars: int | None,
) -> tuple[CheckoutPromoResult | None, CheckoutPromoError | None]:
    code = str(code_input or "").strip()
    if not code:
        return None, None
    preserve_case = bool(settings.MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED)
    lookup_code = code if preserve_case else code.upper()
    promo = await promo_code_dal.get_active_promo_code_by_code_str(
        session,
        lookup_code,
        preserve_case=preserve_case,
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
        return None, CheckoutPromoError(
            400,
            reason_key,
            message,
        )

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
            code=str(promo.code or lookup_code),
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
