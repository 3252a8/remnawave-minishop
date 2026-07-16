import unittest
from unittest.mock import AsyncMock

from bot.services.panel_dry_run_api_service import PanelDryRunApiService
from tests.support.settings_stub import settings_stub


def _settings(**overrides):
    values = {
        "PANEL_API_URL": "https://panel.example.test/api",
        "PANEL_API_KEY": "panel-key",
        "PANEL_DRY_RUN_VALIDATE_REMOTE": False,
        "PANEL_DRY_RUN_SYNTHETIC_CREATE": True,
        "PANEL_USER_CACHE_TTL_SECONDS": 0,
        "PANEL_DEVICES_CACHE_TTL_SECONDS": 0,
        "PANEL_ALL_USERS_CACHE_TTL_SECONDS": 0,
        "PANEL_ALL_USERS_PAGE_SIZE": 1000,
        "REDIS_KEY_PREFIX": "tests",
        "USER_HWID_DEVICE_LIMIT": None,
    }
    values.update(overrides)
    return settings_stub(**values)


class PanelDryRunApiServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_user_details_returns_synthetic_success_without_http_write(self):
        service = PanelDryRunApiService(_settings())
        service._request_once = AsyncMock()

        result = await service.update_user_details_on_panel(
            "user-uuid",
            {"trafficLimitBytes": 1024, "trafficLimitStrategy": "NO_RESET"},
        )

        self.assertEqual(result["uuid"], "user-uuid")
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["trafficLimitBytes"], 1024)
        service._request_once.assert_not_awaited()

    async def test_update_user_details_rejects_invalid_payload(self):
        service = PanelDryRunApiService(_settings())
        service._request_once = AsyncMock()

        result = await service.update_user_details_on_panel(
            "user-uuid",
            {"trafficLimitBytes": -1, "trafficLimitStrategy": "NO_RESET"},
        )

        self.assertIsNone(result)
        service._request_once.assert_not_awaited()

    async def test_update_user_details_accepts_month_rolling_strategy(self):
        service = PanelDryRunApiService(_settings())
        service._request_once = AsyncMock()

        result = await service.update_user_details_on_panel(
            "user-uuid",
            {"trafficLimitBytes": 1024, "trafficLimitStrategy": "MONTH_ROLLING"},
        )

        self.assertEqual(result["trafficLimitStrategy"], "MONTH_ROLLING")
        service._request_once.assert_not_awaited()

    async def test_remote_validation_blocks_missing_panel_user(self):
        service = PanelDryRunApiService(_settings(PANEL_DRY_RUN_VALIDATE_REMOTE=True))
        service._request_once = AsyncMock(
            return_value={"error": True, "status_code": 404, "details": {"errorCode": "A062"}}
        )

        result = await service.update_user_details_on_panel(
            "missing-user",
            {"trafficLimitBytes": 1024, "trafficLimitStrategy": "NO_RESET"},
        )

        self.assertIsNone(result)
        service._request_once.assert_awaited_once()

    async def test_create_panel_user_returns_synthetic_user(self):
        service = PanelDryRunApiService(_settings())
        service._request_once = AsyncMock()

        result = await service.create_panel_user(
            username_on_panel="tg_42",
            telegram_id=42,
            default_traffic_limit_bytes=2048,
            default_traffic_limit_strategy="NO_RESET",
        )

        panel_user = result["response"]
        self.assertTrue(panel_user["dryRun"])
        self.assertEqual(panel_user["username"], "tg_42")
        self.assertIn("uuid", panel_user)
        self.assertTrue(
            panel_user["subscriptionUrl"].startswith("https://panel.example.test/api/sub/")
        )
        self.assertTrue(panel_user["subscriptionUrl"].endswith(panel_user["shortUuid"]))
        service._request_once.assert_not_awaited()

    async def test_happ_encrypt_runs_locally_without_http(self):
        service = PanelDryRunApiService(_settings())
        service._request_once = AsyncMock()

        result = await service.encrypt_happ_link("https://panel.example.test/sub/abc")

        assert result is not None
        self.assertTrue(result.startswith("happ://crypt4/"))
        service._request_once.assert_not_awaited()

    async def test_happ_encrypt_rejects_oversized_content_without_http(self):
        service = PanelDryRunApiService(_settings())
        service._request_once = AsyncMock()

        result = await service.encrypt_happ_link("x" * 502)

        self.assertIsNone(result)
        service._request_once.assert_not_awaited()

    async def test_restart_node_is_intercepted_with_force_restart_body(self):
        service = PanelDryRunApiService(_settings())
        service._request_once = AsyncMock()

        result = await service.restart_node("node-uuid", force_restart=True)

        self.assertTrue(result)
        service._request_once.assert_not_awaited()

    async def test_restart_all_nodes_requires_force_restart_bool_in_dry_run(self):
        service = PanelDryRunApiService(_settings())

        response = await service._request(
            "POST",
            "/nodes/actions/restart-all",
            json={},
            log_full_response=False,
        )

        self.assertTrue(response["error"])
        self.assertEqual(response["status_code"], 400)
        self.assertIn("forceRestart must be a boolean.", response["details"]["errors"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
