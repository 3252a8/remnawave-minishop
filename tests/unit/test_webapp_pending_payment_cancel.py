import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp import billing_payment_cancel


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _payment(**overrides):
    values = {
        "payment_id": 17,
        "user_id": 42,
        "provider": "pally",
        "provider_payment_id": "bill-17",
        "yookassa_payment_id": None,
        "status": "pending_pally",
        "promo_code_id": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _payload(response):
    return json.loads(response.text)


class WebAppPendingPaymentCancelTests(IsolatedAsyncioTestCase):
    async def test_confirms_provider_cancellation_before_releasing_checkout(self):
        session = AsyncMock()
        payment = _payment()
        canceled = _payment(status="canceled")
        service = SimpleNamespace(
            configured=True,
            cancel_pending_bill=AsyncMock(return_value=(True, {"activity": False})),
        )
        request = SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": _SessionFactory(session),
                "pally_service": service,
            },
            match_info={"payment_id": "17"},
        )

        with (
            patch.object(billing_payment_cancel, "_require_user_id", return_value=42),
            patch.object(
                billing_payment_cancel,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_payment_cancel.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_payment_cancel,
                "refresh_payment_status_for_request",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_payment_cancel.payment_dal,
                "transition_provider_payment_to_terminal",
                AsyncMock(return_value=(canceled, True)),
            ) as transition,
            patch.object(
                billing_payment_cancel,
                "_invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate,
        ):
            response = await billing_payment_cancel.cancel_payment_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(_payload(response), {"ok": True, "payment_id": 17, "status": "canceled"})
        service.cancel_pending_bill.assert_awaited_once_with("bill-17")
        transition.assert_awaited_once_with(
            session,
            17,
            "bill-17",
            "canceled",
            failure_kind="customer_canceled_checkout",
            provider_cancellation_party="customer",
            provider_cancellation_reason="customer_requested_promo_reuse",
            suppress_failure_notification=True,
        )
        session.commit.assert_awaited_once()
        invalidate.assert_awaited_once_with(request.app["settings"], 42)

    async def test_keeps_reservation_when_provider_cannot_cancel_checkout(self):
        session = AsyncMock()
        payment = _payment()
        request = SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": _SessionFactory(session),
                "pally_service": SimpleNamespace(configured=True),
            },
            match_info={"payment_id": "17"},
        )

        with (
            patch.object(billing_payment_cancel, "_require_user_id", return_value=42),
            patch.object(
                billing_payment_cancel,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_payment_cancel.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_payment_cancel,
                "refresh_payment_status_for_request",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_payment_cancel.payment_dal,
                "transition_provider_payment_to_terminal",
                AsyncMock(),
            ) as transition,
        ):
            response = await billing_payment_cancel.cancel_payment_route(request)

        self.assertEqual(response.status, 409)
        self.assertEqual(_payload(response)["error"], "payment_cancel_unavailable")
        transition.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_rejects_payment_owned_by_another_user(self):
        session = AsyncMock()
        payment = _payment(user_id=99)
        request = SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": _SessionFactory(session),
            },
            match_info={"payment_id": "17"},
        )

        with (
            patch.object(billing_payment_cancel, "_require_user_id", return_value=42),
            patch.object(
                billing_payment_cancel,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_payment_cancel.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_payment_cancel,
                "refresh_payment_status_for_request",
                AsyncMock(),
            ) as refresh,
        ):
            response = await billing_payment_cancel.cancel_payment_route(request)

        self.assertEqual(response.status, 404)
        refresh.assert_not_awaited()

    async def test_does_not_overwrite_success_that_wins_cancellation_race(self):
        session = AsyncMock()
        payment = _payment()
        succeeded = _payment(status="succeeded")
        service = SimpleNamespace(
            configured=True,
            cancel_pending_bill=AsyncMock(return_value=(True, {"activity": False})),
        )
        request = SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": _SessionFactory(session),
                "pally_service": service,
            },
            match_info={"payment_id": "17"},
        )

        with (
            patch.object(billing_payment_cancel, "_require_user_id", return_value=42),
            patch.object(
                billing_payment_cancel,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_payment_cancel.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_payment_cancel,
                "refresh_payment_status_for_request",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_payment_cancel.payment_dal,
                "transition_provider_payment_to_terminal",
                AsyncMock(return_value=(succeeded, False)),
            ),
        ):
            response = await billing_payment_cancel.cancel_payment_route(request)

        self.assertEqual(response.status, 409)
        self.assertEqual(_payload(response)["error"], "payment_completed")
        session.commit.assert_not_awaited()
