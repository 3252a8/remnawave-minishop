import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiohttp import web

from bot.app.web.webapp import billing_qa
from bot.payment_providers.qa import service as qa_service


class _SessionContext:
    def __init__(self) -> None:
        self.session = AsyncMock()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


class _SessionFactory:
    def __init__(self) -> None:
        self.context = _SessionContext()

    def __call__(self):
        return self.context


def _service(*, mode: str = "development", enabled: bool = True):
    return qa_service.QaPaymentService(
        settings=SimpleNamespace(APP_RUNTIME_MODE=mode),
        bot=SimpleNamespace(),
        async_session_factory=_SessionFactory(),
        i18n=SimpleNamespace(),
        subscription_service=SimpleNamespace(),
        referral_service=SimpleNamespace(),
        config=qa_service.QaPaymentConfig(ENABLED=enabled, SECRET="secret"),
    )


def _payment(**overrides):
    values = {
        "payment_id": 42,
        "user_id": 1001,
        "provider": "qa",
        "provider_payment_id": "qa:42",
        "status": "pending_qa",
        "sale_mode": "subscription",
        "amount": 150.0,
        "currency": "RUB",
        "user": SimpleNamespace(user_id=1001),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class QaPaymentTests(IsolatedAsyncioTestCase):
    async def test_complete_route_requires_authentication(self) -> None:
        with (
            patch.object(billing_qa, "_require_user_id", side_effect=web.HTTPUnauthorized()),
            self.assertRaises(web.HTTPUnauthorized),
        ):
            await billing_qa.complete_qa_payment_route(SimpleNamespace())

    async def test_complete_route_is_hidden_when_qa_is_not_available(self) -> None:
        for mode, enabled in (("production", True), ("development", False)):
            with self.subTest(mode=mode, enabled=enabled):
                service = _service(mode=mode, enabled=enabled)
                request = SimpleNamespace(
                    app={"qa_service": service}, match_info={"payment_id": "42"}
                )
                with patch.object(billing_qa, "_require_user_id", return_value=1001):
                    response = await billing_qa.complete_qa_payment_route(request)
                self.assertEqual(response.status, 404)

    async def test_complete_route_checks_owner_and_provider(self) -> None:
        cases = ((_payment(user_id=2002), 404), (_payment(provider="stripe"), 400))
        for payment, status in cases:
            with self.subTest(payment=payment, status=status):
                service = _service()
                factory = _SessionFactory()
                request = SimpleNamespace(
                    app={"qa_service": service, "async_session_factory": factory},
                    match_info={"payment_id": "42"},
                )
                with (
                    patch.object(billing_qa, "_require_user_id", return_value=1001),
                    patch.object(
                        billing_qa.payment_dal,
                        "get_payment_by_db_id",
                        AsyncMock(return_value=payment),
                    ),
                ):
                    response = await billing_qa.complete_qa_payment_route(request)
                self.assertEqual(response.status, status)

    async def test_complete_payment_uses_shared_finalizer_for_regular_and_gift(self) -> None:
        for sale_mode in ("subscription", "subscription@base|d30|gift"):
            with self.subTest(sale_mode=sale_mode):
                service = _service()
                session = AsyncMock()
                payment = _payment(sale_mode=sale_mode)
                finalizer = AsyncMock(return_value=SimpleNamespace(final_end_date=None))
                with (
                    patch.object(
                        qa_service.payment_dal,
                        "claim_payment_finalization",
                        AsyncMock(return_value=payment),
                    ),
                    patch.object(qa_service, "payment_units_for_activation", return_value=1),
                    patch.object(qa_service, "finalize_successful_payment", finalizer),
                ):
                    response = await service.complete_payment(session, payment)
                self.assertEqual(response.status, 200)
                finalizer_call = finalizer.await_args
                self.assertIsNotNone(finalizer_call)
                assert finalizer_call is not None
                self.assertEqual(finalizer_call.args[0].sale_mode, sale_mode)

    async def test_complete_payment_is_idempotent_after_success(self) -> None:
        service = _service()
        response = await service.complete_payment(AsyncMock(), _payment(status="succeeded"))
        self.assertEqual(response.status, 200)
        self.assertTrue(json.loads(response.body)["duplicate"])
