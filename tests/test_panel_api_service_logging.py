import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.panel_api_service import PanelApiService


class PanelApiServiceLoggingTests(unittest.IsolatedAsyncioTestCase):
    def _make_service(self) -> PanelApiService:
        return PanelApiService(
            SimpleNamespace(
                PANEL_API_URL="https://panel.example.test/api",
                PANEL_API_KEY="panel-key",
                USER_HWID_DEVICE_LIMIT=None,
            )
        )

    async def test_update_user_details_does_not_log_full_response_by_default(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"uuid": "user-uuid"}})

        with patch("bot.services.panel_api_service.logging.info") as info_log:
            result = await service.update_user_details_on_panel(
                "user-uuid",
                {"description": "profile"},
            )

        self.assertEqual(result, {"uuid": "user-uuid"})
        service._request.assert_awaited_once_with(
            "PATCH",
            "/users",
            json={"description": "profile", "uuid": "user-uuid"},
            log_full_response=False,
        )
        info_log.assert_not_called()

    async def test_update_user_details_can_still_request_full_response_logging(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"uuid": "user-uuid"}})

        await service.update_user_details_on_panel(
            "user-uuid",
            {"description": "profile"},
            log_response=True,
        )

        self.assertTrue(service._request.await_args.kwargs["log_full_response"])

    async def test_get_user_by_uuid_uses_short_ttl_cache_and_update_invalidates(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"uuid": "user-uuid"}})

        first = await service.get_user_by_uuid("user-uuid")
        second = await service.get_user_by_uuid("user-uuid")

        self.assertEqual(first, {"uuid": "user-uuid"})
        self.assertEqual(second, {"uuid": "user-uuid"})
        self.assertEqual(service._request.await_count, 1)

        await service.update_user_details_on_panel("user-uuid", {"description": "updated"})
        await service.get_user_by_uuid("user-uuid")

        self.assertEqual(service._request.await_count, 3)

    async def test_get_user_devices_uses_short_ttl_cache_and_disconnect_invalidates(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": [{"hwid": "device-1"}]})

        first = await service.get_user_devices("user-uuid")
        second = await service.get_user_devices("user-uuid")

        self.assertEqual(first, [{"hwid": "device-1"}])
        self.assertEqual(second, [{"hwid": "device-1"}])
        self.assertEqual(service._request.await_count, 1)

        await service.disconnect_device("user-uuid", "device-1")
        await service.get_user_devices("user-uuid")

        self.assertEqual(service._request.await_count, 3)

    async def test_get_all_panel_users_uses_singleflight_cache_and_update_invalidates(self):
        service = self._make_service()
        get_calls = 0

        async def fake_request(method, endpoint, **kwargs):
            nonlocal get_calls
            if method == "GET":
                get_calls += 1
                return {"response": {"users": [{"uuid": "user-uuid"}]}}
            return {"response": {"uuid": "user-uuid"}}

        service._request = AsyncMock(side_effect=fake_request)

        first, second = await asyncio.gather(
            service.get_all_panel_users(),
            service.get_all_panel_users(),
        )

        self.assertEqual(first, [{"uuid": "user-uuid"}])
        self.assertEqual(second, [{"uuid": "user-uuid"}])
        self.assertEqual(get_calls, 1)

        await service.update_user_details_on_panel("user-uuid", {"description": "updated"})
        await service.get_all_panel_users()

        self.assertEqual(get_calls, 2)

    async def test_get_all_panel_users_falls_back_to_100_when_large_page_fails(self):
        service = self._make_service()
        requested_sizes = []

        async def fake_request(method, endpoint, **kwargs):
            params = kwargs.get("params") or {}
            size = params.get("size")
            requested_sizes.append(size)
            if size == 1000:
                return {"error": True, "status_code": 400}
            return {"response": {"users": [{"uuid": "user-uuid"}]}}

        service._request = AsyncMock(side_effect=fake_request)

        users = await service.get_all_panel_users()

        self.assertEqual(users, [{"uuid": "user-uuid"}])
        self.assertEqual(requested_sizes, [1000, 100])


if __name__ == "__main__":
    unittest.main()
