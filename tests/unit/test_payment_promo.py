from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.services.payment_promo import consume_payment_promo, load_payment_promo_effects
from bot.services.promo_effects import PromoEffects


class PaymentPromoTests(IsolatedAsyncioTestCase):
    async def test_load_payment_promo_effects_prefers_frozen_payment_snapshot(self):
        promo = SimpleNamespace(
            promo_code_id=5,
            bonus_days=1,
            discount_percent=None,
            duration_multiplier=None,
            traffic_multiplier=None,
            applies_to="subscription",
        )
        payment = SimpleNamespace(
            promo_code_id=5,
            promo_effect_summary="-50%",
            promo_bonus_days=0,
            promo_discount_percent=50,
            promo_duration_multiplier=None,
            promo_traffic_multiplier=None,
            promo_applies_to="traffic",
            promo_min_subscription_months=None,
            promo_min_traffic_gb=10,
        )

        with patch(
            "bot.services.payment_promo.promo_code_dal.get_promo_code_by_id",
            AsyncMock(return_value=promo),
        ):
            promo_model, effects = await load_payment_promo_effects(AsyncMock(), payment)

        self.assertIs(promo_model, promo)
        self.assertIsNotNone(effects)
        assert effects is not None
        self.assertEqual(effects.discount_percent, 50)
        self.assertEqual(effects.applies_to, "traffic")
        self.assertEqual(effects.min_traffic_gb, 10)

    async def test_consume_payment_promo_honors_invoice_snapshot_terms(self):
        session = AsyncMock()
        promo = SimpleNamespace(promo_code_id=5)
        payment = SimpleNamespace(checkout_base_amount=100, checkout_discount_amount=25)
        activation = SimpleNamespace(activation_id=9)
        effects = PromoEffects(discount_percent=25, applies_to="subscription")

        with (
            patch(
                "bot.services.payment_promo.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.payment_promo.promo_code_dal.consume_promo_activation",
                AsyncMock(return_value=activation),
            ) as consume_activation,
        ):
            consumed = await consume_payment_promo(
                session=session,
                user_id=42,
                promo_model=promo,
                effects=effects,
                payment_id=77,
                payment=payment,
                sale_mode_base="subscription",
                months=3,
                traffic_gb=None,
                granted_days=14,
            )

        self.assertTrue(consumed)
        consume_activation.assert_awaited_once()
        kwargs = consume_activation.await_args.kwargs
        self.assertFalse(kwargs["enforce_limit"])
        self.assertEqual(kwargs["base_amount"], 100)
        self.assertEqual(kwargs["discount_amount"], 25)
        self.assertEqual(kwargs["charged_months"], 3)
        self.assertEqual(kwargs["granted_days"], 14)

    async def test_consume_payment_promo_rejects_bonus_only_for_traffic(self):
        session = AsyncMock()
        promo = SimpleNamespace(promo_code_id=5)
        effects = PromoEffects(bonus_days=7, applies_to="all")

        with (
            patch(
                "bot.services.payment_promo.promo_code_dal.get_user_activation_for_promo",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.payment_promo.promo_code_dal.consume_promo_activation",
                AsyncMock(),
            ) as consume_activation,
        ):
            consumed = await consume_payment_promo(
                session=session,
                user_id=42,
                promo_model=promo,
                effects=effects,
                payment_id=77,
                sale_mode_base="traffic",
                months=None,
                traffic_gb=10,
            )

        self.assertFalse(consumed)
        consume_activation.assert_not_awaited()
