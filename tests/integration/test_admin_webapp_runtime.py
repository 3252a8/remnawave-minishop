import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import webapp_runtime
from bot.app.web.webapp import cache_helpers


class AdminWebappRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_resets_settings_cache_and_invalidates_user_payloads(self):
        settings = SimpleNamespace()
        request = SimpleNamespace(
            app={
                "settings": settings,
                "webapp_settings_cache": {"ts": 123.0, "data": {"stale": True}},
                "subscription_guides_config_cache": {
                    "fingerprint": ("stale",),
                    "status": {"enabled": True},
                },
            }
        )

        with patch.object(
            cache_helpers,
            "invalidate_all_webapp_user_payloads",
            AsyncMock(),
        ) as invalidate_mock:
            await webapp_runtime.refresh_webapp_runtime_after_settings_change(
                request,
                updates={"SUBSCRIPTION_GUIDES_ENABLED": True},
                deletes=[],
            )

        self.assertEqual(request.app["webapp_settings_cache"], {"ts": 0.0, "data": {}})
        self.assertEqual(
            request.app["subscription_guides_config_cache"],
            {"fingerprint": None, "status": None},
        )
        invalidate_mock.assert_awaited_once_with(settings, include_devices=False)

    async def test_refresh_clears_logo_cache_for_appearance_settings(self):
        settings = SimpleNamespace()
        request = SimpleNamespace(
            app={
                "settings": settings,
                "webapp_settings_cache": {"ts": 123.0, "data": {"stale": True}},
                "webapp_logo_cache": ("url", b"body", "image/png"),
            }
        )

        with (
            patch.object(
                cache_helpers,
                "invalidate_all_webapp_user_payloads",
                AsyncMock(),
            ),
            patch("bot.app.web.admin_api_impl.themes.prune_unused_appearance_assets") as prune_mock,
        ):
            await webapp_runtime.refresh_webapp_runtime_after_settings_change(
                request,
                updates={"WEBAPP_LOGO_URL": "/webapp-uploaded-logo/logo.png"},
                deletes=[],
            )

        self.assertIsNone(request.app["webapp_logo_cache"])
        prune_mock.assert_called_once_with(
            settings,
            extra_keep_urls=["/webapp-uploaded-logo/logo.png"],
        )
