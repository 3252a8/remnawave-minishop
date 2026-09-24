import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.middlewares import registration_invite as registration_invite_module
from bot.middlewares.registration_invite import RegistrationInviteMiddleware


class I18nStub:
    def gettext(self, language: str, key: str, **kwargs: object) -> str:
        return f"{language}:{key}"


class RegistrationInviteMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self, *, enabled: bool = True, admin_ids: list[int] | None = None):
        return SimpleNamespace(
            REGISTRATION_INVITE_ONLY_ENABLED=enabled,
            ADMIN_IDS=admin_ids or [],
            DEFAULT_LANGUAGE="en",
        )

    def _data(self, *, user_id: int = 42):
        return {
            "event_from_user": SimpleNamespace(id=user_id),
            "session": AsyncMock(),
            "bot_username": "shop_bot",
            "i18n_data": {
                "current_language": "ru",
                "i18n_instance": I18nStub(),
            },
        }

    async def test_disabled_gate_passes_without_user_lookup(self):
        middleware = RegistrationInviteMiddleware(self._settings(enabled=False), I18nStub())
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace(
            message=SimpleNamespace(text="/tg", answer=AsyncMock()),
            callback_query=None,
            inline_query=None,
        )

        with patch.object(
            registration_invite_module.user_dal,
            "get_user_by_telegram_id",
            AsyncMock(),
        ) as lookup:
            result = await middleware(handler, event, self._data())

        self.assertEqual(result, "ok")
        lookup.assert_not_awaited()

    async def test_start_command_reaches_invitation_validation_flow(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace(
            message=SimpleNamespace(text="/start@shop_bot ref_uABC123XYZ", answer=AsyncMock()),
            callback_query=None,
            inline_query=None,
        )

        with patch.object(
            registration_invite_module.user_dal,
            "get_user_by_telegram_id",
            AsyncMock(),
        ) as lookup:
            result = await middleware(handler, event, self._data())

        self.assertEqual(result, "ok")
        lookup.assert_not_awaited()

    async def test_start_command_for_another_bot_does_not_bypass_gate(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        message = SimpleNamespace(text="/start@other_bot ref_uABC123XYZ", answer=AsyncMock())
        event = SimpleNamespace(message=message, callback_query=None, inline_query=None)

        with (
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=None),
            ),
        ):
            result = await middleware(handler, event, self._data())

        self.assertIsNone(result)
        handler.assert_not_awaited()
        message.answer.assert_awaited_once_with("ru:registration_invite_required")

    async def test_similar_command_does_not_bypass_gate(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        message = SimpleNamespace(text="/starter", answer=AsyncMock())
        event = SimpleNamespace(message=message, callback_query=None, inline_query=None)

        with (
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=None),
            ),
        ):
            result = await middleware(handler, event, self._data())

        self.assertIsNone(result)
        handler.assert_not_awaited()
        message.answer.assert_awaited_once_with("ru:registration_invite_required")

    async def test_existing_telegram_link_passes(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace(
            message=SimpleNamespace(text="/tg", answer=AsyncMock()),
            callback_query=None,
            inline_query=None,
        )
        data = self._data()

        with patch.object(
            registration_invite_module.user_dal,
            "get_user_by_telegram_id",
            AsyncMock(return_value=SimpleNamespace(user_id=-7, telegram_id=42)),
        ):
            result = await middleware(handler, event, data)

        self.assertEqual(result, "ok")
        handler.assert_awaited_once_with(event, data)

    async def test_matching_internal_id_does_not_bypass_invite(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace(
            message=SimpleNamespace(text="/language", answer=AsyncMock()),
            callback_query=None,
            inline_query=None,
        )
        data = self._data()

        with (
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=SimpleNamespace(user_id=42)),
            ),
        ):
            result = await middleware(handler, event, data)

        self.assertIsNone(result)
        handler.assert_not_awaited()

    async def test_legacy_admin_id_does_not_bypass_invite(self):
        middleware = RegistrationInviteMiddleware(
            self._settings(admin_ids=[42]),
            I18nStub(),
        )
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace(
            message=SimpleNamespace(text="/admin", answer=AsyncMock()),
            callback_query=None,
            inline_query=None,
        )

        with patch.object(
            registration_invite_module.user_dal,
            "get_user_by_telegram_id",
            AsyncMock(return_value=None),
        ) as lookup:
            result = await middleware(handler, event, self._data())

        self.assertIsNone(result)
        lookup.assert_awaited_once()
        handler.assert_not_awaited()

    async def test_unregistered_tg_command_is_blocked(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        message = SimpleNamespace(text="/tg", answer=AsyncMock())
        event = SimpleNamespace(message=message, callback_query=None, inline_query=None)

        with (
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=None),
            ),
        ):
            result = await middleware(handler, event, self._data())

        self.assertIsNone(result)
        handler.assert_not_awaited()
        message.answer.assert_awaited_once_with("ru:registration_invite_required")

    async def test_unregistered_callback_is_blocked_with_alert(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        callback = SimpleNamespace(answer=AsyncMock())
        event = SimpleNamespace(message=None, callback_query=callback, inline_query=None)

        with (
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=None),
            ),
        ):
            result = await middleware(handler, event, self._data())

        self.assertIsNone(result)
        handler.assert_not_awaited()
        callback.answer.assert_awaited_once_with(
            "ru:registration_invite_required",
            show_alert=True,
        )

    async def test_unregistered_inline_query_returns_no_results(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        inline_query = SimpleNamespace(answer=AsyncMock())
        event = SimpleNamespace(message=None, callback_query=None, inline_query=inline_query)

        with (
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                registration_invite_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=None),
            ),
        ):
            result = await middleware(handler, event, self._data())

        self.assertIsNone(result)
        handler.assert_not_awaited()
        inline_query.answer.assert_awaited_once_with(
            results=[],
            cache_time=1,
            is_personal=True,
        )

    async def test_database_error_fails_closed(self):
        middleware = RegistrationInviteMiddleware(self._settings(), I18nStub())
        handler = AsyncMock(return_value="ok")
        message = SimpleNamespace(text="/tg", answer=AsyncMock())
        event = SimpleNamespace(message=message, callback_query=None, inline_query=None)

        with patch.object(
            registration_invite_module.user_dal,
            "get_user_by_telegram_id",
            AsyncMock(side_effect=RuntimeError("db unavailable")),
        ):
            result = await middleware(handler, event, self._data())

        self.assertIsNone(result)
        handler.assert_not_awaited()
        message.answer.assert_awaited_once_with("ru:registration_invite_required")


if __name__ == "__main__":
    unittest.main()
