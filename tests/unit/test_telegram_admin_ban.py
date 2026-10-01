import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.admin import user_management_subscription as bans


class TelegramAdminBanTests(unittest.IsolatedAsyncioTestCase):
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
