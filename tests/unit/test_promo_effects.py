from types import SimpleNamespace

import pytest

from bot.services.promo_effects import (
    PromoEffects,
    PromoEffectsValidationError,
    validate_effects,
)


def test_promo_effects_normalize_model_defaults():
    effects = PromoEffects.from_model(
        SimpleNamespace(
            bonus_days=7,
            discount_percent=None,
            duration_multiplier=None,
            traffic_multiplier=None,
            applies_to="unknown",
        )
    )

    assert effects.bonus_days == 7
    assert effects.discount_percent is None
    assert effects.duration_multiplier == 1.0
    assert effects.traffic_multiplier == 1.0
    assert effects.applies_to == "all"
    assert effects.is_bonus_days_only is True


@pytest.mark.parametrize(
    "effects",
    [
        PromoEffects(),
        PromoEffects(discount_percent=0),
        PromoEffects(discount_percent=101),
        PromoEffects(duration_multiplier=0.5),
        PromoEffects(traffic_multiplier=13),
        PromoEffects(bonus_days=1, applies_to="bad"),
        PromoEffects(bonus_days=1, applies_to="traffic"),
        PromoEffects(duration_multiplier=2, applies_to="traffic"),
        PromoEffects(traffic_multiplier=2, applies_to="subscription"),
        PromoEffects(bonus_days=1, applies_to="hwid"),
        PromoEffects(applies_to="hwid"),
        PromoEffects(bonus_days=1, applies_to="traffic", min_subscription_months=12),
        PromoEffects(bonus_days=1, applies_to="subscription", min_traffic_gb=50),
    ],
)
def test_validate_effects_rejects_invalid_combinations(effects):
    with pytest.raises(PromoEffectsValidationError):
        validate_effects(effects, max_traffic_multiplier=12)


def test_thresholds_are_inclusive_and_dimension_scoped():
    subscription_effects = PromoEffects(
        duration_multiplier=2,
        applies_to="subscription",
        min_subscription_months=12,
    )
    traffic_effects = PromoEffects(
        traffic_multiplier=2,
        applies_to="traffic",
        min_traffic_gb=100,
    )

    assert subscription_effects.meets_threshold(
        sale_mode_base="subscription",
        months=12,
        traffic_gb=None,
    )
    assert not subscription_effects.meets_threshold(
        sale_mode_base="subscription",
        months=11,
        traffic_gb=None,
    )
    assert subscription_effects.meets_threshold(
        sale_mode_base="traffic",
        months=None,
        traffic_gb=1,
    )
    assert traffic_effects.meets_threshold(
        sale_mode_base="traffic",
        months=None,
        traffic_gb=100,
    )
    assert not traffic_effects.meets_threshold(
        sale_mode_base="traffic",
        months=None,
        traffic_gb=99.9,
    )


def test_promo_effects_from_payment_snapshot_normalizes_scope_and_discount():
    effects = PromoEffects.from_payment_snapshot(
        SimpleNamespace(
            promo_effect_summary="old terms",
            promo_bonus_days=5,
            promo_discount_percent=0,
            promo_duration_multiplier=None,
            promo_traffic_multiplier=None,
            promo_applies_to="unknown",
            promo_min_subscription_months=None,
            promo_min_traffic_gb=None,
        )
    )

    assert effects is not None
    assert effects.bonus_days == 5
    assert effects.discount_percent is None
    assert effects.applies_to == "all"
