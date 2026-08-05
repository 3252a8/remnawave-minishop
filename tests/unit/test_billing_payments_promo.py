from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp.billing_checkout_adjustments import _resolve_checkout_promo


class BillingPaymentsPromoTests(IsolatedAsyncioTestCase):
    async def test_checkout_rejects_instant_bonus_code(self):
        settings = SimpleNamespace(
            MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False,
            PROMO_DURATION_MULTIPLIER_MAX=12,
            PROMO_TRAFFIC_MULTIPLIER_MAX=12,
        )
        promo = SimpleNamespace(
            promo_code_id=5,
            code="HELLO",
            bonus_days=7,
            bonus_requires_payment=False,
            discount_percent=None,
            duration_multiplier=None,
            traffic_multiplier=None,
            applies_to="subscription",
        )

        lookup = AsyncMock(return_value=promo)
        with patch(
            "bot.app.web.webapp.billing_checkout_adjustments."
            "promo_code_dal.get_active_promo_code_by_code_str",
            lookup,
        ):
            result, error = await _resolve_checkout_promo(
                session=AsyncMock(),
                settings=settings,
                user_id=42,
                code_input="hello",
                sale_mode="subscription@standard",
                payment_units=1,
                traffic_gb=None,
                method="yookassa",
                base_amount=100,
                base_stars=None,
                lock_for_checkout=True,
            )

        self.assertIsNone(result)
        self.assertIsNotNone(error)
        assert error is not None
        self.assertEqual(error.code, "promo_code_direct_activation_required")
        self.assertTrue(lookup.await_args.kwargs["for_update"])
