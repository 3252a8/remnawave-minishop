import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

from bot.services.panel_api_service import PanelApiService, _endpoint_log_label
from tests.support.settings_stub import settings_stub


class PanelApiServiceLoggingTests(unittest.IsolatedAsyncioTestCase):
    def _make_service(self) -> PanelApiService:
        return PanelApiService(
            settings_stub(
                PANEL_API_URL="https://panel.example.test/api",
                PANEL_API_KEY="panel-key",
                USER_HWID_DEVICE_LIMIT=None,
            )
        )

    async def test_client_timeout_uses_panel_settings(self):
        service = PanelApiService(
            settings_stub(
                PANEL_API_URL="https://panel.example.test/api",
                PANEL_API_KEY="panel-key",
                PANEL_API_TOTAL_TIMEOUT_SECONDS="30",
                PANEL_API_CONNECT_TIMEOUT_SECONDS="10",
                PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS="9",
                PANEL_API_SOCK_READ_TIMEOUT_SECONDS="20",
            )
        )

        timeout = service._client_timeout()

        self.assertEqual(timeout.total, 30)
        self.assertEqual(timeout.connect, 10)
        self.assertEqual(timeout.sock_connect, 9)
        self.assertEqual(timeout.sock_read, 20)

    async def test_prepare_headers_includes_optional_panel_cookie(self):
        service = PanelApiService(
            settings_stub(
                PANEL_API_URL="https://panel.example.test/api",
                PANEL_API_KEY="panel-key",
                PANEL_API_COOKIE="rw_session=session-value",
            )
        )

        headers = await service._prepare_headers()

        self.assertEqual(headers["Authorization"], "Bearer panel-key")
        self.assertEqual(headers["Cookie"], "rw_session=session-value")

    def test_endpoint_log_label_strips_user_identifiers(self):
        self.assertEqual(
            _endpoint_log_label("/users/by-email/user@example.com"),
            "/users/by-email",
        )
        self.assertEqual(_endpoint_log_label("/users/by-telegram-id/42"), "/users/by-telegram-id")
        self.assertEqual(_endpoint_log_label("/users/stream?size=1000"), "/users/stream")
        self.assertEqual(_endpoint_log_label("/users/some-uuid/actions/enable"), "/users")
        self.assertEqual(_endpoint_log_label("/hwid/devices/stats"), "/hwid/devices/stats")
        self.assertEqual(
            _endpoint_log_label("/hwid/devices/top-users?size=10"),
            "/hwid/devices/top-users",
        )
        self.assertEqual(
            _endpoint_log_label("/internal-squads/squad-uuid/bulk-actions/add-users"),
            "/internal-squads",
        )
        self.assertEqual(_endpoint_log_label("/system/stats"), "/system/stats")
        self.assertEqual(_endpoint_log_label("/unknown/path"), "/other")

    async def test_request_failure_logs_omit_user_identifiers(self):
        service = self._make_service()

        def fake_request(*_args, **_kwargs):
            raise TimeoutError()

        service._get_session = AsyncMock(return_value=SimpleNamespace(request=fake_request))

        with (
            patch("bot.services.panel_api_service.asyncio.sleep", new=AsyncMock()),
            self.assertLogs(level="INFO") as captured,
        ):
            result = await service._request("GET", "/users/by-email/user@example.com")

        self.assertTrue(result["error"])
        joined = "\n".join(captured.output)
        self.assertNotIn("user@example.com", joined)
        self.assertIn("endpoint=/users/by-email", joined)

    async def test_get_request_retries_connection_timeout(self):
        service = self._make_service()
        request_calls = 0

        class OkResponse:
            status = 200
            headers = {"Content-Type": "application/json"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def text(self):
                return '{"response": {"ok": true}}'

        def fake_request(*_args, **_kwargs):
            nonlocal request_calls
            request_calls += 1
            if request_calls == 1:
                raise aiohttp.ConnectionTimeoutError("connect took too long")
            return OkResponse()

        service._get_session = AsyncMock(return_value=SimpleNamespace(request=fake_request))

        with patch("bot.services.panel_api_service.asyncio.sleep", new=AsyncMock()):
            result = await service._request("GET", "/internal-squads")

        self.assertEqual(result, {"response": {"ok": True}})
        self.assertEqual(request_calls, 2)

    async def test_get_internal_squads_uses_stale_cache_after_refresh_failure(self):
        service = self._make_service()
        stale_squads = [{"uuid": "squad-1", "name": "Squad 1"}]
        service._squads_cache._data["list"] = (time.monotonic() - 1, stale_squads)
        service._get_internal_squads_uncached = AsyncMock(return_value=None)

        squads = await service.get_internal_squads()

        self.assertEqual(squads, stale_squads)
        service._get_internal_squads_uncached.assert_awaited_once()

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

    async def test_create_panel_user_omits_empty_description(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"uuid": "user-uuid"}})

        await service.create_panel_user(
            username_on_panel="tg_42",
            telegram_id=42,
            description="",
        )

        payload = service._request.await_args.kwargs["json"]
        self.assertNotIn("description", payload)
        self.assertEqual(payload["telegramId"], 42)

    async def test_create_panel_user_normalizes_legacy_traffic_strategy(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"uuid": "user-uuid"}})

        await service.create_panel_user(
            username_on_panel="tg_42",
            default_traffic_limit_strategy="MONTHLY",
        )

        payload = service._request.await_args.kwargs["json"]
        self.assertEqual(payload["trafficLimitStrategy"], "MONTH")

    async def test_update_user_details_normalizes_legacy_traffic_strategy(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"uuid": "user-uuid"}})

        await service.update_user_details_on_panel(
            "user-uuid",
            {"trafficLimitStrategy": "MONTHLY_ROLLING"},
        )

        payload = service._request.await_args.kwargs["json"]
        self.assertEqual(payload["trafficLimitStrategy"], "MONTH_ROLLING")

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

    async def test_get_user_by_uuid_lookup_returns_success_payload(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"uuid": "user-uuid"}})

        result = await service.get_user_by_uuid_lookup("user-uuid")

        self.assertTrue(result["ok"])
        self.assertFalse(result["not_found"])
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["user"], {"uuid": "user-uuid"})
        service._request.assert_awaited_once_with(
            "GET",
            "/users/user-uuid",
            log_full_response=False,
        )

    async def test_get_user_by_uuid_lookup_keeps_transient_errors_separate_from_not_found(self):
        service = self._make_service()
        transient_response = {
            "error": True,
            "status_code": -1,
            "message": "Connection error",
        }
        service._request = AsyncMock(return_value=transient_response)

        result = await service.get_user_by_uuid_lookup("user-uuid")

        self.assertFalse(result["ok"])
        self.assertFalse(result["not_found"])
        self.assertIsNone(result["user"])
        self.assertIn("classification=panel_lookup_failed", result["failure_reason"])
        self.assertIn("status_code=-1", result["failure_reason"])
        self.assertIn("message=Connection error", result["failure_reason"])
        self.assertEqual(result["response"], transient_response)

    async def test_get_user_by_uuid_lookup_marks_confirmed_not_found(self):
        service = self._make_service()
        cases = [
            {"error": True, "status_code": 404},
            {"error": True, "status_code": 400, "details": {"errorCode": "A062"}},
        ]

        for response in cases:
            with self.subTest(response=response):
                service._request = AsyncMock(return_value=response)

                result = await service.get_user_by_uuid_lookup("missing-user")

                self.assertFalse(result["ok"])
                self.assertTrue(result["not_found"])
                self.assertIsNone(result["user"])
                self.assertIn("classification=confirmed_not_found", result["failure_reason"])

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

    async def test_get_user_devices_accepts_remnawave_devices_object(self):
        service = self._make_service()
        service._request = AsyncMock(
            return_value={
                "response": {
                    "total": 1,
                    "devices": [{"hwid": "device-1", "deviceModel": "Laptop"}],
                }
            }
        )

        result = await service.get_user_devices("user-uuid")

        self.assertEqual(result, [{"hwid": "device-1", "deviceModel": "Laptop"}])

    async def test_get_user_devices_keeps_empty_panel_devices_list(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"total": 0, "devices": []}})

        result = await service.get_user_devices("user-uuid")

        self.assertEqual(result, [])

    async def test_get_hwid_devices_stats_returns_by_platform_by_app(self):
        service = self._make_service()
        panel_payload = {
            "byPlatform": [{"platform": "ios", "count": 2, "byApp": [{"app": "Happ", "count": 2}]}],
            "stats": {
                "totalUniqueDevices": 2,
                "totalHwidDevices": 2,
                "averageHwidDevicesPerUser": 1,
            },
        }
        service._request = AsyncMock(return_value={"response": panel_payload})

        result = await service.get_hwid_devices_stats()

        self.assertEqual(result, panel_payload)
        service._request.assert_awaited_once_with(
            "GET",
            "/hwid/devices/stats",
            log_full_response=False,
        )

    async def test_get_hwid_devices_top_users_uses_panel_endpoint(self):
        service = self._make_service()
        panel_payload = {"users": [{"userId": 2, "devicesCount": 3}]}
        service._request = AsyncMock(return_value={"response": panel_payload})

        result = await service.get_hwid_devices_top_users(start=5, size=20)

        self.assertEqual(result, panel_payload)
        service._request.assert_awaited_once_with(
            "GET",
            "/hwid/devices/top-users",
            params={"start": 5, "size": 20},
            log_full_response=False,
        )

    async def test_restart_node_sends_force_restart_body(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"ok": True}})

        result = await service.restart_node("node-uuid", force_restart=True)

        self.assertTrue(result)
        service._request.assert_awaited_once_with(
            "POST",
            "/nodes/node-uuid/actions/restart",
            json={"forceRestart": True},
            log_full_response=False,
        )

    async def test_restart_all_nodes_sends_force_restart_body(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"ok": True}})

        result = await service.restart_all_nodes(force_restart=False)

        self.assertTrue(result)
        service._request.assert_awaited_once_with(
            "POST",
            "/nodes/actions/restart-all",
            json={"forceRestart": False},
            log_full_response=False,
        )

    async def test_get_subscription_page_config_by_short_uuid_uses_panel_endpoint(self):
        service = self._make_service()
        panel_payload = {"config": {"version": "1"}}
        service._request = AsyncMock(return_value={"response": panel_payload})

        result = await service.get_subscription_page_config_by_short_uuid(
            "short-uuid",
            request_headers={"user-agent": "Mozilla/5.0"},
        )

        self.assertEqual(result, panel_payload)
        service._request.assert_awaited_once_with(
            "GET",
            "/subscriptions/subpage-config/short-uuid",
            json={"requestHeaders": {"user-agent": "Mozilla/5.0"}},
            log_full_response=False,
        )

    async def test_get_subscription_page_config_list_uses_panel_endpoint(self):
        service = self._make_service()
        panel_payload = {"configs": [{"uuid": "default"}]}
        service._request = AsyncMock(return_value={"response": panel_payload})

        result = await service.get_subscription_page_config_list()

        self.assertEqual(result, panel_payload)
        service._request.assert_awaited_once_with(
            "GET",
            "/subscription-page-configs",
            log_full_response=False,
        )

    async def test_get_subscription_page_config_by_uuid_uses_panel_endpoint(self):
        service = self._make_service()
        panel_payload = {"uuid": "default", "config": {"version": "1"}}
        service._request = AsyncMock(return_value={"response": panel_payload})

        result = await service.get_subscription_page_config_by_uuid("default")

        self.assertEqual(result, panel_payload)
        service._request.assert_awaited_once_with(
            "GET",
            "/subscription-page-configs/default",
            log_full_response=False,
        )

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

    async def test_get_all_panel_users_uses_stream_cursor_pagination(self):
        service = self._make_service()
        calls = []

        async def fake_request(method, endpoint, **kwargs):
            calls.append((endpoint, kwargs.get("params") or {}))
            params = kwargs.get("params") or {}
            if endpoint == "/users/stream" and not params.get("cursor"):
                return {
                    "response": {
                        "users": [{"uuid": "user-1"}],
                        "nextCursor": "cursor-2",
                    }
                }
            if endpoint == "/users/stream" and params.get("cursor") == "cursor-2":
                return {"response": {"users": [{"uuid": "user-2"}]}}
            return {"error": True, "status_code": 500}

        service._request = AsyncMock(side_effect=fake_request)

        users = await service.get_all_panel_users()

        self.assertEqual(users, [{"uuid": "user-1"}, {"uuid": "user-2"}])
        self.assertEqual(
            calls,
            [
                ("/users/stream", {"size": 1000}),
                ("/users/stream", {"size": 1000, "cursor": "cursor-2"}),
            ],
        )

    async def test_get_all_panel_users_falls_back_to_legacy_when_stream_is_missing(self):
        service = self._make_service()
        calls = []

        async def fake_request(method, endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint == "/users/stream":
                return {"error": True, "status_code": 404}
            return {"response": {"users": [{"uuid": "legacy-user"}]}}

        service._request = AsyncMock(side_effect=fake_request)

        users = await service.get_all_panel_users()

        self.assertEqual(users, [{"uuid": "legacy-user"}])
        self.assertEqual(calls, ["/users/stream", "/users"])

    async def test_get_all_panel_users_falls_back_when_stream_is_legacy_uuid_route(self):
        service = self._make_service()
        calls = []

        async def fake_request(method, endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint == "/users/stream":
                return {
                    "error": True,
                    "status_code": 400,
                    "message": "Validation failed",
                    "errors": [{"validation": "uuid", "path": ["uuid"]}],
                }
            return {"response": {"users": [{"uuid": "legacy-user"}]}}

        service._request = AsyncMock(side_effect=fake_request)

        users = await service.get_all_panel_users()

        self.assertEqual(users, [{"uuid": "legacy-user"}])
        self.assertEqual(calls, ["/users/stream", "/users"])

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
        self.assertEqual(requested_sizes, [1000, 1000, 100])


if __name__ == "__main__":
    unittest.main()
