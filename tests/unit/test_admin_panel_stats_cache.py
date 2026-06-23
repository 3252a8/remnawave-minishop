import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.admin_api_impl import stats as stats_module


class AdminPanelStatsCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        stats_module._ADMIN_PANEL_STATS_CACHES.clear()
        stats_module._ADMIN_DB_STATS_CACHES.clear()

    async def asyncTearDown(self):
        stats_module._ADMIN_PANEL_STATS_CACHES.clear()
        stats_module._ADMIN_DB_STATS_CACHES.clear()

    def _settings(self):
        return SimpleNamespace(
            ADMIN_PANEL_STATS_CACHE_TTL_SECONDS=15,
            REDIS_URL="redis://redis:6379/0",
            REDIS_KEY_PREFIX="shop",
        )

    def _panel_service(self):
        return SimpleNamespace(
            get_system_stats=AsyncMock(return_value={"users": {"totalUsers": 10}}),
            get_bandwidth_stats=AsyncMock(return_value={"current": 123}),
            get_nodes_statistics=AsyncMock(return_value={"nodes": []}),
            get_nodes_bandwidth_usage=AsyncMock(return_value={"topNodes": []}),
            get_nodes_online_lookups=AsyncMock(return_value={"byUuid": {}, "byName": {}}),
        )

    async def test_admin_panel_stats_are_cached_between_requests(self):
        settings = self._settings()
        panel_service = self._panel_service()
        cache_store = {}

        async def fake_get(_settings, key):
            return cache_store.get(key)

        async def fake_set(_settings, key, value, ttl):
            cache_store[key] = value

        with (
            patch("bot.infra.redis.cache_get_json", fake_get),
            patch("bot.infra.redis.cache_set_json", fake_set),
        ):
            first = await stats_module._load_admin_panel_stats(None, settings, panel_service)
            second = await stats_module._load_admin_panel_stats(None, settings, panel_service)

        self.assertEqual(first, second)
        panel_service.get_system_stats.assert_awaited_once()
        panel_service.get_bandwidth_stats.assert_awaited_once()
        panel_service.get_nodes_statistics.assert_awaited_once()
        panel_service.get_nodes_bandwidth_usage.assert_awaited_once()
        panel_service.get_nodes_online_lookups.assert_awaited_once()


class AdminDbStatsCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        stats_module._ADMIN_DB_STATS_CACHES.clear()

    async def asyncTearDown(self):
        stats_module._ADMIN_DB_STATS_CACHES.clear()

    def _settings(self):
        return SimpleNamespace(
            ADMIN_DB_STATS_CACHE_TTL_SECONDS=15,
            REDIS_URL="redis://redis:6379/0",
            REDIS_KEY_PREFIX="shop",
        )

    class _SessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def test_admin_db_stats_are_cached_between_requests(self):
        settings = self._settings()
        cache_store = {}

        async def fake_get(_settings, key):
            return cache_store.get(key)

        async def fake_set(_settings, key, value, ttl):
            cache_store[key] = value

        user_stats = AsyncMock(
            return_value={
                "total_users": 10,
                "banned_users": 1,
                "active_today": 2,
                "active_subscriptions": 8,
                "paid_subscriptions": 7,
                "trial_users": 1,
                "free_subscription_users": 0,
                "inactive_users": 2,
                "expired_subscription_users": 1,
                "referral_users": 3,
            }
        )
        financial_stats = AsyncMock(
            return_value={
                "today_revenue": 1.0,
                "week_revenue": 2.0,
                "month_revenue": 3.0,
                "all_time_revenue": 4.0,
                "today_payments_count": 1,
                "daily_series": [],
            }
        )
        sync_status = AsyncMock(
            return_value=SimpleNamespace(
                status="success",
                last_sync_time=None,
                details=None,
                users_processed_from_panel=10,
                subscriptions_synced=7,
            )
        )
        recent_payments = AsyncMock(
            return_value=[
                SimpleNamespace(
                    payment_id=1,
                    user_id=10,
                    provider="test",
                    provider_payment_id="provider-1",
                    amount=123.45,
                    currency="RUB",
                    status="succeeded",
                    description="Test payment",
                    subscription_duration_months=1,
                    sale_mode=None,
                    tariff_key=None,
                    purchased_gb=None,
                    purchased_hwid_devices=None,
                    created_at=None,
                )
            ]
        )

        with (
            patch("bot.infra.redis.cache_get_json", fake_get),
            patch("bot.infra.redis.cache_set_json", fake_set),
            patch.object(stats_module.user_dal, "get_enhanced_user_statistics", user_stats),
            patch.object(stats_module.payment_dal, "get_financial_statistics", financial_stats),
            patch.object(stats_module.panel_sync_dal, "get_panel_sync_status", sync_status),
            patch.object(
                stats_module.payment_dal,
                "get_recent_payment_logs_with_user",
                recent_payments,
            ),
        ):
            first = await stats_module._load_admin_db_stats(settings, self._SessionFactory())
            second = await stats_module._load_admin_db_stats(settings, self._SessionFactory())

        self.assertEqual(first, second)
        self.assertEqual(first["recent_payments"][0]["payment_id"], 1)
        user_stats.assert_awaited_once()
        financial_stats.assert_awaited_once()
        sync_status.assert_awaited_once()
        recent_payments.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
