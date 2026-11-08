import unittest
from unittest.mock import AsyncMock, call

from bot.services.panel_api_user_mutations import PanelApiUserMutationMixin


class PanelHwidResetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = PanelApiUserMutationMixin()
        self.service.get_user_devices = AsyncMock()
        self.service.disconnect_device = AsyncMock(return_value=True)
        self.service._invalidate_devices_cache = AsyncMock()
        self.service._request = AsyncMock()

    async def test_removes_unique_hwids_without_revoking_or_editing_user(self):
        self.service.get_user_devices.return_value = [
            {"hwid": "old-client"},
            {"hwid": "current-client"},
            {"hwid": "old-client"},
        ]
        self.assertTrue(await self.service.reset_user_hwid_devices("user"))
        self.assertEqual(
            self.service.disconnect_device.await_args_list,
            [call("user", "old-client"), call("user", "current-client")],
        )
        self.service._request.assert_not_awaited()
        self.assertEqual(self.service._invalidate_devices_cache.await_count, 2)

    async def test_empty_device_list_succeeds(self):
        self.service.get_user_devices.return_value = []
        self.assertTrue(await self.service.reset_user_hwid_devices("user"))
        self.service.disconnect_device.assert_not_awaited()

    async def test_failed_device_lookup_does_not_report_success(self):
        self.service.get_user_devices.return_value = None
        self.assertFalse(await self.service.reset_user_hwid_devices("user"))
        self.service.disconnect_device.assert_not_awaited()

    async def test_invalid_device_list_is_validated_before_any_deletion(self):
        self.service.get_user_devices.return_value = [{"hwid": "valid"}, {"hwid": ""}]
        self.assertFalse(await self.service.reset_user_hwid_devices("user"))
        self.service.disconnect_device.assert_not_awaited()

    async def test_partial_failure_is_not_success_and_invalidates_cache(self):
        self.service.get_user_devices.return_value = [{"hwid": "first"}, {"hwid": "second"}]
        self.service.disconnect_device.side_effect = [True, False]
        self.assertFalse(await self.service.reset_user_hwid_devices("user"))
        self.assertEqual(self.service.disconnect_device.await_count, 2)
        self.assertEqual(self.service._invalidate_devices_cache.await_count, 2)

    async def test_transport_exception_still_invalidates_devices(self):
        self.service.get_user_devices.side_effect = RuntimeError("Panel offline")
        with self.assertRaises(RuntimeError):
            await self.service.reset_user_hwid_devices("user")
        self.assertEqual(self.service._invalidate_devices_cache.await_count, 2)
