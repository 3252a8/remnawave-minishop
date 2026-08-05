import asyncio
import time
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, call, patch

import aiohttp

from bot.services.panel_api_compat import PanelApiCompatibility
from bot.services.panel_api_contracts import PanelApiCapability, PanelApiOperation
from bot.services.panel_api_service import PanelApiService, _endpoint_log_label
from tests.support.settings_stub import settings_stub


class PanelApiServiceLoggingTests(unittest.IsolatedAsyncioTestCase):
    def _make_service(self, *, detect_version: bool = False) -> PanelApiService:
        service = PanelApiService(
            settings_stub(
                PANEL_API_URL="https://panel.example.test/api",
                PANEL_API_KEY="panel-key",
                USER_HWID_DEVICE_LIMIT=None,
            )
        )
        if not detect_version:
            # Most unit tests mock the transport itself. A fresh unknown result
            # preserves endpoint-fallback behavior without turning the version
            # probe into an unrelated extra mock call.
            service._panel_api_compatibility = PanelApiCompatibility.unknown()
            service._panel_api_compatibility_detected_at = time.monotonic()
        return service

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
            headers: ClassVar[dict[str, str]] = {"Content-Type": "application/json"}

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

    async def test_successful_html_response_is_a_protocol_error(self):
        service = self._make_service()

        class HtmlResponse:
            status = 200
            headers: ClassVar[dict[str, str]] = {"Content-Type": "text/html; charset=utf-8"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def text(self):
                return "<html><body>Sign in</body></html>"

        service._get_session = AsyncMock(
            return_value=SimpleNamespace(request=lambda *_args, **_kwargs: HtmlResponse())
        )

        result = await service._request_once("GET", "/system/stats")

        self.assertTrue(result["error"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(
            result["message"],
            "Panel API returned an unexpected non-JSON response.",
        )
        self.assertEqual(result["details"]["content_type"], "text/html; charset=utf-8")
        self.assertNotIn("data_text", result)

    async def test_successful_invalid_json_response_is_a_protocol_error(self):
        service = self._make_service()

        class InvalidJsonResponse:
            status = 200
            headers: ClassVar[dict[str, str]] = {"Content-Type": "application/json"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def text(self):
                return "not-json"

        service._get_session = AsyncMock(
            return_value=SimpleNamespace(request=lambda *_args, **_kwargs: InvalidJsonResponse())
        )

        result = await service._request_once("GET", "/system/stats")

        self.assertTrue(result["error"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["message"], "Panel API returned invalid JSON.")
        self.assertIn("parse_error", result["details"])
        self.assertNotIn("data_text", result)

    async def test_successful_empty_204_response_is_not_a_protocol_error(self):
        service = self._make_service()

        class EmptyResponse:
            status = 204
            headers: ClassVar[dict[str, str]] = {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

            async def text(self):
                return ""

        service._get_session = AsyncMock(
            return_value=SimpleNamespace(request=lambda *_args, **_kwargs: EmptyResponse())
        )

        result = await service._request_once("DELETE", "/users/42")

        self.assertEqual(
            result,
            {"status": "success", "status_code": 204, "response": None},
        )

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
            operation=PanelApiOperation.USER_UPDATE,
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

    async def test_update_v3_user_sends_numeric_id_selector(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"id": 42}})

        result = await service.update_user_details_on_panel("42", {"description": "profile"})

        self.assertEqual(result, {"id": 42, "uuid": "42"})
        service._request.assert_awaited_once_with(
            "PATCH",
            "/users",
            operation=PanelApiOperation.USER_UPDATE,
            json={"description": "profile", "id": 42},
            log_full_response=False,
        )

    async def test_future_major_allows_best_effort_mutations(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "4.0.0"}}
        )
        service._panel_api_compatibility_detected_at = time.monotonic()
        service._request = AsyncMock(return_value={"response": {"id": 42}})

        result = await service.update_user_details_on_panel("42", {"description": "profile"})

        self.assertEqual(result, {"id": 42, "uuid": "42"})
        service._request.assert_awaited_once_with(
            "PATCH",
            "/users",
            operation=PanelApiOperation.USER_UPDATE,
            json={"description": "profile", "id": 42},
            log_full_response=False,
        )

    async def test_empty_update_success_reloads_user_for_legacy_return_contract(self):
        service = self._make_service()
        service._request = AsyncMock(
            side_effect=[
                {"status": "success", "status_code": 204, "response": None},
                {"response": {"id": 42, "description": "updated"}},
            ]
        )

        result = await service.update_user_details_on_panel("42", {"description": "updated"})

        self.assertEqual(result, {"id": 42, "uuid": "42", "description": "updated"})
        self.assertEqual(
            [call.kwargs["operation"] for call in service._request.await_args_list],
            [PanelApiOperation.USER_UPDATE, PanelApiOperation.USER_GET],
        )

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

    async def test_create_panel_user_uses_exact_expiry_and_hwid_limit(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"uuid": "user-uuid"}})
        expire_at = datetime(2026, 2, 3, 4, 5, 6, 789000, tzinfo=UTC)

        await service.create_panel_user(
            username_on_panel="tg_42",
            expire_at=expire_at,
            hwid_device_limit=4,
        )

        payload = service._request.await_args.kwargs["json"]
        self.assertEqual(payload["expireAt"], "2026-02-03T04:05:06.789Z")
        self.assertEqual(payload["hwidDeviceLimit"], 4)

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

    async def test_get_user_by_uuid_can_bypass_stale_cache_for_verification(self):
        service = self._make_service()
        service._request = AsyncMock(
            side_effect=[
                {"response": {"uuid": "user-uuid", "trafficLimitBytes": 100}},
                {"response": {"uuid": "user-uuid", "trafficLimitBytes": 200}},
            ]
        )

        cached = await service.get_user_by_uuid("user-uuid")
        fresh = await service.get_user_by_uuid("user-uuid", use_cache=False)

        self.assertEqual(cached["trafficLimitBytes"], 100)
        self.assertEqual(fresh["trafficLimitBytes"], 200)
        self.assertEqual(service._request.await_count, 2)

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
            operation=PanelApiOperation.USER_GET,
            log_full_response=False,
        )

    async def test_v3_stale_uuid_lookup_is_rejected_without_an_http_request(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.0.0"}}
        )
        service._panel_api_compatibility_detected_at = time.monotonic()
        service._request = AsyncMock()

        result = await service.get_user_by_uuid_lookup("legacy-user-uuid")

        self.assertFalse(result["ok"])
        self.assertFalse(result["not_found"])
        self.assertIn("classification=incompatible_user_reference", result["failure_reason"])
        self.assertIn("action=panel_sync_required", result["failure_reason"])
        service._request.assert_not_awaited()

    async def test_v2_numeric_user_mutation_is_rejected_without_an_http_request(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "2.8.1"}}
        )
        service._panel_api_compatibility_detected_at = time.monotonic()
        service._request = AsyncMock()

        result = await service.update_user_details_on_panel("42", {"description": "profile"})

        self.assertIsNone(result)
        service._request.assert_not_awaited()

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
            {"error": True, "status_code": 404, "errorCode": "A025"},
            {"error": True, "status_code": 400, "details": {"errorCode": "A062"}},
            {"error": True, "status_code": 404, "details": {"errorCode": "A063"}},
            {"error": True, "status_code": 404, "details": {"code": "user_not_found"}},
        ]

        for response in cases:
            with self.subTest(response=response):
                service._request = AsyncMock(return_value=response)

                result = await service.get_user_by_uuid_lookup("missing-user")

                self.assertFalse(result["ok"])
                self.assertTrue(result["not_found"])
                self.assertIsNone(result["user"])
                self.assertIn("classification=confirmed_not_found", result["failure_reason"])

    def test_user_not_found_does_not_include_unrelated_a040_error(self):
        service = self._make_service()

        self.assertFalse(
            service._is_user_not_found_response(
                {
                    "error": True,
                    "status_code": 500,
                    "details": {"errorCode": "A040"},
                }
            )
        )

    async def test_delete_user_from_panel_treats_plain_404_as_already_deleted(self):
        service = self._make_service()
        service._request = AsyncMock(
            return_value={
                "error": True,
                "status_code": 404,
                "details": {"message": "Request failed with status 404"},
            }
        )

        with (
            patch.object(service, "_invalidate_user_cache", AsyncMock()) as invalidate_user,
            patch.object(service, "_invalidate_devices_cache", AsyncMock()) as invalidate_devices,
            patch.object(service, "_invalidate_all_users_cache", AsyncMock()) as invalidate_all,
        ):
            result = await service.delete_user_from_panel("missing-user")

        self.assertTrue(result)
        service._request.assert_awaited_once_with(
            "DELETE",
            "/users/missing-user",
            operation=PanelApiOperation.USER_DELETE,
            log_full_response=False,
        )
        invalidate_user.assert_awaited_once_with("missing-user")
        invalidate_devices.assert_awaited_once_with("missing-user")
        invalidate_all.assert_awaited_once_with()

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

    async def test_revoke_subscription_clears_all_hwid_devices_first(self):
        service = self._make_service()
        service.get_user_devices = AsyncMock(
            return_value=[{"hwid": "device-1"}, {"hwid": "device-2"}]
        )
        service.disconnect_device = AsyncMock(return_value=True)
        service._request = AsyncMock(
            return_value={
                "response": {
                    "uuid": "user-uuid",
                    "subscriptionUrl": "https://sub.example.test/new",
                }
            }
        )

        result = await service.revoke_user_subscription("user-uuid")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["subscriptionUrl"], "https://sub.example.test/new")
        self.assertEqual(
            service.disconnect_device.await_args_list,
            [
                call("user-uuid", "device-1"),
                call("user-uuid", "device-2"),
            ],
        )
        service._request.assert_awaited_once_with(
            "POST",
            "/users/user-uuid/actions/revoke",
            operation=PanelApiOperation.USER_REVOKE,
            log_full_response=False,
        )

    async def test_revoke_subscription_aborts_when_hwid_cleanup_fails(self):
        service = self._make_service()
        service.get_user_devices = AsyncMock(return_value=[{"hwid": "device-1"}])
        service.disconnect_device = AsyncMock(return_value=False)
        service._request = AsyncMock()

        result = await service.revoke_user_subscription("user-uuid")

        self.assertIsNone(result)
        service._request.assert_not_awaited()

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
            operation=PanelApiOperation.HWID_STATS,
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
            operation=PanelApiOperation.HWID_TOP_USERS,
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
            operation=PanelApiOperation.NODE_RESTART,
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
            operation=PanelApiOperation.NODES_RESTART_ALL,
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
            operation=PanelApiOperation.SUBSCRIPTION_CONFIG_RESOLVED,
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
            operation=PanelApiOperation.SUBSCRIPTION_PAGE_CONFIG_LIST,
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
            operation=PanelApiOperation.SUBSCRIPTION_PAGE_CONFIG_GET,
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

    async def test_get_all_panel_users_normalizes_v3_numeric_ids(self):
        service = self._make_service()
        service._request = AsyncMock(
            return_value={"response": {"users": [{"id": 42, "username": "tg_42"}]}}
        )

        users = await service.get_all_panel_users()

        self.assertEqual(users, [{"id": 42, "uuid": "42", "username": "tg_42"}])

    async def test_v3_filter_uses_stream_and_caches_metadata(self):
        service = self._make_service(detect_version=True)

        async def fake_request(method, endpoint, **kwargs):
            if endpoint == "/system/metadata":
                return {"response": {"version": "3.0.0"}}
            if endpoint == "/users/stream":
                return {
                    "response": {
                        "users": [
                            {
                                "id": 42,
                                "telegramId": 99,
                                "email": "user@example.test",
                            }
                        ]
                    }
                }
            return {"error": True, "status_code": 404}

        service._request = AsyncMock(side_effect=fake_request)

        first = await service.get_users_by_filter(telegram_id=99)
        second = await service.get_users_by_filter(email="user@example.test")

        expected = [
            {
                "id": 42,
                "uuid": "42",
                "telegramId": 99,
                "email": "user@example.test",
            }
        ]
        self.assertEqual(first, expected)
        self.assertEqual(second, expected)
        endpoints = [call.args[1] for call in service._request.await_args_list]
        self.assertEqual(endpoints.count("/system/metadata"), 1)
        self.assertNotIn("/users/by-telegram-id/99", endpoints)
        self.assertNotIn("/users/by-email/user@example.test", endpoints)

    async def test_filtered_stream_rechecks_results_if_old_panel_ignores_query(self):
        service = self._make_service(detect_version=True)
        service._request = AsyncMock(
            side_effect=[
                {"response": {"version": "3.0.0"}},
                {
                    "response": {
                        "users": [
                            {"id": 41, "telegramId": 98},
                            {"id": 42, "telegramId": 99},
                        ]
                    }
                },
            ]
        )

        users = await service.get_users_by_filter(telegram_id=99)

        self.assertEqual(users, [{"id": 42, "uuid": "42", "telegramId": 99}])

    async def test_user_filters_treat_a063_as_a_confirmed_miss(self):
        for filter_args in (
            {"telegram_id": 99},
            {"username": "tg_99"},
            {"email": "user@example.test"},
        ):
            with self.subTest(filter_args=filter_args):
                service = self._make_service()
                service._request = AsyncMock(
                    return_value={
                        "error": True,
                        "status_code": 404,
                        "details": {"errorCode": "A063"},
                    }
                )

                users = await service.get_users_by_filter(**filter_args)

                self.assertEqual(users, [])

    async def test_hot_upgrade_route_404_refreshes_metadata_before_not_found_handling(self):
        service = self._make_service()
        service._request = AsyncMock(
            side_effect=[
                {
                    "error": True,
                    "status_code": 404,
                    "message": "Cannot GET /api/users/by-telegram-id/99",
                },
                {"response": {"version": "3.2.0"}},
                {"response": {"users": []}},
            ]
        )

        users = await service.get_users_by_filter(telegram_id=99)

        self.assertEqual(users, [])
        self.assertEqual(
            [call.args[1] for call in service._request.await_args_list],
            ["/users/by-telegram-id/99", "/system/metadata", "/users/stream"],
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

    async def test_known_v3_stream_failure_never_calls_removed_legacy_users_route(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.2.0"}}
        )
        service._panel_api_compatibility_detected_at = time.monotonic()
        service._request = AsyncMock(return_value={"error": True, "status_code": 503})

        users = await service.get_all_panel_users(page_size=100)

        self.assertIsNone(users)
        service._request.assert_awaited_once()
        self.assertEqual(service._request.await_args.args[1], "/users/stream")
        self.assertTrue(
            service.panel_capability_state(
                PanelApiCapability.USER_STREAM,
                service._panel_api_compatibility,
            )
        )

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

    async def test_get_all_panel_users_rejects_unsupported_legacy_response_shape(self):
        service = self._make_service()
        calls = []

        async def fake_request(method, endpoint, **kwargs):
            calls.append(endpoint)
            if endpoint == "/users/stream":
                return {"error": True, "status_code": 404}
            return {"response": {"unexpected": []}}

        service._request = AsyncMock(side_effect=fake_request)

        users = await service.get_all_panel_users()

        self.assertIsNone(users)
        self.assertEqual(calls, ["/users/stream", "/users", "/users/stream", "/users"])

    async def test_drop_user_connections_targets_only_given_nodes(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"eventSent": True}})

        dropped = await service.drop_user_connections("user-uuid", ["node-1", "node-2"])

        self.assertTrue(dropped)
        service._request.assert_awaited_once_with(
            "POST",
            "/ip-control/drop-connections",
            operation=PanelApiOperation.USER_CONNECTIONS_DROP_V2,
            json={
                "dropBy": {"by": "userUuids", "userUuids": ["user-uuid"]},
                "targetNodes": {
                    "target": "specificNodes",
                    "nodeUuids": ["node-1", "node-2"],
                },
            },
            log_full_response=False,
        )

    async def test_drop_user_connections_without_nodes_targets_all_nodes(self):
        service = self._make_service()
        service._request = AsyncMock(return_value={"response": {"eventSent": True}})

        await service.drop_user_connections("user-uuid")

        payload = service._request.await_args.kwargs["json"]
        self.assertEqual(payload["targetNodes"], {"target": "allNodes"})

    async def test_drop_v3_user_connections_uses_connections_contract(self):
        service = self._make_service()
        service._request = AsyncMock(
            return_value={"status": "success", "status_code": 202, "response": None}
        )

        dropped = await service.drop_user_connections("42", ["node-1"])

        self.assertTrue(dropped)
        service._request.assert_awaited_once_with(
            "POST",
            "/connections/drop",
            operation=PanelApiOperation.USER_CONNECTIONS_DROP_V3,
            json={
                "dropBy": {"by": "userIds", "userIds": [42]},
                "targetNodes": {"target": "specificNodes", "nodeUuids": ["node-1"]},
            },
            log_full_response=False,
        )

    async def test_disconnect_v3_device_uses_numeric_user_id(self):
        service = self._make_service()
        service._request = AsyncMock(
            return_value={"status": "success", "status_code": 204, "response": None}
        )

        disconnected = await service.disconnect_device("42", "device-1")

        self.assertTrue(disconnected)
        service._request.assert_awaited_once_with(
            "POST",
            "/hwid/devices/delete",
            operation=PanelApiOperation.HWID_DEVICE_DELETE,
            json={"userId": 42, "hwid": "device-1"},
            log_full_response=False,
        )

    async def test_v3_user_scoped_resource_routes_use_numeric_id(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.0.0"}}
        )
        service._panel_api_compatibility_detected_at = time.monotonic()
        service._request = AsyncMock(
            side_effect=[
                {"response": {"devices": []}},
                {"response": {"categories": [], "series": [], "topNodes": []}},
                {"status": "success", "status_code": 204, "response": None},
            ]
        )

        devices = await service.get_user_devices("42")
        bandwidth = await service.get_user_bandwidth_stats(
            "42",
            start="2026-07-01",
            end="2026-08-01",
        )
        reset = await service.reset_user_traffic("42")

        self.assertEqual(devices, [])
        self.assertEqual(bandwidth, {"categories": [], "series": [], "topNodes": []})
        self.assertTrue(reset)
        self.assertEqual(
            [(call.args[0], call.args[1]) for call in service._request.await_args_list],
            [
                ("GET", "/hwid/devices/42"),
                ("GET", "/bandwidth-stats/users/42"),
                ("POST", "/users/42/actions/reset-traffic"),
            ],
        )
        self.assertEqual(
            service._request.await_args_list[1].kwargs["params"],
            {"start": "2026-07-01", "end": "2026-08-01", "topNodesLimit": 20},
        )

    async def test_user_bandwidth_without_a_complete_range_does_not_call_panel(self):
        service = self._make_service()
        service._request = AsyncMock()

        result = await service.get_user_bandwidth_stats("panel-uuid", start="2026-07-01")

        self.assertIsNone(result)
        service._request.assert_not_awaited()

    async def test_v3_squad_mutation_uses_targeted_bulk_contract(self):
        service = self._make_service()
        service._request = AsyncMock(
            return_value={"status": "success", "status_code": 202, "response": None}
        )

        added = await service.add_users_to_internal_squad("squad-1", ["42", "43"])

        self.assertTrue(added)
        service._request.assert_awaited_once_with(
            "POST",
            "/internal-squads/squad-1/bulk-actions/add-many-users",
            operation=PanelApiOperation.INTERNAL_SQUAD_ADD_USERS,
            json={"userIds": [42, 43]},
            log_full_response=False,
        )

    async def test_v3_squad_mutation_chunks_panel_limited_batches(self):
        service = self._make_service()
        service._V3_SQUAD_BULK_LIMIT = 2
        service._request = AsyncMock(
            return_value={"status": "success", "status_code": 202, "response": None}
        )

        added = await service.add_users_to_internal_squad("squad-1", ["42", "43", "44"])

        self.assertTrue(added)
        payloads = [call.kwargs["json"] for call in service._request.await_args_list]
        self.assertEqual(payloads, [{"userIds": [42, 43]}, {"userIds": [44]}])

    async def test_v3_exact_squad_bulk_uses_numeric_ids(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.0.0"}}
        )
        service._request = AsyncMock(
            return_value={"status": "success", "status_code": 204, "response": None}
        )

        updated = await service.update_users_internal_squads_exact(
            ["42", "43"],
            ["standard", "premium"],
        )

        self.assertTrue(updated)
        service._request.assert_awaited_once_with(
            "POST",
            "/users/bulk/update-squads",
            operation=PanelApiOperation.USERS_BULK_UPDATE_SQUADS,
            json={
                "userIds": [42, 43],
                "activeInternalSquads": ["standard", "premium"],
            },
            log_full_response=False,
        )

    async def test_v2_exact_squad_bulk_uses_uuids(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "2.8.1"}}
        )
        service._request = AsyncMock(return_value={"response": {"affectedRows": 2}})

        updated = await service.update_users_internal_squads_exact(
            ["uuid-1", "uuid-2"],
            ["standard"],
        )

        self.assertTrue(updated)
        self.assertEqual(
            service._request.await_args.kwargs["json"],
            {"uuids": ["uuid-1", "uuid-2"], "activeInternalSquads": ["standard"]},
        )

    async def test_exact_squad_bulk_skips_empty_state_due_to_v3_a088(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.0.0"}}
        )
        service._request = AsyncMock()

        updated = await service.update_users_internal_squads_exact(["42"], [])

        self.assertFalse(updated)
        service._request.assert_not_awaited()

    async def test_v3_connection_drop_batches_users(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.0.0"}}
        )
        service._request = AsyncMock(
            return_value={"status": "success", "status_code": 202, "response": None}
        )

        dropped = await service.drop_users_connections(["42", "43"], ["node-1"])

        self.assertTrue(dropped)
        self.assertEqual(
            service._request.await_args.kwargs["json"]["dropBy"],
            {"by": "userIds", "userIds": [42, 43]},
        )

    async def test_v3_multi_node_usage_validates_shape(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.0.0"}}
        )
        service._request = AsyncMock(
            return_value={
                "response": {
                    "nodes": [{"uuid": "node-1", "users": [{"id": 42, "totalBytes": 100}]}]
                }
            }
        )

        usage = await service.get_multi_node_user_usage(
            ["node-1"],
            start="2026-08-01",
            end="2026-08-02",
        )

        self.assertIsNotNone(usage)
        service._request.assert_awaited_once_with(
            "POST",
            "/bandwidth-stats/nodes/usage",
            operation=PanelApiOperation.NODES_USER_USAGE,
            params={"start": "2026-08-01", "end": "2026-08-02", "minTotalBytes": 0},
            json={"nodesUuids": ["node-1"]},
            log_full_response=False,
        )

    async def test_v2_multi_node_top_users_preserves_limit(self):
        service = self._make_service()
        service._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "2.8.1"}}
        )
        service._request = AsyncMock(
            return_value={"response": {"topUsers": [{"username": "one", "total": 1}]}}
        )

        usage = await service.get_multi_node_users_bandwidth_stats(
            ["node-1", "node-2"],
            start="2026-08-01",
            end="2026-08-02",
            top_users_limit=30_001,
        )

        self.assertIsNotNone(usage)
        self.assertEqual(service._request.await_args.kwargs["params"]["topUsersLimit"], 30_001)

    async def test_drop_user_connections_tolerates_panel_without_connected_nodes(self):
        service = self._make_service()
        service._request = AsyncMock(
            return_value={
                "error": True,
                "status_code": 404,
                "details": {"message": "Connected nodes not found", "errorCode": "A219"},
            }
        )

        with self.assertNoLogs("bot.services.panel_api_users", level="ERROR"):
            dropped = await service.drop_user_connections("user-uuid", ["node-1"])

        self.assertFalse(dropped)

    async def test_drop_user_connections_warns_when_panel_lacks_the_endpoint(self):
        service = self._make_service()
        service._request = AsyncMock(
            return_value={
                "error": True,
                "status_code": 404,
                "details": {
                    "message": "Cannot POST /api/ip-control/drop-connections",
                    "error": "Not Found",
                },
            }
        )

        with self.assertLogs("bot.services.panel_api_connections", level="WARNING") as logs:
            dropped = await service.drop_user_connections("user-uuid", ["node-1"])

        self.assertFalse(dropped)
        self.assertTrue(any("ip-control" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
