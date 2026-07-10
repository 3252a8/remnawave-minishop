import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import users as admin_users
from bot.app.web.admin_api_impl import users_actions
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
        self.enabled_tariffs = list(tariffs)
        self.default_tariff = tariffs[0].key if tariffs else ""

    def require(self, key):
        tariff = self._tariffs.get(key)
        if not tariff:
            raise KeyError(key)
        return tariff


class FakeRequest:
    def __init__(self, body, session, subscription_service, settings=None):
        self.app = {
            "settings": settings or settings_stub(),
            "async_session_factory": lambda: session,
            "subscription_service": subscription_service,
        }
        self.match_info = {"user_id": "42"}
        self._body = body

    async def json(self):
        return self._body


class AdminUserHwidLimitRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_unlimited_payload_stores_zero_and_syncs_panel(self):
        session = FakeSession()
        active = SimpleNamespace(hwid_device_limit=3)
        subscription_service = SimpleNamespace(
            sync_hwid_device_limit_to_panel=AsyncMock(return_value=0)
        )
        request = FakeRequest(
            {"unlimited": True, "hwid_device_limit": 999}, session, subscription_service
        )

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
            patch.object(admin_users.message_log_dal, "create_message_log_no_commit", AsyncMock()),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
            patch.object(
                users_actions,
                "_serialize_subscription",
                return_value={"hwid_device_limit": 0},
            ),
        ):
            response = await admin_users.admin_user_hwid_device_limit_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text)["subscription"]["hwid_device_limit"], 0)
        self.assertEqual(active.hwid_device_limit, 0)
        subscription_service.sync_hwid_device_limit_to_panel.assert_awaited_once_with(session, 42)
        self.assertTrue(session.committed)
        self.assertEqual(session.refreshed, active)

    async def test_use_default_payload_stores_null_override(self):
        session = FakeSession()
        active = SimpleNamespace(hwid_device_limit=5)
        subscription_service = SimpleNamespace(
            sync_hwid_device_limit_to_panel=AsyncMock(return_value=3)
        )
        request = FakeRequest({"use_default": True}, session, subscription_service)

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
            patch.object(admin_users.message_log_dal, "create_message_log_no_commit", AsyncMock()),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
            patch.object(
                users_actions,
                "_serialize_subscription",
                return_value={"hwid_device_limit": None},
            ),
        ):
            response = await admin_users.admin_user_hwid_device_limit_route(request)

        self.assertEqual(response.status, 200)
        self.assertIsNone(json.loads(response.text)["subscription"]["hwid_device_limit"])
        self.assertIsNone(active.hwid_device_limit)
        subscription_service.sync_hwid_device_limit_to_panel.assert_awaited_once_with(session, 42)

    async def test_hwid_sync_failure_rolls_back_without_audit_log(self):
        session = FakeSession()
        active = SimpleNamespace(hwid_device_limit=5)
        subscription_service = SimpleNamespace(
            sync_hwid_device_limit_to_panel=AsyncMock(return_value=None)
        )
        request = FakeRequest({"hwid_device_limit": 7}, session, subscription_service)

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
            patch.object(
                admin_users.message_log_dal,
                "create_message_log_no_commit",
                AsyncMock(),
            ) as log,
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            response = await admin_users.admin_user_hwid_device_limit_route(request)

        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(response.text)["error"], "panel_update_failed")
        self.assertTrue(session.rolled_back)
        self.assertFalse(session.committed)
        log.assert_not_awaited()

    async def test_negative_limit_is_rejected(self):
        session = FakeSession()
        subscription_service = SimpleNamespace(
            sync_hwid_device_limit_to_panel=AsyncMock(return_value=None)
        )
        request = FakeRequest({"hwid_device_limit": -1}, session, subscription_service)

        with patch.object(users_actions, "_require_admin_user_id", return_value=100):
            response = await admin_users.admin_user_hwid_device_limit_route(request)

        self.assertEqual(response.status, 400)


class AdminUserExtendRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_extend_route_can_skip_hwid_device_extension(self):
        session = FakeSession()
        new_end = datetime(2099, 2, 1, tzinfo=UTC)
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=new_end)
        )
        request = FakeRequest(
            {"days": 10, "extend_hwid_devices": False},
            session,
            subscription_service,
        )

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.message_log_dal, "create_message_log", AsyncMock()) as log,
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=1)),
            ),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
            patch.object(users_actions, "_serialize_subscription", return_value={"ok": True}),
        ):
            response = await admin_users.admin_user_extend_route(request)

        self.assertEqual(response.status, 200)
        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session,
            42,
            10,
            "admin_extend_subscription_webapp",
            extend_hwid_devices=False,
            apply_tariff_hwid_limit=False,
        )
        self.assertIn("hwid=no", log.await_args.args[1]["content"])
        self.assertTrue(session.committed)

    async def test_extend_route_extends_hwid_devices_by_default(self):
        session = FakeSession()
        new_end = datetime(2099, 2, 1, tzinfo=UTC)
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=new_end)
        )
        request = FakeRequest({"days": 10}, session, subscription_service)

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.message_log_dal, "create_message_log", AsyncMock()) as log,
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=1)),
            ),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
            patch.object(users_actions, "_serialize_subscription", return_value={"ok": True}),
        ):
            response = await admin_users.admin_user_extend_route(request)

        self.assertEqual(response.status, 200)
        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session,
            42,
            10,
            "admin_extend_subscription_webapp",
            extend_hwid_devices=True,
            apply_tariff_hwid_limit=False,
        )
        self.assertIn("hwid=yes", log.await_args.args[1]["content"])
        self.assertTrue(session.committed)

    async def test_extend_route_uses_single_period_tariff_by_default(self):
        session = FakeSession()
        new_end = datetime(2099, 2, 1, tzinfo=UTC)
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=new_end)
        )
        settings = settings_stub(
            tariffs_config=FakeTariffsConfig(
                [SimpleNamespace(key="standard", billing_model="period")]
            )
        )
        request = FakeRequest({"days": 10}, session, subscription_service, settings=settings)

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.message_log_dal, "create_message_log", AsyncMock()),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=1)),
            ),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
            patch.object(users_actions, "_serialize_subscription", return_value={"ok": True}),
        ):
            response = await admin_users.admin_user_extend_route(request)

        self.assertEqual(response.status, 200)
        subscription_service.extend_active_subscription_days.assert_awaited_once_with(
            session,
            42,
            10,
            "admin_extend_subscription_webapp",
            extend_hwid_devices=True,
            apply_tariff_hwid_limit=False,
            tariff_key="standard",
        )

    async def test_extend_route_requires_tariff_when_multiple_exist(self):
        session = FakeSession()
        subscription_service = SimpleNamespace(
            extend_active_subscription_days=AsyncMock(return_value=None)
        )
        settings = SimpleNamespace(
            tariffs_config=FakeTariffsConfig(
                [
                    SimpleNamespace(key="standard", billing_model="period"),
                    SimpleNamespace(key="plus", billing_model="period"),
                ]
            )
        )
        request = FakeRequest({"days": 10}, session, subscription_service, settings=settings)

        with patch.object(users_actions, "_require_admin_user_id", return_value=100):
            response = await admin_users.admin_user_extend_route(request)

        self.assertEqual(response.status, 400)
        self.assertEqual(json.loads(response.text)["error"], "tariff_required")
        subscription_service.extend_active_subscription_days.assert_not_awaited()

    async def test_change_tariff_route_switches_active_subscription(self):
        session = FakeSession()
        subscription_service = SimpleNamespace(
            switch_tariff_without_payment=AsyncMock(return_value={"subscription_id": 1})
        )
        settings = SimpleNamespace(
            tariffs_config=FakeTariffsConfig(
                [
                    SimpleNamespace(key="standard", billing_model="period"),
                    SimpleNamespace(key="plus", billing_model="period"),
                ]
            )
        )
        request = FakeRequest({"tariff_key": "plus"}, session, subscription_service, settings)

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.message_log_dal, "create_message_log", AsyncMock()),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=1)),
            ),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
            patch.object(
                users_actions,
                "_serialize_subscription",
                return_value={"tariff_key": "plus"},
            ),
        ):
            response = await admin_users.admin_user_tariff_route(request)

        self.assertEqual(response.status, 200)
        subscription_service.switch_tariff_without_payment.assert_awaited_once_with(
            session,
            42,
            "plus",
            "admin_assign",
            apply_tariff_hwid_limit=False,
        )
        self.assertTrue(session.committed)

    async def test_change_tariff_route_can_apply_tariff_hwid_limit(self):
        session = FakeSession()
        subscription_service = SimpleNamespace(
            switch_tariff_without_payment=AsyncMock(return_value={"subscription_id": 1})
        )
        settings = SimpleNamespace(
            tariffs_config=FakeTariffsConfig(
                [
                    SimpleNamespace(key="standard", billing_model="period"),
                    SimpleNamespace(key="plus", billing_model="period"),
                ]
            )
        )
        request = FakeRequest(
            {"tariff_key": "plus", "apply_tariff_hwid_limit": True},
            session,
            subscription_service,
            settings,
        )

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(admin_users.message_log_dal, "create_message_log", AsyncMock()),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=SimpleNamespace(subscription_id=1)),
            ),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
            patch.object(
                users_actions,
                "_serialize_subscription",
                return_value={"tariff_key": "plus"},
            ),
        ):
            response = await admin_users.admin_user_tariff_route(request)

        self.assertEqual(response.status, 200)
        subscription_service.switch_tariff_without_payment.assert_awaited_once_with(
            session,
            42,
            "plus",
            "admin_assign",
            apply_tariff_hwid_limit=True,
        )
        self.assertTrue(session.committed)

    async def test_over_max_limit_is_rejected(self):
        session = FakeSession()
        subscription_service = SimpleNamespace(
            sync_hwid_device_limit_to_panel=AsyncMock(return_value=None)
        )
        request = FakeRequest({"hwid_device_limit": 1_000_001}, session, subscription_service)

        with patch.object(users_actions, "_require_admin_user_id", return_value=100):
            response = await admin_users.admin_user_hwid_device_limit_route(request)

        self.assertEqual(response.status, 400)
        self.assertEqual(json.loads(response.text)["error"], "invalid_hwid_device_limit")
        subscription_service.sync_hwid_device_limit_to_panel.assert_not_awaited()


class AdminUserOverrideSyncFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_regular_traffic_override_failure_rolls_back_without_audit_log(self):
        session = FakeSession()
        active = SimpleNamespace(
            regular_unlimited_override=False,
            regular_bonus_bytes=0,
        )
        subscription_service = SimpleNamespace(
            sync_main_traffic_limit_to_panel=AsyncMock(return_value=False)
        )
        request = FakeRequest(
            {"unlimited": True, "regular_bonus_gb": 5},
            session,
            subscription_service,
        )

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
            patch.object(
                admin_users.message_log_dal,
                "create_message_log_no_commit",
                AsyncMock(),
            ) as log,
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            response = await admin_users.admin_user_regular_traffic_override_route(request)

        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(response.text)["error"], "panel_update_failed")
        self.assertTrue(session.rolled_back)
        self.assertFalse(session.committed)
        log.assert_not_awaited()

    async def test_premium_override_failure_rolls_back_without_audit_log(self):
        session = FakeSession()
        active = SimpleNamespace(
            premium_unlimited_override=False,
            premium_bonus_bytes=0,
            premium_is_limited=True,
        )
        subscription_service = SimpleNamespace(
            sync_premium_squad_access_to_panel=AsyncMock(return_value=False)
        )
        request = FakeRequest(
            {"unlimited": True, "bonus_gb": 0},
            session,
            subscription_service,
        )

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=100),
            patch.object(
                admin_users.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active),
            ),
            patch.object(
                admin_users.message_log_dal,
                "create_message_log_no_commit",
                AsyncMock(),
            ) as log,
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            response = await admin_users.admin_user_premium_override_route(request)

        self.assertEqual(response.status, 502)
        self.assertEqual(json.loads(response.text)["error"], "panel_update_failed")
        self.assertTrue(session.rolled_back)
        self.assertFalse(session.committed)
        log.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
