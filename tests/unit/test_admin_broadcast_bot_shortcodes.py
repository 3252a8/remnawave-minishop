import unittest
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from aiogram import Bot, types

from bot.handlers.admin import broadcast_shortcodes as helper
from bot.services.broadcast_personalization import BroadcastUserContext
from bot.utils import MessageContent
from tests.support.settings_stub import settings_stub


class MessageHtmlExtractionTest(unittest.TestCase):
    def test_prefers_html_text_for_text_messages(self):
        message = SimpleNamespace(html_text="<b>Hi</b> {first_name}")
        content = MessageContent("text", text="Hi {first_name}")

        self.assertEqual(
            helper.message_content_html_text(cast(types.Message, message), content),
            "<b>Hi</b> {first_name}",
        )

    def test_prefers_html_caption_for_media_messages(self):
        message = SimpleNamespace(html_caption="<i>Photo</i> {first_name}", html_text="")
        content = MessageContent("photo", file_id="file-id", text="Photo {first_name}")

        self.assertEqual(
            helper.message_content_html_text(cast(types.Message, message), content),
            "<i>Photo</i> {first_name}",
        )


class BotShortcodeHelperTest(unittest.IsolatedAsyncioTestCase):
    async def test_bot_username_is_lazy(self):
        bot = SimpleNamespace(get_me=AsyncMock())

        username = await helper.bot_username_for_shortcodes(cast(Bot, bot), {"first_name"})

        self.assertEqual(username, "")
        bot.get_me.assert_not_awaited()

    async def test_bot_username_resolved_for_referral_link(self):
        bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="demo_bot")))

        username = await helper.bot_username_for_shortcodes(
            cast(Bot, bot),
            {"referral_bot_link"},
        )

        self.assertEqual(username, "demo_bot")
        bot.get_me.assert_awaited_once()

    async def test_context_loader_uses_panel_only_for_config_link(self):
        settings = settings_stub()
        load = AsyncMock(return_value={})

        with patch.object(helper, "load_broadcast_contexts", load):
            await helper.load_admin_broadcast_contexts(
                cast(Any, object()),
                settings,
                [1],
                {"first_name"},
            )

        self.assertIsNone(load.await_args.args[4])

    async def test_context_loader_opens_panel_for_config_link(self):
        settings = settings_stub()
        load = AsyncMock(
            return_value={1: BroadcastUserContext(user_id=1, config_link="happ://crypt4/x")}
        )

        class _Panel:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc: object) -> bool:
                return False

        with (
            patch.object(helper, "load_broadcast_contexts", load),
            patch.object(helper, "PanelApiService", return_value=_Panel()) as panel_factory,
        ):
            result = await helper.load_admin_broadcast_contexts(
                cast(Any, object()),
                settings,
                [1],
                {"config_link"},
            )

        panel_factory.assert_called_once_with(settings)
        self.assertIs(load.await_args.args[4], panel_factory.return_value)
        self.assertIn(1, result)


if __name__ == "__main__":
    unittest.main()
