from __future__ import annotations

import inspect as inspect_module
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bot.services.promo_effects import PromoEffects
from db.dal import promo_code_dal


@dataclass(frozen=True)
class PromoRedemptionContext:
    session: Any
    user_id: int
    promo_model: Any
    effects: PromoEffects
    sale_mode_base: str
    months: int | None = None
    traffic_gb: float | None = None
    payment_id: int | None = None


@dataclass(frozen=True)
class PromoRedemptionDecision:
    allowed: bool
    reason_key: str | None = None
    reason_kwargs: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def allow(cls) -> PromoRedemptionDecision:
        return cls(allowed=True)

    @classmethod
    def deny(
        cls,
        reason_key: str,
        **reason_kwargs: object,
    ) -> PromoRedemptionDecision:
        return cls(allowed=False, reason_key=reason_key, reason_kwargs=reason_kwargs)


PromoRedemptionPolicy = Callable[
    [PromoRedemptionContext],
    PromoRedemptionDecision | Awaitable[PromoRedemptionDecision],
]

_extra_promo_redemption_policies: list[PromoRedemptionPolicy] = []


async def _core_state_policy(ctx: PromoRedemptionContext) -> PromoRedemptionDecision:
    promo = ctx.promo_model
    now = datetime.now(UTC)
    valid_until = getattr(promo, "valid_until", None)
    if valid_until is not None and valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=UTC)
    if not bool(getattr(promo, "is_active", False)):
        return PromoRedemptionDecision.deny("promo_code_not_found")
    if valid_until is not None and valid_until <= now:
        return PromoRedemptionDecision.deny("promo_code_expired")
    if int(getattr(promo, "current_activations", 0) or 0) >= int(
        getattr(promo, "max_activations", 0) or 0
    ):
        return PromoRedemptionDecision.deny("promo_code_exhausted")
    activation = await promo_code_dal.get_user_activation_for_promo(
        ctx.session,
        int(promo.promo_code_id),
        ctx.user_id,
    )
    if activation is not None:
        if ctx.payment_id is not None and int(getattr(activation, "payment_id", 0) or 0) == int(
            ctx.payment_id
        ):
            return PromoRedemptionDecision.allow()
        return PromoRedemptionDecision.deny("promo_code_already_used_by_user")
    has_pending = await promo_code_dal.user_has_pending_payment_with_promo(
        ctx.session,
        ctx.user_id,
        int(promo.promo_code_id),
        exclude_payment_id=ctx.payment_id,
    )
    if has_pending:
        return PromoRedemptionDecision.deny("promo_code_pending_payment_exists")
    pending_reservations = await promo_code_dal.count_pending_payments_with_promo(
        ctx.session,
        int(promo.promo_code_id),
        exclude_payment_id=ctx.payment_id,
    )
    if int(getattr(promo, "current_activations", 0) or 0) + pending_reservations >= int(
        getattr(promo, "max_activations", 0) or 0
    ):
        return PromoRedemptionDecision.deny("promo_code_exhausted")
    return PromoRedemptionDecision.allow()


def _core_threshold_policy(ctx: PromoRedemptionContext) -> PromoRedemptionDecision:
    if ctx.effects.meets_threshold(
        sale_mode_base=ctx.sale_mode_base,
        months=ctx.months,
        traffic_gb=ctx.traffic_gb,
    ):
        return PromoRedemptionDecision.allow()
    if ctx.effects.min_subscription_months is not None and ctx.sale_mode_base == "subscription":
        return PromoRedemptionDecision.deny(
            "promo_code_min_period_required",
            months=ctx.effects.min_subscription_months,
        )
    return PromoRedemptionDecision.deny(
        "promo_code_min_traffic_required",
        traffic_gb=ctx.effects.min_traffic_gb,
    )


_CORE_PROMO_REDEMPTION_POLICIES: tuple[PromoRedemptionPolicy, ...] = (
    _core_state_policy,
    _core_threshold_policy,
)


def register_promo_redemption_policy(policy: PromoRedemptionPolicy) -> None:
    if not callable(policy):
        raise TypeError("policy must be callable")
    if policy not in _extra_promo_redemption_policies:
        _extra_promo_redemption_policies.append(policy)


def reset_promo_redemption_policies() -> None:
    _extra_promo_redemption_policies.clear()


def iter_promo_redemption_policies() -> tuple[PromoRedemptionPolicy, ...]:
    return (*_CORE_PROMO_REDEMPTION_POLICIES, *_extra_promo_redemption_policies)


async def evaluate_promo_redemption(
    ctx: PromoRedemptionContext,
) -> PromoRedemptionDecision:
    for policy in iter_promo_redemption_policies():
        result = policy(ctx)
        if inspect_module.isawaitable(result):
            result = await result
        if not result.allowed:
            return result
    return PromoRedemptionDecision.allow()
