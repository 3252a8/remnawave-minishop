from datetime import UTC, datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.services.checkout_promos import (
    CheckoutPromoResult,
    checkout_promo_payment_fields,
    resolve_best_checkout_promo,
)
from bot.services.promo_effects import PromoEffects


def _quote(
    promo_code_id: int,
    discount_percent: float,
    discount_amount: float,
) -> CheckoutPromoResult:
    return CheckoutPromoResult(
        promo_code_id=promo_code_id,
        code=f"SAVE{promo_code_id}",
        effects=PromoEffects(discount_percent=discount_percent),
        base_amount=1_000,
        effective_amount=1_000 - discount_amount,
        effective_stars=None,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        effect_summary=f"discount:{discount_percent:g}",
        charged_months=3,
        charged_gb=None,
        quoted_at=datetime.now(UTC),
    )


class CheckoutPromoTests(IsolatedAsyncioTestCase):
    async def test_best_candidate_uses_largest_discount_for_selected_period(self):
        quotes = {
            "NEWEST10": _quote(10, 10, 100),
            "OLDER30": _quote(30, 30, 300),
        }

        async def resolve(**kwargs):
            return quotes[kwargs["code_input"]], None

        with patch(
            "bot.services.checkout_promos.resolve_checkout_promo",
            AsyncMock(side_effect=resolve),
        ):
            result = await resolve_best_checkout_promo(
                ["NEWEST10", "OLDER30"],
                session=AsyncMock(),
                settings=AsyncMock(),
                user_id=42,
                sale_mode="subscription@standard",
                payment_units=3,
                base_amount=1_000,
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.promo_code_id, 30)

    async def test_zero_price_candidate_is_not_selected(self):
        free = _quote(100, 100, 1_000)

        with patch(
            "bot.services.checkout_promos.resolve_checkout_promo",
            AsyncMock(return_value=(free, None)),
        ):
            result = await resolve_best_checkout_promo(
                ["FREE100"],
                session=AsyncMock(),
                settings=AsyncMock(),
                user_id=42,
                sale_mode="subscription@standard",
                payment_units=1,
                base_amount=1_000,
            )

        self.assertIsNone(result)

    def test_payment_snapshot_contains_promo_attribution(self):
        quote = _quote(30, 30, 300)

        fields = checkout_promo_payment_fields(quote)

        self.assertEqual(fields["promo_code_id"], 30)
        self.assertEqual(fields["checkout_base_amount"], 1_000)
        self.assertEqual(fields["checkout_discount_amount"], 300)
        self.assertEqual(fields["checkout_charged_months"], 3)
