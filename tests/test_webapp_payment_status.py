import json
import time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import billing as billing_module
from bot.payment_providers.base import PaymentProviderSpec, WebAppPaymentContext
from bot.payment_providers.freekassa import FreeKassaService
from bot.payment_providers.heleket import HeleketService
from bot.payment_providers.paykilla import PaykillaService
from bot.payment_providers.platega import PlategaService
from bot.payment_providers.severpay import SeverPayService
from bot.payment_providers.shared import reusable_webapp_payment_response
from bot.payment_providers.yookassa import create_webapp_payment, reuse_webapp_payment


class _SessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class WebAppPaymentStatusTests(IsolatedAsyncioTestCase):
    async def test_heleket_reuses_unexpired_check_payment(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="invoice-77",
            provider_payment_url=None,
        )
        service = object.__new__(HeleketService)
        service.get_payment_info = AsyncMock(
            return_value=(
                True,
                {
                    "uuid": "invoice-77",
                    "order_id": "77",
                    "amount": "299.00",
                    "currency": "RUB",
                    "payment_status": "check",
                    "is_final": False,
                    "expired_at": int(time.time()) + 900,
                    "url": "https://heleket.example/pay/77",
                },
            )
        )

        url = await service.try_reuse_pending_payment(payment)

        self.assertEqual(url, "https://heleket.example/pay/77")
        service.get_payment_info.assert_awaited_once_with("invoice-77")

    async def test_heleket_reuses_by_order_id_when_provider_amount_includes_fee(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="invoice-77",
            provider_payment_url=None,
        )
        service = object.__new__(HeleketService)
        service.get_payment_info = AsyncMock(
            return_value=(
                True,
                {
                    "uuid": "invoice-77",
                    "order_id": "77",
                    "amount": "314.00",
                    "currency": "RUB",
                    "payment_status": "check",
                    "is_final": False,
                    "expired_at": int(time.time()) + 900,
                    "url": "https://heleket.example/pay/77",
                },
            )
        )

        url = await service.try_reuse_pending_payment(payment)

        self.assertEqual(url, "https://heleket.example/pay/77")

    async def test_heleket_does_not_reuse_processing_payment(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="invoice-77",
            provider_payment_url="https://heleket.example/pay/77",
        )
        service = object.__new__(HeleketService)
        service.get_payment_info = AsyncMock(
            return_value=(
                True,
                {
                    "uuid": "invoice-77",
                    "order_id": "77",
                    "amount": "299.00",
                    "currency": "RUB",
                    "payment_status": "process",
                    "is_final": False,
                    "expired_at": int(time.time()) + 900,
                },
            )
        )

        self.assertIsNone(await service.try_reuse_pending_payment(payment))

    async def test_severpay_reuses_new_payment(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="12345",
            provider_payment_url="https://severpay.example/pay/77",
        )
        service = object.__new__(SeverPayService)
        service.get_payment = AsyncMock(
            return_value=(
                True,
                {
                    "id": 12345,
                    "uid": "payment-uid-77",
                    "order_id": "77",
                    "amount": 299.0,
                    "currency": "RUB",
                    "status": "new",
                },
            )
        )

        url = await service.try_reuse_pending_payment(payment)

        self.assertEqual(url, "https://severpay.example/pay/77")
        service.get_payment.assert_awaited_once_with("12345")

    async def test_severpay_reuses_by_order_id_when_provider_amount_includes_fee(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="12345",
            provider_payment_url="https://severpay.example/pay/77",
        )
        service = object.__new__(SeverPayService)
        service.get_payment = AsyncMock(
            return_value=(
                True,
                {
                    "id": 12345,
                    "uid": "payment-uid-77",
                    "order_id": "77",
                    "amount": 314.0,
                    "currency": "RUB",
                    "status": "new",
                },
            )
        )

        url = await service.try_reuse_pending_payment(payment)

        self.assertEqual(url, "https://severpay.example/pay/77")

    async def test_severpay_does_not_reuse_failed_payment(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="12345",
            provider_payment_url="https://severpay.example/pay/77",
        )
        service = object.__new__(SeverPayService)
        service.get_payment = AsyncMock(
            return_value=(
                True,
                {
                    "id": 12345,
                    "order_id": "77",
                    "amount": 299.0,
                    "currency": "RUB",
                    "status": "fail",
                },
            )
        )

        self.assertIsNone(await service.try_reuse_pending_payment(payment))

    async def test_platega_reuses_matching_pending_transaction(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="transaction-77",
            provider_payment_url="https://platega.example/pay/77",
        )
        service = object.__new__(PlategaService)
        service.get_transaction = AsyncMock(
            return_value=(
                True,
                {
                    "id": "transaction-77",
                    "status": "PENDING",
                    "paymentDetails": {"amount": 299.0, "currency": "RUB"},
                    "payload": json.dumps(
                        {
                            "payment_db_id": 77,
                            "user_id": 1001,
                            "sale_mode": "subscription@standard",
                            "platega_variant": "sbp",
                        }
                    ),
                },
            )
        )

        url = await service.try_reuse_pending_transaction(
            payment,
            user_id=1001,
            sale_mode="subscription@standard",
            variant="sbp",
        )

        self.assertEqual(url, "https://platega.example/pay/77")
        service.get_transaction.assert_awaited_once_with("transaction-77")

    async def test_platega_reuses_by_payload_when_provider_amount_includes_fee(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="transaction-77",
            provider_payment_url="https://platega.example/pay/77",
        )
        service = object.__new__(PlategaService)
        service.get_transaction = AsyncMock(
            return_value=(
                True,
                {
                    "id": "transaction-77",
                    "status": "PENDING",
                    "paymentDetails": {"amount": 314.0, "currency": "RUB"},
                    "payload": json.dumps(
                        {
                            "payment_db_id": 77,
                            "user_id": 1001,
                            "sale_mode": "subscription@standard",
                            "platega_variant": "sbp",
                        }
                    ),
                },
            )
        )

        url = await service.try_reuse_pending_transaction(
            payment,
            user_id=1001,
            sale_mode="subscription@standard",
            variant="sbp",
        )

        self.assertEqual(url, "https://platega.example/pay/77")

    async def test_platega_does_not_reuse_other_variant(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="transaction-77",
            provider_payment_url="https://platega.example/pay/77",
        )
        service = object.__new__(PlategaService)
        service.get_transaction = AsyncMock(
            return_value=(
                True,
                {
                    "id": "transaction-77",
                    "status": "PENDING",
                    "paymentDetails": {"amount": 299.0, "currency": "RUB"},
                    "payload": json.dumps(
                        {
                            "payment_db_id": 77,
                            "user_id": 1001,
                            "sale_mode": "subscription@standard",
                            "platega_variant": "crypto",
                        }
                    ),
                },
            )
        )

        self.assertIsNone(
            await service.try_reuse_pending_transaction(
                payment,
                user_id=1001,
                sale_mode="subscription@standard",
                variant="sbp",
            )
        )

    async def test_platega_reuses_tariff_upgrade_pending_transaction(self):
        payment = SimpleNamespace(
            payment_id=35,
            amount=150.0,
            currency="RUB",
            provider_payment_id="transaction-35",
            provider_payment_url="https://platega.example/pay/35",
        )
        service = object.__new__(PlategaService)
        service.get_transaction = AsyncMock(
            return_value=(
                True,
                {
                    "id": "transaction-35",
                    "status": "PENDING",
                    "paymentDetails": {"amount": 150.0, "currency": "RUB"},
                    "payload": json.dumps(
                        {
                            "payment_db_id": 35,
                            "user_id": 734546943,
                            "months": 1,
                            "sale_mode": "tariff_upgrade@main",
                            "traffic_gb": None,
                            "hwid_devices": None,
                            "source": "webapp",
                            "platega_variant": "sbp",
                        }
                    ),
                },
            )
        )

        url = await service.try_reuse_pending_transaction(
            payment,
            user_id=734546943,
            sale_mode="tariff_upgrade@main",
            variant="sbp",
        )

        self.assertEqual(url, "https://platega.example/pay/35")

    async def test_render_link_or_fail_skips_id_without_payment_url(self):
        from bot.payment_providers.shared.callbacks import render_link_or_fail

        payment = SimpleNamespace(payment_id=77, status="pending_platega")
        session = AsyncMock()
        callback = SimpleNamespace(
            message=SimpleNamespace(edit_text=AsyncMock()),
            answer=AsyncMock(),
        )

        with patch(
            "bot.payment_providers.shared.callbacks.safe_store_provider_payment_id",
            AsyncMock(return_value=True),
        ) as store_id, patch(
            "bot.payment_providers.shared.callbacks.render_payment_link",
            AsyncMock(),
        ) as render_link, patch(
            "bot.payment_providers.shared.callbacks.safe_mark_failed_creation",
            AsyncMock(),
        ) as mark_failed, patch(
            "bot.payment_providers.shared.callbacks.notify_payment_gateway_failure",
            AsyncMock(),
        ):
            await render_link_or_fail(
                callback,
                translator=lambda key, **kwargs: key,
                current_lang="ru",
                i18n=None,
                parts=SimpleNamespace(),
                session=session,
                payment=payment,
                api_success=True,
                payment_url=None,
                provider_payment_id="transaction-77",
                log_prefix="Platega",
            )

        store_id.assert_not_awaited()
        render_link.assert_not_awaited()
        mark_failed.assert_awaited_once()

    async def test_freekassa_reuses_matching_new_order(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="order-hash-77",
        )
        service = object.__new__(FreeKassaService)
        service.config = SimpleNamespace(PAYMENT_URL="https://freekassa.example/")
        service.get_orders = AsyncMock(
            return_value=(
                True,
                {
                    "type": "success",
                    "orders": [
                        {
                            "merchant_order_id": "77",
                            "fk_order_id": 12345,
                            "amount": 299.0,
                            "currency": "RUB",
                            "status": 0,
                        }
                    ],
                },
            )
        )

        url = await service.try_reuse_pending_order(payment)

        self.assertEqual(url, "https://freekassa.example/form/12345/order-hash-77")
        service.get_orders.assert_awaited_once_with(payment_id=77, order_status=0)

    async def test_freekassa_reuses_by_order_id_when_provider_amount_includes_fee(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="order-hash-77",
        )
        service = object.__new__(FreeKassaService)
        service.config = SimpleNamespace(PAYMENT_URL="https://freekassa.example/")
        service.get_orders = AsyncMock(
            return_value=(
                True,
                {
                    "orders": [
                        {
                            "merchant_order_id": "77",
                            "fk_order_id": 12345,
                            "amount": 199.0,
                            "currency": "RUB",
                            "status": 0,
                        }
                    ]
                },
            )
        )

        url = await service.try_reuse_pending_order(payment)

        self.assertEqual(url, "https://freekassa.example/form/12345/order-hash-77")

    async def test_reusable_payment_response_returns_existing_payment(self):
        payment = SimpleNamespace(payment_id=77)
        resolver = AsyncMock(return_value="https://provider.example/pay/77")
        spec = PaymentProviderSpec(
            id="provider",
            provider_key="provider",
            label="Provider",
            pending_status="pending_provider",
            enabled=lambda _config: True,
            reuse_webapp_payment=resolver,
        )
        ctx = WebAppPaymentContext(
            request=SimpleNamespace(app={}),
            session=AsyncMock(),
            user_id=1001,
            method="provider",
            months=3,
            price=299.0,
            stars_price=None,
            description="Subscription",
            sale_mode="subscription@standard",
            currency="RUB",
        )

        with patch.object(
            billing_module.payment_dal,
            "find_recent_pending_provider_payment",
            AsyncMock(return_value=payment),
        ) as find_pending:
            response = await reusable_webapp_payment_response(ctx, spec)

        self.assertIsNotNone(response)
        self.assertEqual(response.status, 200)
        self.assertIn(b'"payment_id": 77', response.body)
        resolver.assert_awaited_once_with(ctx, payment)
        self.assertEqual(find_pending.await_args.kwargs["amount"], 299.0)
        self.assertEqual(find_pending.await_args.kwargs["currency"], "RUB")
        self.assertEqual(find_pending.await_args.kwargs["sale_mode"], "subscription@standard")
        self.assertEqual(find_pending.await_args.kwargs["months"], 3)
        self.assertEqual(find_pending.await_args.kwargs["tariff_key"], "standard")

    async def test_yookassa_reuses_only_matching_pending_invoice(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            yookassa_payment_id="yk_77",
            provider_payment_id=None,
        )
        service = SimpleNamespace(
            configured=True,
            get_payment_info=AsyncMock(
                return_value={
                    "id": "yk_77",
                    "status": "pending",
                    "paid": False,
                    "amount_value": 299.0,
                    "amount_currency": "RUB",
                    "metadata": {
                        "user_id": "1001",
                        "payment_db_id": "77",
                        "sale_mode": "subscription@standard",
                    },
                    "confirmation_url": "https://yookassa.example/pay/77",
                }
            ),
        )
        ctx = WebAppPaymentContext(
            request=SimpleNamespace(app={"yookassa_service": service}),
            session=AsyncMock(),
            user_id=1001,
            method="yookassa",
            months=3,
            price=299.0,
            stars_price=None,
            description="Subscription",
            sale_mode="subscription@standard",
            currency="RUB",
        )

        url = await reuse_webapp_payment(ctx, payment)

        self.assertEqual(url, "https://yookassa.example/pay/77")
        service.get_payment_info.assert_awaited_once_with("yk_77")

    async def test_yookassa_reuses_by_metadata_when_provider_amount_includes_fee(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            yookassa_payment_id="yk_77",
            provider_payment_id=None,
        )
        service = SimpleNamespace(
            configured=True,
            get_payment_info=AsyncMock(
                return_value={
                    "id": "yk_77",
                    "status": "pending",
                    "paid": False,
                    "amount_value": 314.0,
                    "amount_currency": "RUB",
                    "metadata": {
                        "user_id": "1001",
                        "payment_db_id": "77",
                        "sale_mode": "subscription@standard",
                    },
                    "confirmation_url": "https://yookassa.example/pay/77",
                }
            ),
        )
        ctx = WebAppPaymentContext(
            request=SimpleNamespace(app={"yookassa_service": service}),
            session=AsyncMock(),
            user_id=1001,
            method="yookassa",
            months=3,
            price=299.0,
            stars_price=None,
            description="Subscription",
            sale_mode="subscription@standard",
            currency="RUB",
        )

        url = await reuse_webapp_payment(ctx, payment)

        self.assertEqual(url, "https://yookassa.example/pay/77")

    async def test_yookassa_does_not_reuse_invoice_with_other_sale_mode(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            yookassa_payment_id="yk_77",
            provider_payment_id=None,
        )
        service = SimpleNamespace(
            configured=True,
            get_payment_info=AsyncMock(
                return_value={
                    "status": "pending",
                    "paid": False,
                    "amount_value": 299.0,
                    "amount_currency": "RUB",
                    "metadata": {
                        "user_id": "1001",
                        "payment_db_id": "77",
                        "sale_mode": "traffic@standard",
                    },
                    "confirmation_url": "https://yookassa.example/pay/77",
                }
            ),
        )
        ctx = WebAppPaymentContext(
            request=SimpleNamespace(app={"yookassa_service": service}),
            session=AsyncMock(),
            user_id=1001,
            method="yookassa",
            months=3,
            price=299.0,
            stars_price=None,
            description="Subscription",
            sale_mode="subscription@standard",
            currency="RUB",
        )

        self.assertIsNone(await reuse_webapp_payment(ctx, payment))

    async def test_paykilla_reuses_processing_invoice_by_client_order_id(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="pk_77",
        )
        service = object.__new__(PaykillaService)
        service.config = SimpleNamespace(WIDGET_URL="https://gopay.paykilla.com")
        service.get_invoice_details = AsyncMock(
            return_value=(
                True,
                {
                    "id": "pk_77",
                    "clientOrderId": "77",
                    "status": "PROCESSING",
                    "totalPrice": "314.00",
                    "currency": "USD",
                },
            )
        )

        url = await service.try_reuse_pending_invoice(payment)

        self.assertEqual(url, "https://gopay.paykilla.com/pk_77")
        service.get_invoice_details.assert_awaited_once_with("pk_77")

    async def test_paykilla_does_not_reuse_invoice_with_other_client_order_id(self):
        payment = SimpleNamespace(
            payment_id=77,
            amount=299.0,
            currency="RUB",
            provider_payment_id="pk_77",
        )
        service = object.__new__(PaykillaService)
        service.config = SimpleNamespace(WIDGET_URL="https://gopay.paykilla.com")
        service.get_invoice_details = AsyncMock(
            return_value=(
                True,
                {
                    "id": "pk_77",
                    "clientOrderId": "88",
                    "status": "PROCESSING",
                },
            )
        )

        self.assertIsNone(await service.try_reuse_pending_invoice(payment))

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
