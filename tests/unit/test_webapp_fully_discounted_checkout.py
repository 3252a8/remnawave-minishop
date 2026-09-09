import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import billing_payments, billing_promo_checkout
from bot.payment_providers.base import PaymentProviderSpec, WebAppPaymentContext
from bot.services.checkout_promos import CheckoutPromoResult
from bot.services.promo_effects import PromoEffects


class FullyDiscountedCheckoutTests(IsolatedAsyncioTestCase):
    async def test_zero_total_promo_skips_provider_and_partner_balance(self):
        session = AsyncMock()
        completed_response = billing_payments.web.json_response(
            {
                "ok": True,
                "action": "completed",
                "payment_id": 17,
                "status": "succeeded",
                "paid": True,
            }
        )
        provider_spec = PaymentProviderSpec(
            id="provider",
            provider_key="provider",
            label="Provider",
            pending_status="pending_provider",
            enabled=lambda _config: True,
            create_webapp_payment=AsyncMock(),
        )
        promo_result = CheckoutPromoResult(
            promo_code_id=91,
            code="FREE100",
            effects=PromoEffects(discount_percent=100),
            base_amount=700.0,
            effective_amount=0.0,
            effective_stars=None,
            discount_percent=100.0,
            discount_amount=700.0,
            effect_summary="discount:100",
            charged_months=3,
            charged_gb=None,
            quoted_at=datetime.now(UTC),
        )
        settings = SimpleNamespace(
            DEFAULT_CURRENCY_SYMBOL="RUB",
            MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED=False,
        )
        request = SimpleNamespace(app={})

        with (
            patch.object(billing_payments, "get_settings", return_value=settings),
            patch.object(billing_payments, "get_i18n", return_value=None),
            patch.object(
                billing_payments.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=None),
            ),
            patch("bot.payment_providers.get_provider_spec", return_value=provider_spec),
            patch.object(
                billing_payments,
                "create_fully_discounted_payment",
                AsyncMock(return_value=completed_response),
            ) as create_discounted,
            patch.object(
                billing_payments,
                "allocate_checkout_balance",
                AsyncMock(),
            ) as allocate_balance,
        ):
            response = await billing_payments._create_subscription_payment(
                request=request,
                session=session,
                user_id=1001,
                method="provider",
                months=3,
                price=700.0,
                stars_price=None,
                lang="en",
                currency="RUB",
                sale_mode="subscription@standard",
                promo_result=promo_result,
                entitlement_context_snapshot="entitlement-snapshot",
                use_partner_balance=True,
            )

        self.assertIs(response, completed_response)
        create_discounted.assert_awaited_once()
        context = create_discounted.await_args.kwargs["payment_context"]
        self.assertEqual(context.price, 0.0)
        self.assertEqual(context.promo_code_id, 91)
        self.assertEqual(context.checkout_base_amount, 700.0)
        self.assertEqual(context.checkout_discount_amount, 700.0)
        allocate_balance.assert_not_awaited()
        provider_spec.create_webapp_payment.assert_not_awaited()

    async def test_fully_discounted_checkout_uses_standard_finalizer(self):
        session = AsyncMock()
        payment = SimpleNamespace(payment_id=17)
        context = WebAppPaymentContext(
            request=SimpleNamespace(app={}),
            session=session,
            user_id=1001,
            method="provider",
            months=3,
            price=0.0,
            stars_price=None,
            description="Subscription",
            sale_mode="subscription@standard",
            currency="RUB",
            promo_code_id=91,
            checkout_base_amount=700.0,
            checkout_discount_amount=700.0,
        )

        with (
            patch.object(
                billing_promo_checkout,
                "create_webapp_payment_record",
                AsyncMock(return_value=payment),
            ) as create_record,
            patch.object(billing_promo_checkout, "get_referral_service", return_value=object()),
            patch.object(billing_promo_checkout, "get_bot", return_value=object()),
            patch.object(billing_promo_checkout, "get_settings", return_value=object()),
            patch.object(billing_promo_checkout, "get_i18n", return_value=object()),
            patch.object(billing_promo_checkout, "get_subscription_service", return_value=object()),
            patch.object(
                billing_promo_checkout,
                "finalize_successful_payment",
                AsyncMock(return_value=object()),
            ) as finalize,
        ):
            response = await billing_promo_checkout.create_fully_discounted_payment(
                request=SimpleNamespace(app={}),
                payment_context=context,
            )

        payload = json.loads(response.body)
        self.assertEqual(payload["action"], "completed")
        self.assertTrue(payload["paid"])
        create_record.assert_awaited_once_with(
            context,
            amount=0.0,
            currency="RUB",
            status="succeeded_pending_finalization",
            provider="promo",
            funding_source="checkout_promo",
        )
        request = finalize.await_args.args[0]
        self.assertEqual(request.amount, 0.0)
        self.assertEqual(request.provider_subscription, "promo")
        self.assertTrue(request.skip_referral_bonus)
