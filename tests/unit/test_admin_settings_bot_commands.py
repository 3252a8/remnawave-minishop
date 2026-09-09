import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import settings as settings_api


class AdminSettingsBotCommandsTests(unittest.IsolatedAsyncioTestCase):
    async def test_patch_reports_command_sync_failure_as_not_applied(self):
        request = SimpleNamespace()
        runtime_settings = SimpleNamespace(TELEGRAM_BOT_MENU_DISABLED=True)
        body = SimpleNamespace(
            updates={"TELEGRAM_BOT_MENU_DISABLED": True},
            deletes=[],
        )

        with (
            patch.object(settings_api, "_require_admin_user_id", return_value=42),
            patch.object(settings_api, "get_settings", return_value=runtime_settings),
            patch.object(settings_api, "get_session_factory", return_value=object()),
            patch.object(settings_api, "parse_body_or_400", AsyncMock(return_value=body)),
            patch.object(
                settings_api,
                "update_overrides",
                AsyncMock(
                    return_value={
                        "ok": True,
                        "applied": 1,
                        "reverted": 0,
                        "not_applied": [],
                    }
                ),
            ),
            patch.object(
                settings_api,
                "refresh_webapp_runtime_after_settings_change",
                AsyncMock(),
            ),
            patch.object(
                settings_api,
                "_sync_bot_commands_after_settings_change",
                AsyncMock(return_value="TELEGRAM_BOT_MENU_DISABLED"),
            ),
        ):
            response = await settings_api.admin_settings_patch_route(request)

        payload = json.loads(response.text)
        self.assertEqual(payload["not_applied"], ["TELEGRAM_BOT_MENU_DISABLED"])

    async def test_bot_menu_change_syncs_commands_immediately(self):
        bot = object()
        settings = SimpleNamespace(TELEGRAM_BOT_MENU_DISABLED=True)
        request = SimpleNamespace(app={"bot": bot})

        with patch.object(
            settings_api,
            "sync_telegram_bot_commands",
            AsyncMock(),
        ) as sync_mock:
            failed_key = await settings_api._sync_bot_commands_after_settings_change(
                request,
                settings,
                updates={"TELEGRAM_BOT_MENU_DISABLED": True},
                deletes=[],
            )

        self.assertIsNone(failed_key)
        sync_mock.assert_awaited_once_with(bot, settings)

    async def test_resetting_bot_menu_setting_syncs_commands_immediately(self):
        bot = object()
        settings = SimpleNamespace(TELEGRAM_BOT_MENU_DISABLED=False)
        request = SimpleNamespace(app={"bot": bot})

        with patch.object(
            settings_api,
            "sync_telegram_bot_commands",
            AsyncMock(),
        ) as sync_mock:
            failed_key = await settings_api._sync_bot_commands_after_settings_change(
                request,
                settings,
                updates={},
                deletes=["TELEGRAM_BOT_MENU_DISABLED"],
            )

        self.assertIsNone(failed_key)
        sync_mock.assert_awaited_once_with(bot, settings)

    async def test_unrelated_setting_does_not_sync_commands(self):
        settings = SimpleNamespace()
        request = SimpleNamespace(app={})

        with patch.object(
            settings_api,
            "sync_telegram_bot_commands",
            AsyncMock(),
        ) as sync_mock:
            failed_key = await settings_api._sync_bot_commands_after_settings_change(
                request,
                settings,
                updates={"DEFAULT_LANGUAGE": "en"},
                deletes=[],
            )

        self.assertIsNone(failed_key)
        sync_mock.assert_not_awaited()

    async def test_sync_failure_marks_setting_for_restart(self):
        settings = SimpleNamespace(TELEGRAM_BOT_MENU_DISABLED=True)
        request = SimpleNamespace(app={"bot": object()})

        with patch.object(
            settings_api,
            "sync_telegram_bot_commands",
            AsyncMock(side_effect=RuntimeError("Telegram unavailable")),
        ):
            failed_key = await settings_api._sync_bot_commands_after_settings_change(
                request,
                settings,
                updates={"TELEGRAM_BOT_MENU_DISABLED": True},
                deletes=[],
            )

        self.assertEqual(failed_key, "TELEGRAM_BOT_MENU_DISABLED")
