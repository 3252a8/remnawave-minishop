import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.admin import common as admin_common
from bot.handlers.admin import sync_admin as sync_module
from bot.handlers.admin import sync_admin_commands


class _I18n:
    def gettext(self, _lang, key, **kwargs):
        if kwargs:
            return f"{key}:{kwargs}"
        return key


def _settings():
    return SimpleNamespace(DEFAULT_LANGUAGE="ru")


class AdminBotSyncQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_command_enqueues_panel_sync_instead_of_running_inline(self):
        enqueued = []

        async def fake_enqueue(settings, provider, payload, *, event_id=None):
            enqueued.append((settings, provider, payload, event_id))
            return True

        message = SimpleNamespace(
            from_user=SimpleNamespace(id=42),
            chat=SimpleNamespace(id=100500),
            answer=AsyncMock(),
        )
        i18n_data = {"current_language": "ru", "i18n_instance": _I18n()}

        with (
            patch.object(sync_admin_commands, "enqueue_webhook_event", fake_enqueue),
            patch.object(sync_admin_commands, "perform_sync", AsyncMock()) as perform_sync,
        ):
            await sync_module.sync_command_handler(
                message_event=message,
                bot=AsyncMock(),
                settings=_settings(),
                i18n_data=i18n_data,
                panel_service=AsyncMock(),
                session=AsyncMock(),
            )

        perform_sync.assert_not_awaited()
        message.answer.assert_awaited_once_with("sync_started_simple")
        self.assertEqual(len(enqueued), 1)
        _, provider, payload, event_id = enqueued[0]
        self.assertEqual(provider, "panel_sync")
        self.assertIsNone(event_id)
        self.assertEqual(
            payload,
            {
                "source": "bot_admin",
                "requested_by": 42,
                "target_chat_id": 100500,
                "language": "ru",
            },
        )

    async def test_admin_sync_button_delegates_to_sync_handler_without_second_answer(self):
        callback = SimpleNamespace(
            data="admin_action:sync_panel",
            from_user=SimpleNamespace(id=42),
            message=SimpleNamespace(chat=SimpleNamespace(id=100500)),
            answer=AsyncMock(),
        )

        with patch.object(
            admin_common.admin_sync_handlers,
            "sync_command_handler",
            AsyncMock(),
        ) as sync_command:
            await admin_common.admin_panel_actions_callback_handler(
                callback=callback,
                state=AsyncMock(),
                settings=_settings(),
                i18n_data={"current_language": "ru", "i18n_instance": _I18n()},
                bot=AsyncMock(),
                panel_service=AsyncMock(),
                subscription_service=AsyncMock(),
                session=AsyncMock(),
            )

        sync_command.assert_awaited_once()
        callback.answer.assert_not_awaited()
