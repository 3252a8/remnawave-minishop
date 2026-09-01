from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from bot.app.web.admin_api_impl.user_device_summary import build_admin_user_hwid_devices


class AdminUserDeviceSummaryTests(IsolatedAsyncioTestCase):
    async def test_counts_devices_and_uses_panel_limit(self):
        panel_service = SimpleNamespace(
            get_user_devices=AsyncMock(return_value=[{"hwid": "one"}, {"hwid": "two"}])
        )

        summary = await build_admin_user_hwid_devices(
            panel_service=panel_service,
            panel_user_uuid="panel-user",
            panel_user_snapshot={"hwidDeviceLimit": 5},
            active_subscription=None,
            settings=SimpleNamespace(USER_HWID_DEVICE_LIMIT=None),
        )

        self.assertEqual(summary.current_devices, 2)
        self.assertEqual(summary.max_devices, 5)
        panel_service.get_user_devices.assert_awaited_once_with("panel-user")

    async def test_uses_infinity_for_unlimited_limit(self):
        panel_service = SimpleNamespace(get_user_devices=AsyncMock(return_value=[{"hwid": "one"}]))

        summary = await build_admin_user_hwid_devices(
            panel_service=panel_service,
            panel_user_uuid="panel-user",
            panel_user_snapshot={"hwidDeviceLimit": 0},
            active_subscription=None,
            settings=SimpleNamespace(USER_HWID_DEVICE_LIMIT=None),
        )

        self.assertEqual(summary.current_devices, 1)
        self.assertIsNone(summary.max_devices)

    async def test_falls_back_to_local_effective_limit(self):
        subscription = SimpleNamespace(hwid_device_limit=None, extra_hwid_devices=1)

        summary = await build_admin_user_hwid_devices(
            panel_service=None,
            panel_user_uuid=None,
            panel_user_snapshot=None,
            active_subscription=subscription,
            settings=SimpleNamespace(USER_HWID_DEVICE_LIMIT=4),
        )

        self.assertEqual(summary.current_devices, 0)
        self.assertEqual(summary.max_devices, 5)
