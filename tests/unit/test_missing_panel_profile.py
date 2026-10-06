import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.services.subscription_service_impl.panel_identity import (
    PanelIdentityMixin,
    PanelUserCreateOptions,
)


class MissingPanelProfileTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mixin = PanelIdentityMixin()
        self.mixin.settings = SimpleNamespace(tariffs_config=None)
        self.user = SimpleNamespace(
            user_id=42,
            minishop_id="ms_1234567890abcdef1234567890abcdef",
            panel_username="tg_42",
            panel_user_uuid="deleted-panel-user",
            telegram_id=42,
            email="client@example.test",
            username="client",
            first_name="Client",
            last_name=None,
            managed_panel_tariff_tag=None,
        )
        self.panel_user = {
            "uuid": "new-panel-user",
            "username": self.user.minishop_id,
            "telegramId": 42,
            "email": self.user.email,
            "shortUuid": "new-subscription-link",
            "tag": "PERIOD_PLAN",
        }
        self.panel = SimpleNamespace(
            get_user_by_uuid_lookup=AsyncMock(return_value={"ok": False, "not_found": True}),
            get_users_by_filter=AsyncMock(return_value=[]),
            create_panel_user=AsyncMock(return_value={"response": self.panel_user}),
        )
        self.mixin.panel_service = self.panel
        self.mixin._notify_admin_panel_user_creation_failed = AsyncMock()
        self.session = AsyncMock()
        self.expiry = datetime(2026, 11, 6, tzinfo=UTC)
        self.options = PanelUserCreateOptions(
            30, 1000, "NO_RESET", expire_at=self.expiry, tag="period-plan"
        )
        self.update_user = AsyncMock()
        self.relink_subscriptions = AsyncMock()
        for target, mock in (
            ("user_dal.get_user_by_panel_uuid", AsyncMock(return_value=None)),
            ("user_dal.update_user", self.update_user),
            ("user_panel_squad_override_dal.merge_panel_user_uuid", AsyncMock(return_value=0)),
            (
                "subscription_panel_identity_dal.relink_panel_subscriptions",
                self.relink_subscriptions,
            ),
        ):
            patcher = patch(f"bot.services.subscription_service_impl.panel_identity.{target}", mock)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def link(self):
        return await self.mixin._get_or_create_panel_user_link(
            self.session, 42, self.user, create_options=self.options
        )

    async def test_confirmed_missing_profile_is_created_once_with_purchase_terms(self):
        link = await self.link()
        self.assertTrue(link.panel_user_created_now)
        self.assertTrue(link.local_link_updated_now)
        self.assertEqual(link.panel_user_uuid, "new-panel-user")
        self.assertEqual(link.panel_subscription_uuid, "new-subscription-link")
        creation = self.panel.create_panel_user.await_args.kwargs
        self.assertEqual(creation["expire_at"], self.expiry)
        self.assertEqual(creation["default_traffic_limit_bytes"], 1000)
        self.assertEqual(creation["tag"], "PERIOD_PLAN")
        self.assertEqual(creation["telegram_id"], 42)
        self.assertEqual(creation["email"], self.user.email)
        self.update_user.assert_awaited_once_with(
            self.session, 42, {"panel_user_uuid": "new-panel-user"}
        )
        self.relink_subscriptions.assert_not_awaited()
        self.panel.get_user_by_uuid_lookup.return_value = {"ok": True, "user": self.panel_user}
        second = await self.link()
        self.assertFalse(second.panel_user_created_now)
        self.panel.create_panel_user.assert_awaited_once()

    async def test_unknown_uuid_failure_and_incompatible_reference_never_create(self):
        self.panel.get_user_by_uuid_lookup.return_value = {"ok": False, "not_found": False}
        link = await self.link()
        self.assertIsNone(link.panel_user)
        self.panel.create_panel_user.assert_not_awaited()
        self.update_user.assert_not_awaited()
        self.assertEqual(self.user.panel_user_uuid, "deleted-panel-user")

    async def test_any_failed_identity_search_blocks_replacement(self):
        for failed_filter in ("tg_42", "telegram_id", "email", self.user.minishop_id):
            with self.subTest(failed_filter=failed_filter):

                async def search(marker=failed_filter, **filters):
                    if marker in filters or filters.get("username") == marker:
                        return None
                    return []

                self.panel.get_users_by_filter.side_effect = search
                link = await self.link()
                self.assertIsNone(link.panel_user)
                self.panel.create_panel_user.assert_not_awaited()
                self.update_user.assert_not_awaited()

    async def test_existing_telegram_profile_is_reused_without_local_uuid(self):
        self.user.panel_user_uuid = None
        self.panel.get_users_by_filter.side_effect = lambda **filters: (
            [self.panel_user] if "telegram_id" in filters else []
        )
        link = await self.link()
        self.assertEqual(link.panel_user_uuid, "new-panel-user")
        self.assertFalse(link.panel_user_created_now)
        self.panel.create_panel_user.assert_not_awaited()

    async def test_failed_creation_keeps_old_link_and_notifies_admin(self):
        self.panel.create_panel_user.return_value = {"error": True}
        link = await self.link()
        self.assertIsNone(link.panel_user)
        self.update_user.assert_not_awaited()
        self.assertEqual(self.user.panel_user_uuid, "deleted-panel-user")
        self.mixin._notify_admin_panel_user_creation_failed.assert_awaited_once_with(
            self.session, 42
        )
