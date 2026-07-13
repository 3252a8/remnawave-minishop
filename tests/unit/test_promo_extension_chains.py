import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.infra.grants import (
    GrantAdjustment,
    GrantContext,
    register_grant_modifier,
    reset_grant_modifiers,
    resolve_effective_grant,
)
from bot.infra.pricing import (
    PriceAdjustment,
    PriceContext,
    register_price_modifier,
    reset_price_modifiers,
    resolve_effective_price,
)
from bot.infra.promo_policies import (
    PromoRedemptionContext,
    PromoRedemptionDecision,
    evaluate_promo_redemption,
    register_promo_redemption_policy,
    reset_promo_redemption_policies,
)
from bot.services.promo_effects import PromoEffects
from db.dal import promo_code_dal


@pytest.fixture(autouse=True)
def _reset_chains():
    reset_price_modifiers()
    reset_grant_modifiers()
    reset_promo_redemption_policies()
    yield
    reset_price_modifiers()
    reset_grant_modifiers()
    reset_promo_redemption_policies()


def test_price_chain_applies_core_discount_and_registered_modifier():
    seen: list[str] = []

    def plugin_modifier(ctx: PriceContext):
        seen.append(ctx.sale_mode_base)
        return (PriceAdjustment(discount_percent=90, source="plugin"),)

    register_price_modifier(plugin_modifier)
    result = resolve_effective_price(
        PriceContext(
            sale_mode="subscription@standard",
            sale_mode_base="subscription",
            tariff_key="standard",
            units=12,
            currency="RUB",
            is_stars=False,
            user_id=1,
            base_amount=100,
            base_stars=100,
            promo=PromoEffects(discount_percent=20, applies_to="subscription"),
            promo_code_id=10,
            months=12,
        )
    )

    assert seen == ["subscription"]
    assert result.total_discount_percent == 100
    assert result.amount == 0
    assert result.stars == 1
    assert [adjustment.source for adjustment in result.adjustments] == ["promo", "plugin"]


def test_grant_chain_applies_core_bonus_and_registered_modifier():
    seen: list[str] = []
    period_start = datetime(2026, 1, 1, tzinfo=UTC)
    base_period_end = datetime(2026, 2, 1, tzinfo=UTC)

    def plugin_modifier(ctx: GrantContext):
        seen.append(ctx.sale_mode_base)
        return (GrantAdjustment(extra_days=3, source="plugin"),)

    register_grant_modifier(plugin_modifier)
    result = resolve_effective_grant(
        GrantContext(
            sale_mode_base="subscription",
            tariff_key="standard",
            base_period_days=31,
            months=1,
            charged_gb=None,
            scope="regular",
            promo=PromoEffects(bonus_days=2, duration_multiplier=2, applies_to="subscription"),
            period_start=period_start,
            base_period_end=base_period_end,
        )
    )

    assert seen == ["subscription"]
    assert result.extra_days == 33
    assert [adjustment.source for adjustment in result.adjustments] == ["promo", "plugin"]


def test_redemption_policy_chain_invokes_registered_policy(monkeypatch):
    monkeypatch.setattr(
        promo_code_dal,
        "get_user_activation_for_promo",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        promo_code_dal,
        "user_has_pending_payment_with_promo",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        promo_code_dal,
        "count_pending_payments_with_promo",
        AsyncMock(return_value=0),
    )
    seen: list[int] = []

    def plugin_policy(ctx: PromoRedemptionContext) -> PromoRedemptionDecision:
        seen.append(ctx.user_id)
        return PromoRedemptionDecision.deny("plugin_denied")

    register_promo_redemption_policy(plugin_policy)
    decision = asyncio.run(
        evaluate_promo_redemption(
            PromoRedemptionContext(
                session=object(),
                user_id=42,
                promo_model=SimpleNamespace(
                    promo_code_id=5,
                    is_active=True,
                    valid_until=datetime.now(UTC) + timedelta(days=1),
                    current_activations=0,
                    max_activations=10,
                ),
                effects=PromoEffects(bonus_days=1),
                sale_mode_base="subscription",
                months=1,
            )
        )
    )

    assert seen == [42]
    assert decision.allowed is False
    assert decision.reason_key == "plugin_denied"


def test_redemption_policy_counts_pending_invoices_against_global_limit(monkeypatch):
    monkeypatch.setattr(
        promo_code_dal,
        "get_user_activation_for_promo",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        promo_code_dal,
        "user_has_pending_payment_with_promo",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        promo_code_dal,
        "count_pending_payments_with_promo",
        AsyncMock(return_value=1),
    )

    decision = asyncio.run(
        evaluate_promo_redemption(
            PromoRedemptionContext(
                session=object(),
                user_id=42,
                promo_model=SimpleNamespace(
                    promo_code_id=5,
                    is_active=True,
                    valid_until=datetime.now(UTC) + timedelta(days=1),
                    current_activations=1,
                    max_activations=2,
                ),
                effects=PromoEffects(discount_percent=50),
                sale_mode_base="subscription",
                months=1,
            )
        )
    )

    assert decision.allowed is False
    assert decision.reason_key == "promo_code_exhausted"
