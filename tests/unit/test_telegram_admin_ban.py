import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.admin import user_management_list_card as cards
from bot.handlers.admin import user_management_state as users
from bot.handlers.admin import user_management_subscription as bans


class TelegramAdminBanTests(unittest.IsolatedAsyncioTestCase):
    async def test_banned_list_page_opens_card_with_return_to_same_page(self):
        banned = [
            SimpleNamespace(user_id=number, first_name="Demo", minishop_id=f"ms_{number}")
            for number in (1, 2, 3)
        ]
        for user in banned:
            user.username = None
            user.email = None
            user.telegram_id = None
            user.referred_by_id = None
        message = SimpleNamespace(edit_text=AsyncMock())
        callback = SimpleNamespace(
            data="admin_action:view_banned:1", message=message, answer=AsyncMock()
        )
        i18n_data = {"i18n_instance": SimpleNamespace(gettext=lambda lang, key, **kwargs: key)}
        settings = SimpleNamespace(DEFAULT_LANGUAGE="ru", LOGS_PAGE_SIZE=1)
        session = SimpleNamespace()
        with (
            patch.object(users.user_dal, "get_banned_users", AsyncMock(return_value=banned)),
            patch.object(users, "callback_message", return_value=message),
        ):
            await users.view_banned_users_handler(
                callback, SimpleNamespace(), i18n_data, settings, session
            )

        markup = message.edit_text.await_args.kwargs["reply_markup"]
        callback.data = markup.inline_keyboard[0][0].callback_data
        self.assertEqual(callback.data, "admin_user_card:2:1")
        callback.answer.assert_awaited_once()

        with (
            patch.object(cards.user_dal, "get_user_by_id", AsyncMock(return_value=banned[1])),
            patch.object(cards, "callback_message", return_value=message),
            patch.object(cards, "_resolve_bot_username", AsyncMock(return_value="demo_bot")),
            patch.object(cards, "format_user_card", AsyncMock(return_value="Card")),
            patch.object(cards, "_send_with_profile_link_fallback", AsyncMock()) as render,
            patch("bot.services.referral_service.ReferralService"),
        ):
            await cards.user_card_from_list_handler(
                callback,
                SimpleNamespace(),
                i18n_data,
                settings,
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
                session,
            )

        buttons = [
            button for row in render.await_args.kwargs["markup"].inline_keyboard for button in row
        ]
        self.assertIn(
            ("user_card_back_to_banned_list_button", "admin_action:view_banned:1"),
            [(button.text, button.callback_data) for button in buttons],
        )

    async def test_checks_account_identity_before_mutating_database_or_panel(self):
        for banned, allowed in ((False, False), (False, True), (True, False)):
            with self.subTest(banned=banned, allowed=allowed):
                user = SimpleNamespace(user_id=42, is_banned=banned, panel_user_uuid="panel")
                callback = SimpleNamespace(from_user=SimpleNamespace(id=1001), answer=AsyncMock())
                session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
                panel = SimpleNamespace(update_user_status_on_panel=AsyncMock())
                i18n = SimpleNamespace(gettext=lambda lang, key, **kwargs: key)
                with (
                    patch.object(
                        bans, "can_ban_account", AsyncMock(return_value=allowed)
                    ) as policy,
                    patch.object(
                        bans, "require_telegram_account_id", AsyncMock(return_value=71)
                    ) as identity,
                    patch.object(bans.user_dal, "update_user", AsyncMock()) as update,
                    patch.object(bans, "handle_refresh_user_card", AsyncMock()),
                ):
                    await bans.handle_toggle_ban(
                        callback,
                        user,
                        panel,
                        SimpleNamespace(),
                        session,
                        SimpleNamespace(),
                        i18n,
                        "ru",
                    )
                    if banned:
                        policy.assert_not_awaited()
                        identity.assert_not_awaited()
                    else:
                        identity.assert_awaited_once_with(session, 1001)
                        policy.assert_awaited_once_with(session, 71, 42)
                    if not banned and not allowed:
                        update.assert_not_awaited()
                        panel.update_user_status_on_panel.assert_not_awaited()
                        session.commit.assert_not_awaited()
                        session.rollback.assert_awaited_once()
                        self.assertFalse(user.is_banned)
                    else:
                        update.assert_awaited_once_with(session, 42, {"is_banned": not banned})
                        panel.update_user_status_on_panel.assert_awaited_once_with("panel", banned)
                        session.commit.assert_awaited_once()
