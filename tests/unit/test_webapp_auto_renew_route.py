import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp import billing as billing_module
from bot.app.web.webapp import billing_subscription
from db.dal import user_billing_dal


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
                "settings": SimpleNamespace(DEFAULT_LANGUAGE="en"),
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
                "update_subscription",
                AsyncMock(),
            ) as update_subscription,
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
        update_subscription.assert_awaited_once_with(
            session,
            7,
            {"auto_renew_enabled": False},
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
                "update_subscription",
                AsyncMock(),
            ) as update_subscription,
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
        update_subscription.assert_awaited_once_with(
            session,
            8,
            {"auto_renew_enabled": True},
        )
        has_saved_method.assert_awaited_once_with(session, 42, provider="yookassa")
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()
