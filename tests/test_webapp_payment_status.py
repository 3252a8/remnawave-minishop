from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import billing as billing_module
from bot.payment_providers.base import WebAppPaymentContext
from bot.payment_providers.yookassa import create_webapp_payment


class _SessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class WebAppPaymentStatusTests(IsolatedAsyncioTestCase):
    async def test_yookassa_pending_payment_refresh_processes_succeeded_provider_status(self):
        payment = SimpleNamespace(
            payment_id=42,
            user_id=1001,
            provider="yookassa",
            status="pending_yookassa",
            yookassa_payment_id="yk_42",
            provider_payment_id=None,
        )
        refreshed_payment = SimpleNamespace(
            payment_id=42,
            user_id=1001,
            provider="yookassa",
            status="succeeded",
            yookassa_payment_id="yk_42",
            provider_payment_id=None,
        )
        yookassa_service = SimpleNamespace(
            configured=True,
            get_payment_info=AsyncMock(
                return_value={
                    "id": "yk_42",
                    "status": "succeeded",
                    "paid": True,
                    "amount_value": 100.0,
                    "amount_currency": "RUB",
                    "metadata": {"user_id": "1001", "payment_db_id": "42"},
                }
            ),
        )
        request = SimpleNamespace(
            app={
                "bot": SimpleNamespace(),
                "i18n": SimpleNamespace(),
                "settings": SimpleNamespace(),
                "panel_service": SimpleNamespace(),
                "subscription_service": SimpleNamespace(),
                "referral_service": SimpleNamespace(),
                "lknpd_service": None,
                "yookassa_service": yookassa_service,
            }
        )
        session = AsyncMock()

        with (
            patch.object(
                billing_module.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(side_effect=[payment, refreshed_payment]),
            ),
            patch(
                "bot.payment_providers.yookassa.process_successful_payment",
                AsyncMock(),
            ) as process_success,
        ):
            result = await billing_module._refresh_yookassa_payment_status(
                request,
                session,
                payment,
            )

        self.assertIs(result, refreshed_payment)
        session.commit.assert_awaited_once()
        process_success.assert_awaited_once()
        provider_payload = process_success.await_args.args[2]
        self.assertEqual(provider_payload["amount"], {"value": "100.0", "currency": "RUB"})

    async def test_yookassa_webapp_payment_uses_unrestricted_checkout_form(self):
        payment_record = SimpleNamespace(payment_id=77)
        yookassa_service = SimpleNamespace(
            configured=True,
            config=SimpleNamespace(
                DEFAULT_RECEIPT_EMAIL="receipt@example.test",
                autopayments_active=True,
                AUTOPAYMENTS_REQUIRE_CARD_BINDING=True,
            ),
            create_payment=AsyncMock(
                return_value={
                    "id": "yk_77",
                    "status": "pending",
                    "confirmation_url": "https://yookassa.example/pay",
                }
            ),
        )
        session = AsyncMock()
        ctx = WebAppPaymentContext(
            request=SimpleNamespace(app={"yookassa_service": yookassa_service}),
            session=session,
            user_id=1001,
            method="yookassa",
            months=1,
            price=100.0,
            stars_price=None,
            description="Subscription",
            sale_mode="subscription",
        )

        with (
            patch(
                "bot.payment_providers.yookassa.create_webapp_payment_record",
                AsyncMock(return_value=payment_record),
            ),
            patch(
                "bot.payment_providers.yookassa.payment_dal.update_payment_status_by_db_id",
                AsyncMock(),
            ),
        ):
            response = await create_webapp_payment(ctx)

        self.assertEqual(response.status, 200)
        yookassa_service.create_payment.assert_awaited_once()
        self.assertIs(
            yookassa_service.create_payment.await_args.kwargs["save_payment_method"],
            False,
        )

    async def test_payment_status_invalidates_profile_cache_for_succeeded_payment(self):
        settings = SimpleNamespace()
        payment = SimpleNamespace(payment_id=42, user_id=1001, status="succeeded")
        request = SimpleNamespace(
            app={"settings": settings, "async_session_factory": _SessionFactory()},
            match_info={"payment_id": "42"},
        )

        with (
            patch.object(billing_module, "_require_user_id", return_value=1001),
            patch.object(
                billing_module.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_module,
                "_refresh_yookassa_payment_status",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_module,
                "invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate_cache,
        ):
            response = await billing_module.payment_status_route(request)

        invalidate_cache.assert_awaited_once_with(settings, 1001, include_devices=True)
        self.assertEqual(response.status, 200)

    async def test_wata_pending_payment_refresh_delegates_to_provider_service(self):
        payment = SimpleNamespace(
            payment_id=43,
            user_id=1001,
            provider="wata",
            status="pending_wata",
        )
        refreshed_payment = SimpleNamespace(
            payment_id=43,
            user_id=1001,
            provider="wata",
            status="succeeded",
        )
        wata_service = SimpleNamespace(
            configured=True,
            refresh_payment_status=AsyncMock(return_value=refreshed_payment),
        )
        request = SimpleNamespace(app={"wata_service": wata_service})
        session = AsyncMock()

        result = await billing_module._refresh_wata_payment_status(request, session, payment)

        self.assertIs(result, refreshed_payment)
        wata_service.refresh_payment_status.assert_awaited_once_with(session, payment)
