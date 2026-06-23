import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest

from bot.handlers.user.start import ensure_required_channel_subscription
from bot.middlewares.channel_subscription import ChannelSubscriptionMiddleware
from bot.utils.channel_subscription import (
    is_required_channel_access_error,
    normalize_required_channel_id,
    normalize_required_channel_link,
)


class I18nStub:
    def gettext(self, _lang, key, **_kwargs):
        return {
            "channel_subscription_required": "subscribe first",
            "channel_subscription_check_failed": "check failed",
        }.get(key, key)


class FakeBot:
    def __init__(self, *, status="member", error=None, chat=None, chat_error=None):
        self.status = status
        self.error = error
        self.chat = chat
        self.chat_error = chat_error
        self.calls = []
        self.get_chat_calls = []

    async def get_chat_member(self, chat_id, user_id):
        self.calls.append((chat_id, user_id))
        if self.error:
            raise self.error
        return SimpleNamespace(status=self.status)

    async def get_chat(self, chat_id):
        self.get_chat_calls.append(chat_id)
        if self.chat_error:
            raise self.chat_error
        return self.chat or SimpleNamespace(username="required_channel")


def _settings(required_channel_id, required_channel_link="https://t.me/example"):
    return SimpleNamespace(
        REQUIRED_CHANNEL_ID=required_channel_id,
        REQUIRED_CHANNEL_LINK=required_channel_link,
        ADMIN_IDS=[],
        DEFAULT_LANGUAGE="en",
    )


def _message_event(bot, user_id=42):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        bot=bot,
        answer=AsyncMock(),
    )


def _db_user(*, verified=False, verified_for=None):
    return SimpleNamespace(
        channel_subscription_verified=verified,
        channel_subscription_verified_for=verified_for,
    )


class RequiredChannelIdNormalizationTests(unittest.TestCase):
    def test_normalizes_raw_channel_ids_to_bot_api_chat_ids(self):
        self.assertEqual(normalize_required_channel_id(1234567890), -1001234567890)
        self.assertEqual(normalize_required_channel_id("1234567890"), -1001234567890)
        self.assertEqual(normalize_required_channel_id(-1234567890), -1001234567890)
        self.assertEqual(normalize_required_channel_id(-1001234567890), -1001234567890)
        self.assertEqual(normalize_required_channel_id(-123456789), -123456789)

    def test_ignores_empty_channel_ids(self):
        self.assertIsNone(normalize_required_channel_id(None))
        self.assertIsNone(normalize_required_channel_id(""))
        self.assertIsNone(normalize_required_channel_id(0))

    def test_normalizes_channel_links_for_join_button(self):
        self.assertEqual(
            normalize_required_channel_link("@required_channel"), "https://t.me/required_channel"
        )
        self.assertEqual(
            normalize_required_channel_link("required_channel"), "https://t.me/required_channel"
        )
        self.assertEqual(
            normalize_required_channel_link("t.me/required_channel"),
            "https://t.me/required_channel",
        )
        self.assertEqual(
            normalize_required_channel_link("https://t.me/required_channel"),
            "https://t.me/required_channel",
        )
        self.assertEqual(normalize_required_channel_link("+inviteHash"), "https://t.me/+inviteHash")
        self.assertIsNone(normalize_required_channel_link("not a valid link"))

    def test_detects_channel_configuration_errors(self):
        self.assertTrue(
            is_required_channel_access_error(
                TelegramBadRequest(method=None, message="Bad Request: chat not found")
            )
        )
        self.assertFalse(
            is_required_channel_access_error(
                TelegramBadRequest(method=None, message="Bad Request: user not found")
            )
        )


class RequiredChannelSubscriptionCheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_uses_normalized_channel_id_and_persists_it(self):
        bot = FakeBot(status="member")
        event = _message_event(bot)
        user = _db_user()

        with patch("bot.handlers.user.start.user_dal.update_user", AsyncMock()) as update_user:
            result = await ensure_required_channel_subscription(
                event,
                _settings(1234567890),
                I18nStub(),
                "en",
                AsyncMock(),
                db_user=user,
            )

        self.assertTrue(result)
        self.assertEqual(bot.calls, [(-1001234567890, 42)])
        payload = update_user.await_args.args[2]
        self.assertTrue(payload["channel_subscription_verified"])
        self.assertEqual(payload["channel_subscription_verified_for"], -1001234567890)

    async def test_channel_access_errors_show_check_failed_without_persisting_false_status(self):
        bot = FakeBot(error=TelegramBadRequest(method=None, message="Bad Request: chat not found"))
        event = _message_event(bot)
        user = _db_user()

        with patch("bot.handlers.user.start.user_dal.update_user", AsyncMock()) as update_user:
            result = await ensure_required_channel_subscription(
                event,
                _settings(1234567890),
                I18nStub(),
                "en",
                AsyncMock(),
                db_user=user,
            )

        self.assertFalse(result)
        event.answer.assert_awaited_once_with("check failed")
        update_user.assert_not_awaited()

    async def test_join_button_prefers_channel_link_resolved_from_required_id(self):
        bot = FakeBot(
            status="left",
            chat=SimpleNamespace(username="required_channel", invite_link=None),
        )
        event = _message_event(bot)
        user = _db_user()

        with patch("bot.handlers.user.start.user_dal.update_user", AsyncMock()):
            result = await ensure_required_channel_subscription(
                event,
                _settings(1234567890, required_channel_link="https://t.me/main_sales_bot"),
                I18nStub(),
                "en",
                AsyncMock(),
                db_user=user,
            )

        self.assertFalse(result)
        self.assertEqual(bot.calls, [(-1001234567890, 42)])
        self.assertEqual(bot.get_chat_calls, [-1001234567890])
        reply_markup = event.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(
            reply_markup.inline_keyboard[0][0].url,
            "https://t.me/required_channel",
        )


class ChannelSubscriptionMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_middleware_accepts_cached_verification_for_normalized_channel_id(self):
        middleware = ChannelSubscriptionMiddleware(_settings(1234567890), I18nStub())
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace(callback_query=None, message=None)
        data = {
            "event_from_user": SimpleNamespace(id=42),
            "session": AsyncMock(),
            "i18n_data": {"current_language": "en", "i18n_instance": I18nStub()},
        }
        user = _db_user(verified=True, verified_for=-1001234567890)

        with patch(
            "bot.middlewares.channel_subscription.user_dal.get_user_by_id",
            AsyncMock(return_value=user),
        ):
            result = await middleware(handler, event, data)

        self.assertEqual(result, "ok")
        handler.assert_awaited_once_with(event, data)

    async def test_middleware_prompt_uses_channel_link_resolved_from_required_id(self):
        middleware = ChannelSubscriptionMiddleware(
            _settings(1234567890, required_channel_link="https://t.me/main_sales_bot"),
            I18nStub(),
        )
        handler = AsyncMock(return_value="ok")
        message = SimpleNamespace(text="menu", answer=AsyncMock())
        event = SimpleNamespace(callback_query=None, message=message)
        bot = FakeBot(
            chat=SimpleNamespace(username="required_channel", invite_link=None),
        )
        data = {
            "bot": bot,
            "event_from_user": SimpleNamespace(id=42),
            "session": AsyncMock(),
            "i18n_data": {"current_language": "en", "i18n_instance": I18nStub()},
        }
        user = _db_user(verified=False, verified_for=None)

        with patch(
            "bot.middlewares.channel_subscription.user_dal.get_user_by_id",
            AsyncMock(return_value=user),
        ):
            result = await middleware(handler, event, data)

        self.assertIsNone(result)
        handler.assert_not_awaited()
        self.assertEqual(bot.get_chat_calls, [-1001234567890])
        reply_markup = message.answer.await_args.kwargs["reply_markup"]
        self.assertEqual(
            reply_markup.inline_keyboard[0][0].url,
            "https://t.me/required_channel",
        )


if __name__ == "__main__":
    unittest.main()
