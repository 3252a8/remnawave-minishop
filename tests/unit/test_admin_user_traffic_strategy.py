import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import users as admin_users
from bot.app.web.admin_api_impl import users_actions
from bot.app.web.admin_api_impl.common import _admin_subscription_traffic_strategy_fallback
from tests.support.settings_stub import settings_stub


class FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.refreshed = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def refresh(self, obj):
        self.refreshed = obj


class FakeTariffsConfig:
    def __init__(self, tariffs):
        self._tariffs = {tariff.key: tariff for tariff in tariffs}

    def require(self, key):
        tariff = self._tariffs.get(key)
        if not tariff:
            raise KeyError(key)
        return tariff


class FakeRequest:
    def __init__(self, body, session, panel_service, settings):
        self.app = {
            "settings": settings,
            "async_session_factory": lambda: session,
            "panel_service": panel_service,
        }
        self.match_info = {"user_id": "42"}
        self._body = body

    async def json(self):
        return self._body


def _active_subscription(**overrides):
    values = {
        "subscription_id": 1,
        "tariff_key": "standard",
        "provider": "yookassa",
        "panel_user_uuid": "panel-user-uuid",
        "period_start_at": datetime(2026, 7, 1, tzinfo=UTC),
        "premium_period_start_at": datetime(2026, 7, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AdminUserTrafficStrategyRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_user_card_fallback_uses_period_tariff_strategy(self):
        settings = settings_stub(
            USER_TRAFFIC_STRATEGY="DAY",
            tariffs_config=FakeTariffsConfig(
                [
                    SimpleNamespace(
                        key="standard",
                        billing_model="period",
                        traffic_limit_strategy="WEEK",
                    )
                ]
            ),
        )

        self.assertEqual(
            _admin_subscription_traffic_strategy_fallback(
                settings,
                _active_subscription(),
            ),
            "WEEK",
        )

    async def test_period_tariff_strategy_updates_panel_and_clears_local_period_anchors(self):
        session = FakeSession()
        panel_service = SimpleNamespace(
            update_user_details_on_panel=AsyncMock(
                return_value={"uuid": "panel-user-uuid", "trafficLimitStrategy": "WEEK"}
            )
        )
        settings = settings_stub(
            tariffs_config=FakeTariffsConfig(
                [SimpleNamespace(key="standard", billing_model="period")]
            )
        )
        active = _active_subscription()
        request = FakeRequest(
            {"traffic_limit_strategy": "weekly"}, session, panel_service, settings
        )

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
            patch.object(admin_users.message_log_dal, "create_message_log", AsyncMock()) as log,
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
            patch.object(
                users_actions,
                "_serialize_subscription",
                return_value={"subscription_id": 1},
            ),
        ):
            response = await admin_users.admin_user_traffic_strategy_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["subscription"]["traffic_limit_strategy"], "WEEK")
        self.assertTrue(payload["subscription"]["traffic_strategy_editable"])
        panel_service.update_user_details_on_panel.assert_awaited_once_with(
            "panel-user-uuid",
            {"uuid": "panel-user-uuid", "trafficLimitStrategy": "WEEK"},
        )
        self.assertIsNone(active.period_start_at)
        self.assertIsNone(active.premium_period_start_at)
        self.assertTrue(session.committed)
        self.assertEqual(session.refreshed, active)
        self.assertIn("traffic_limit_strategy=WEEK", log.await_args.args[1]["content"])

    async def test_traffic_tariff_strategy_change_is_blocked(self):
        session = FakeSession()
        panel_service = SimpleNamespace(update_user_details_on_panel=AsyncMock())
        settings = settings_stub(
            tariffs_config=FakeTariffsConfig(
                [SimpleNamespace(key="traffic-pack", billing_model="traffic")]
            )
        )
        active = _active_subscription(tariff_key="traffic-pack")
        request = FakeRequest({"traffic_limit_strategy": "MONTH"}, session, panel_service, settings)

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
        ):
            response = await admin_users.admin_user_traffic_strategy_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 409)
        self.assertEqual(payload["error"], "traffic_strategy_locked")
        panel_service.update_user_details_on_panel.assert_not_awaited()

    async def test_invalid_strategy_is_rejected_before_panel_update(self):
        session = FakeSession()
        panel_service = SimpleNamespace(update_user_details_on_panel=AsyncMock())
        settings = settings_stub(
            tariffs_config=FakeTariffsConfig(
                [SimpleNamespace(key="standard", billing_model="period")]
            )
        )
        request = FakeRequest(
            {"traffic_limit_strategy": "banana"},
            session,
            panel_service,
            settings,
        )

        with patch.object(users_actions, "_require_admin_user_id", return_value=100):
            response = await admin_users.admin_user_traffic_strategy_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 400)
        self.assertEqual(payload["error"], "invalid_traffic_strategy")
        panel_service.update_user_details_on_panel.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
