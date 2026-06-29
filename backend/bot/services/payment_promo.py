from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.promo_effects import PromoEffects, summarize_effects
from db.dal import promo_code_dal

logger = logging.getLogger(__name__)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


async def load_payment_promo_effects(
    session: AsyncSession,
    payment_or_promo_code_id: Any | None,
) -> tuple[Any | None, PromoEffects | None]:
    payment = None
    promo_code_id = payment_or_promo_code_id
    if payment_or_promo_code_id is not None and not isinstance(payment_or_promo_code_id, int):
        payment = payment_or_promo_code_id
        promo_code_id = getattr(payment, "promo_code_id", None)
    if not promo_code_id:
        return None, None
    promo_model = await promo_code_dal.get_promo_code_by_id(session, promo_code_id)
    if promo_model is None:
        logger.warning("Attached code ID %s was not found.", promo_code_id)
        return None, None
    snapshot_effects = PromoEffects.from_payment_snapshot(payment) if payment is not None else None
    return promo_model, snapshot_effects or PromoEffects.from_model(promo_model)


async def consume_payment_promo(
    *,
    session: AsyncSession,
    user_id: int,
    promo_model: Any,
    effects: PromoEffects,
    payment_id: int,
    sale_mode_base: str,
    months: int | None,
    traffic_gb: float | None,
    payment: Any | None = None,
    granted_days: int | None = None,
    granted_gb: float | None = None,
) -> bool:
    promo_code_id = int(getattr(promo_model, "promo_code_id"))
    existing = await promo_code_dal.get_user_activation_for_promo(
        session,
        promo_code_id,
        user_id,
    )
    if existing is not None:
        return int(getattr(existing, "payment_id", 0) or 0) == int(payment_id)

    if (
        (effects.is_bonus_days_only and sale_mode_base != "subscription")
        or not effects.applies_to_sale_mode(sale_mode_base)
        or not effects.meets_threshold(
            sale_mode_base=sale_mode_base,
            months=months,
            traffic_gb=traffic_gb,
        )
    ):
        logger.warning(
            "Attached code %s was denied at success for user %s: invoice scope mismatch",
            promo_code_id,
            user_id,
        )
        return False

    activation = await promo_code_dal.consume_promo_activation(
        session,
        promo_code_id,
        user_id,
        payment_id=payment_id,
        enforce_limit=False,
        effect_summary=summarize_effects(effects),
        bonus_days=effects.bonus_days,
        discount_percent=effects.discount_percent,
        duration_multiplier=effects.duration_multiplier
        if effects.duration_multiplier != 1.0
        else None,
        traffic_multiplier=effects.traffic_multiplier
        if effects.traffic_multiplier != 1.0
        else None,
        applies_to=effects.applies_to,
        base_amount=_optional_float(getattr(payment, "checkout_base_amount", None)),
        discount_amount=_optional_float(getattr(payment, "checkout_discount_amount", None)),
        charged_months=months,
        charged_gb=traffic_gb,
        granted_days=granted_days,
        granted_gb=granted_gb,
    )
    return activation is not None
