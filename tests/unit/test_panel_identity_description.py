import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.subscription_service_impl.panel_identity import PanelIdentityMixin
from db.base import Base
from db.dal.subscription_panel_identity_dal import relink_panel_subscriptions
from db.models import (
    Subscription,
    SubscriptionLifecycleNotification,
    SubscriptionNotification,
    User,
)


def test_subscription_panel_identity_payload_excludes_description_updates():
    user = SimpleNamespace(
        email="linked@example.com",
        username="alice",
        first_name="Alice",
        last_name="Smith",
        telegram_id=42,
        user_id=42,
        minishop_id="ms_1234567890abcdef1234567890abcdef",
        panel_username=None,
    )

    payload = PanelIdentityMixin()._panel_identity_payload_for_user(user)

    assert "description" not in payload
    assert payload["email"] == "linked@example.com"
    assert payload["telegramId"] == 42


def test_subscription_panel_description_filters_broken_lines_for_creation():
    user = SimpleNamespace(
        minishop_id="ms_1234567890abcdef1234567890abcdef",
        panel_username=None,
        email="linked@example.com",
        username="alice??",
        first_name="????",
        last_name="Smith",
        telegram_id=42,
        user_id=42,
    )

    assert PanelIdentityMixin()._panel_description_for_user(user) == "alice??\nSmith"


def test_panel_identity_does_not_duplicate_user_after_inconclusive_upgrade_lookup():
    mixin = PanelIdentityMixin()
    mixin.settings = SimpleNamespace(
        user_traffic_limit_bytes=0,
        USER_TRAFFIC_STRATEGY="NO_RESET",
        parsed_user_squad_uuids=[],
        parsed_user_external_squad_uuid=None,
    )
    mixin.panel_service = SimpleNamespace(
        get_users_by_filter=AsyncMock(return_value=None),
        get_user_by_uuid_lookup=AsyncMock(
            return_value={
                "ok": False,
                "user": None,
                "not_found": False,
                "failure_reason": "classification=incompatible_user_reference",
            }
        ),
        create_panel_user=AsyncMock(),
    )
    db_user = SimpleNamespace(
        user_id=42,
        telegram_id=42,
        email=None,
        panel_user_uuid="legacy-user-uuid",
        minishop_id="ms_1234567890abcdef1234567890abcdef",
        panel_username=None,
        referral_code=None,
    )

    link = asyncio.run(mixin._get_or_create_panel_user_link(AsyncMock(), 42, db_user))

    assert link.panel_user_uuid == "legacy-user-uuid"
    assert link.panel_user is None
    mixin.panel_service.create_panel_user.assert_not_awaited()


class PanelSubscriptionRelinkTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(self.engine.dispose)
        async with self.engine.begin() as connection:
            await connection.execute(text("PRAGMA foreign_keys=ON"))
            await connection.run_sync(Base.metadata.create_all)
        self.session = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.addAsyncCleanup(self.session.close)
        self.user = User(
            user_id=42,
            telegram_id=42,
            panel_user_uuid="legacy-user-uuid",
        )
        self.sub = Subscription(
            subscription_id=314,
            user_id=42,
            panel_user_uuid="legacy-user-uuid",
            panel_subscription_uuid="legacy-subscription",
            end_date=datetime(2099, 10, 6, tzinfo=UTC),
            start_date=datetime(2026, 6, 1, tzinfo=UTC),
            tariff_key="saved-plan",
            auto_renew_enabled=False,
            topup_balance_bytes=123456,
        )
        self.history = Subscription(
            subscription_id=313,
            user_id=42,
            panel_user_uuid="legacy-user-uuid",
            panel_subscription_uuid="historical-subscription",
            end_date=datetime(2026, 6, 1, tzinfo=UTC),
            is_active=False,
        )
        self.unrelated = Subscription(
            subscription_id=315,
            user_id=42,
            panel_user_uuid="other-panel-account",
            panel_subscription_uuid="other-subscription",
            end_date=self.sub.end_date,
        )
        self.other_user = Subscription(
            subscription_id=316,
            user_id=43,
            panel_user_uuid="legacy-user-uuid",
            end_date=self.sub.end_date,
        )
        self.session.add_all(
            [self.user, User(user_id=43), self.sub, self.history, self.unrelated, self.other_user]
        )
        await self.session.flush()
        self.session.add_all(
            [
                SubscriptionNotification(
                    subscription_id=314, notification_key="before_1d:telegram"
                ),
                SubscriptionLifecycleNotification(
                    subscription_id=314,
                    notification_key="before_1d:telegram",
                    period_end_date=self.sub.end_date,
                ),
            ]
        )
        await self.session.commit()
        self.panel_user = {
            "uuid": "42",
            "subscriptionUuid": "current-subscription",
            "shortUuid": "current-short",
            "telegramId": 42,
            "username": self.user.minishop_id,
        }

    async def _reconcile(self):
        mixin = PanelIdentityMixin()
        mixin.settings = SimpleNamespace(
            user_traffic_limit_bytes=0,
            USER_TRAFFIC_STRATEGY="NO_RESET",
            parsed_user_squad_uuids=[],
            parsed_user_external_squad_uuid=None,
        )
        mixin.panel_service = SimpleNamespace(
            get_user_by_uuid_lookup=AsyncMock(return_value={"ok": False}),
            get_users_by_filter=AsyncMock(return_value=[self.panel_user]),
            create_panel_user=AsyncMock(),
        )
        link = await mixin._get_or_create_panel_user_link(self.session, 42, self.user)
        await self.session.commit()
        mixin.panel_service.create_panel_user.assert_not_awaited()
        return link

    async def test_upgrade_preserves_rows_fields_and_both_notification_histories(self):
        await self.session.refresh(self.sub)
        before = {
            column.key: getattr(self.sub, column.key)
            for column in Subscription.__table__.columns
            if column.key not in {"panel_user_uuid", "panel_subscription_uuid"}
        }
        link = await self._reconcile()
        self.assertTrue(link.local_link_updated_now)
        self.assertEqual(self.user.panel_user_uuid, "42")
        self.assertEqual(self.sub.panel_user_uuid, "42")
        self.assertEqual(self.sub.panel_subscription_uuid, "current-subscription")
        self.assertEqual(self.history.panel_user_uuid, "42")
        self.assertEqual(self.history.panel_subscription_uuid, "historical-subscription")
        self.assertEqual(self.unrelated.panel_user_uuid, "other-panel-account")
        self.assertEqual(self.other_user.panel_user_uuid, "legacy-user-uuid")
        await self.session.refresh(self.sub)
        self.assertEqual(before, {key: getattr(self.sub, key) for key in before})
        for model in (SubscriptionNotification, SubscriptionLifecycleNotification):
            markers = list((await self.session.scalars(select(model))).all())
            self.assertEqual([marker.subscription_id for marker in markers], [314])
        self.assertEqual(
            set((await self.session.scalars(select(Subscription.subscription_id))).all()),
            {313, 314, 315, 316},
        )

    async def test_expired_subscription_and_short_uuid_are_relinked_in_place(self):
        self.sub.is_active = False
        self.sub.end_date = datetime(2026, 9, 1, tzinfo=UTC)
        del self.panel_user["subscriptionUuid"]
        self.panel_user["uuid"] = "new-user-uuid"
        await self._reconcile()
        self.assertEqual(self.sub.panel_user_uuid, "new-user-uuid")
        self.assertEqual(self.sub.panel_subscription_uuid, "current-short")
        self.assertFalse(self.sub.is_active)
        self.assertEqual(self.sub.subscription_id, 314)

    async def test_existing_current_link_is_reused_without_a_unique_conflict(self):
        self.history.panel_subscription_uuid = "current-subscription"
        await self._reconcile()
        self.assertEqual(self.history.panel_subscription_uuid, "current-subscription")
        self.assertEqual(self.sub.panel_subscription_uuid, "legacy-subscription")
        self.assertEqual(self.history.panel_user_uuid, "42")

    async def test_conflicting_subscription_owner_is_rejected_before_changes(self):
        self.other_user.panel_subscription_uuid = "current-subscription"
        await self.session.commit()
        with self.assertRaisesRegex(ValueError, "another account"):
            await relink_panel_subscriptions(
                self.session,
                user_id=42,
                old_panel_user_uuid="legacy-user-uuid",
                new_panel_user_uuid="42",
                panel_subscription_uuid="current-subscription",
            )
        self.assertEqual(self.sub.panel_user_uuid, "legacy-user-uuid")
        self.assertEqual(self.history.panel_user_uuid, "legacy-user-uuid")

    async def test_relink_is_idempotent_and_does_not_create_missing_rows(self):
        await self._reconcile()
        for old_reference in ("legacy-user-uuid", "42", "missing-reference"):
            with self.subTest(reference=old_reference):
                self.assertEqual(
                    await relink_panel_subscriptions(
                        self.session,
                        user_id=42,
                        old_panel_user_uuid=old_reference,
                        new_panel_user_uuid="42",
                        panel_subscription_uuid="current-subscription",
                    ),
                    0,
                )
