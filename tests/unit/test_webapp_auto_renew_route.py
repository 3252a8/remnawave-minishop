import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp import billing as billing_module
from bot.app.web.webapp import billing_subscription
from db.balance_renewal import GrantBalanceRenewal, renewal_provider
from db.dal import auto_renew_dal, user_billing_dal


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Request:
    def __init__(self, payload, app):
        self._payload = payload
        self.app = app

    async def json(self):
        return self._payload


class WebAppAutoRenewRouteTests(IsolatedAsyncioTestCase):
    async def test_granted_subscription_requires_explicit_balance_terms(self):
        for origin, source in (("trial", "user"), ("admin", "partner")):
            with self.subTest(origin=origin, source=source):
                await self._check_grant_balance_setup(origin, source)

    async def _check_grant_balance_setup(self, origin, source):
        sub = SimpleNamespace(
            subscription_id=7,
            user_id=42,
            is_active=True,
            provider=origin,
            auto_renew_enabled=True,
            auto_renew_consent_version=4,
            end_date=datetime.now(UTC) + timedelta(hours=2),
        )
        request, session, user = self._request({"enabled": True}, sub=sub)
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        service = SimpleNamespace(configured=True, recurring_active=True)
        request.app["subscription_service"].recurring_service_for = lambda provider: service
        selection = GrantBalanceRenewal(f"{source}_balance", "standard", 90)
        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(billing_module.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch.object(
                billing_module.subscription_dal,
                "get_subscription_by_id_for_update",
                AsyncMock(return_value=sub),
            ),
            patch.object(auto_renew_dal, "stop_open_cycles_for_subscription", AsyncMock()) as stop,
            patch.object(
                auto_renew_dal, "get_cycle_by_subscription_anchor", AsyncMock(return_value=None)
            ) as current_cycle,
            patch.object(billing_subscription, "_invalidate_webapp_user_caches", AsyncMock()),
            patch.object(billing_subscription, "balance_recurring_available", return_value=True),
            patch.object(billing_subscription, "quote_grant_balance_renewal") as quote,
        ):
            response = await billing_subscription.subscription_auto_renew_route(request)
            self.assertEqual(response.status, 400)
            self.assertEqual(renewal_provider(sub), origin)
            session.commit.assert_not_awaited()

            request._payload["balance_renewal"] = {
                "source": source,
                "tariff_key": "standard",
                "duration_days": 90,
            }
            quote.return_value = None
            response = await billing_subscription.subscription_auto_renew_route(request)
            self.assertEqual(response.status, 400)
            self.assertEqual(renewal_provider(sub), origin)
            session.commit.assert_not_awaited()

            quote.return_value = SimpleNamespace(amount=700)
            response = await billing_subscription.subscription_auto_renew_route(request)
            self.assertEqual(response.status, 200)
            quote.assert_called_with(request.app["settings"], sub, selection)
            self.assertEqual(renewal_provider(sub), selection.provider)
            self.assertEqual(sub.provider, origin)
            self.assertEqual(sub.auto_renew_consent_version, 5)
            session.commit.assert_awaited_once()
            stop.assert_awaited_once_with(session, 7, "consent_changed")

            response = await billing_subscription.subscription_auto_renew_route(request)
            self.assertEqual(response.status, 200)
            self.assertEqual(sub.auto_renew_consent_version, 5)
            stop.assert_awaited_once()

            request._payload["balance_renewal"]["duration_days"] = 30
            current_cycle.return_value = SimpleNamespace(cycle_id=8)
            response = await billing_subscription.subscription_auto_renew_route(request)
            self.assertEqual(response.status, 409)
            self.assertEqual(json.loads(response.text)["error"], "balance_renewal_cycle_started")
            self.assertEqual(sub.balance_renewal_duration_days, 90)
            self.assertEqual(sub.auto_renew_consent_version, 5)

            request._payload = {"enabled": False}
            response = await billing_subscription.subscription_auto_renew_route(request)
            self.assertEqual(response.status, 200)
            self.assertEqual(renewal_provider(sub), origin)
            self.assertFalse(sub.auto_renew_enabled)
            self.assertEqual(sub.auto_renew_consent_version, 6)

    async def test_tribute_creator_requires_external_cancellation(self):
        sub = SimpleNamespace(
            subscription_id=7, user_id=42, provider="tribute", auto_renew_enabled=True
        )
        request, session, user = self._request({"enabled": False}, sub=sub)
        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(billing_module.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch.object(
                billing_subscription.tribute_dal,
                "get_other_active_creator_subscription_id",
                AsyncMock(return_value=123),
            ),
            patch.object(billing_module.subscription_dal, "set_auto_renew", AsyncMock()) as update,
            patch.object(
                billing_subscription, "stop_provider_managed_recurrence", AsyncMock()
            ) as cancel,
        ):
            response = await billing_module.subscription_auto_renew_route(request)
        self.assertEqual(response.status, 409)
        self.assertEqual(json.loads(response.text)["error"], "auto_renew_tribute_cancel_required")
        update.assert_not_awaited()
        cancel.assert_not_awaited()
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()

    async def test_tribute_creator_confirmation_disables_only_local_renewal(self):
        paid_until = "2099-01-01"
        sub = SimpleNamespace(
            subscription_id=7,
            user_id=42,
            provider="tribute",
            auto_renew_enabled=True,
            end_date=paid_until,
        )
        request, session, user = self._request(
            {"enabled": False, "creator_cancellation_confirmed": True}, sub=sub
        )
        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(billing_module.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch.object(
                billing_subscription.tribute_dal,
                "get_other_active_creator_subscription_id",
                AsyncMock(return_value=123),
            ),
            patch.object(
                billing_subscription.tribute_dal,
                "get_other_active_shop_order_uuid",
                AsyncMock(return_value=None),
            ),
            patch.object(billing_module.subscription_dal, "set_auto_renew", AsyncMock()) as update,
            patch.object(
                billing_subscription, "stop_provider_managed_recurrence", AsyncMock()
            ) as cancel,
            patch.object(billing_subscription, "_invalidate_webapp_user_caches", AsyncMock()),
        ):
            response = await billing_module.subscription_auto_renew_route(request)

        self.assertEqual(response.status, 200)
        self.assertFalse(json.loads(response.text)["auto_renew_enabled"])
        update.assert_awaited_once_with(session, 7, False, stop_reason="customer_disabled")
        cancel.assert_not_awaited()
        self.assertEqual(sub.end_date, paid_until)
        session.commit.assert_awaited_once()

    async def test_tribute_shop_can_still_cancel_in_app(self):
        sub = SimpleNamespace(
            subscription_id=7, user_id=42, provider="tribute", auto_renew_enabled=True
        )
        request, session, user = self._request({"enabled": False}, sub=sub)
        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(billing_module.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch.object(
                billing_subscription.tribute_dal,
                "get_other_active_creator_subscription_id",
                AsyncMock(return_value=None),
            ),
            patch.object(billing_module.subscription_dal, "set_auto_renew", AsyncMock()) as update,
            patch.object(
                billing_subscription,
                "stop_provider_managed_recurrence",
                AsyncMock(return_value=True),
            ) as cancel,
            patch.object(billing_subscription, "_invalidate_webapp_user_caches", AsyncMock()),
        ):
            response = await billing_module.subscription_auto_renew_route(request)
        self.assertEqual(response.status, 200)
        self.assertFalse(json.loads(response.text)["auto_renew_enabled"])
        cancel.assert_awaited_once_with(
            request.app["subscription_service"], session, user_id=42, provider="tribute"
        )
        update.assert_awaited_once()
        session.commit.assert_awaited_once()

    def _request(self, payload, *, sub, recurring_active=True):
        session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        user = SimpleNamespace(
            user_id=42,
            is_banned=False,
            panel_user_uuid="panel-uuid",
            language_code="en",
        )
        recurring_service = SimpleNamespace(configured=True, recurring_active=recurring_active)
        subscription_service = SimpleNamespace(
            recurring_provider_services={"yookassa": recurring_service},
            recurring_service_for=lambda provider: {"yookassa": recurring_service}.get(provider),
        )
        request = _Request(
            payload,
            {
                "settings": SimpleNamespace(DEFAULT_LANGUAGE="en", REDIS_URL=None),
                "subscription_service": subscription_service,
                "async_session_factory": _SessionFactory(session),
            },
        )
        return request, session, user

    async def test_disables_yookassa_auto_renew_even_when_recurring_service_inactive(self):
        sub = SimpleNamespace(
            subscription_id=7,
            user_id=42,
            provider="yookassa",
            auto_renew_enabled=True,
        )
        request, session, user = self._request(
            {"enabled": False},
            sub=sub,
            recurring_active=False,
        )

        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(billing_module.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch.object(
                billing_module.subscription_dal,
                "set_auto_renew",
                AsyncMock(),
            ) as set_auto_renew,
            patch.object(
                user_billing_dal,
                "user_has_saved_payment_method",
                AsyncMock(return_value=False),
            ) as has_saved_method,
            patch.object(billing_subscription, "_invalidate_webapp_user_caches", AsyncMock()),
        ):
            response = await billing_module.subscription_auto_renew_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text)["auto_renew_enabled"], False)
        set_auto_renew.assert_awaited_once_with(
            session,
            7,
            False,
            stop_reason="customer_disabled",
        )
        has_saved_method.assert_not_awaited()
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    async def test_enables_yookassa_auto_renew_through_shared_recurring_service(self):
        sub = SimpleNamespace(
            subscription_id=8,
            user_id=42,
            provider="yookassa",
            auto_renew_enabled=False,
        )
        request, session, user = self._request({"enabled": True}, sub=sub)

        with (
            patch.object(billing_subscription, "_require_user_id", return_value=42),
            patch.object(billing_module.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch.object(
                billing_module.subscription_dal,
                "set_auto_renew",
                AsyncMock(),
            ) as set_auto_renew,
            patch.object(
                user_billing_dal,
                "user_has_saved_payment_method",
                AsyncMock(return_value=True),
            ) as has_saved_method,
            patch.object(billing_subscription, "_invalidate_webapp_user_caches", AsyncMock()),
        ):
            response = await billing_module.subscription_auto_renew_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text)["auto_renew_enabled"], True)
        set_auto_renew.assert_awaited_once_with(
            session,
            8,
            True,
            stop_reason="consent_changed",
        )
        has_saved_method.assert_awaited_once_with(session, 42, provider="yookassa")
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
