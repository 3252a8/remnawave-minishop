import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Delete, Update

from db.dal import user_dal


class FakeResult:
    def __init__(self, scalar_value=None, rowcount=1):
        self._scalar_value = scalar_value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar_value

    def scalars(self):
        return self

    def all(self):
        if self._scalar_value is None:
            return []
        if isinstance(self._scalar_value, list):
            return self._scalar_value
        return [self._scalar_value]


class UserDalMergeTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_user_ids_without_active_subscription_uses_left_join_null_check(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=FakeResult([2, 3])),
        )

        result = await user_dal.get_user_ids_without_active_subscription(session)

        self.assertEqual(result, [2, 3])
        stmt = session.execute.await_args.args[0]
        sql = str(
            stmt.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).upper()
        self.assertIn("LEFT OUTER JOIN", sql)
        self.assertIn("IS NULL", sql)

    async def test_merge_users_uses_bulk_updates_for_related_tables(self):
        source = SimpleNamespace(
            user_id=1,
            email="source@example.com",
            telegram_id=111,
            panel_user_uuid="panel-source",
            email_verified_at=datetime.now(timezone.utc),
            username="source-user",
            first_name="Source",
            last_name="User",
            language_code="ru",
            telegram_photo_url="https://example.com/source.jpg",
            channel_subscription_verified=True,
            channel_subscription_checked_at=datetime.now(timezone.utc),
            channel_subscription_verified_for=1,
            lifetime_used_traffic_bytes=512,
            referred_by_id=999,
            referral_code="SRC123",
        )
        target = SimpleNamespace(
            user_id=2,
            email=None,
            telegram_id=None,
            panel_user_uuid=None,
            email_verified_at=None,
            username=None,
            first_name=None,
            last_name=None,
            language_code=None,
            telegram_photo_url=None,
            channel_subscription_verified=False,
            channel_subscription_checked_at=None,
            channel_subscription_verified_for=None,
            lifetime_used_traffic_bytes=128,
            referred_by_id=None,
            referral_code=None,
        )
        session = SimpleNamespace(
            execute=AsyncMock(side_effect=lambda stmt: FakeResult()),
            delete=AsyncMock(),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        )

        async def fake_get_user_by_id(_session, user_id):
            if user_id == source.user_id:
                return source
            if user_id == target.user_id:
                return target
            return None

        with (
            patch("db.dal.user_dal.get_user_by_id", side_effect=fake_get_user_by_id),
            patch("db.dal.user_dal._get_active_subscription_for_user", return_value=None),
            patch("db.dal.user_dal._get_latest_subscription_for_user", return_value=None),
        ):
            merged = await user_dal.merge_users(
                session,
                source_user_id=source.user_id,
                target_user_id=target.user_id,
            )

        self.assertIs(merged, target)

        update_tables = []
        delete_tables = []
        for call in session.execute.await_args_list:
            stmt = call.args[0]
            if isinstance(stmt, Update):
                update_tables.append(stmt.table.name)
            elif isinstance(stmt, Delete):
                delete_tables.append(stmt.table.name)

        self.assertIn("user_billing", update_tables)
        self.assertIn("ad_attributions", update_tables)
        self.assertIn("subscriptions", update_tables)
        self.assertIn("payments", update_tables)
        self.assertIn("promo_code_activations", update_tables)
        self.assertIn("user_payment_methods", update_tables)
        self.assertIn("message_logs", update_tables)
        self.assertIn("users", update_tables)
        self.assertIn("user_payment_methods", delete_tables)
        self.assertIn("promo_code_activations", delete_tables)
        session.delete.assert_awaited_once_with(source)

    async def test_merge_users_moves_active_email_subscription_onto_expired_telegram_account(self):
        before = datetime.now(timezone.utc)
        source = SimpleNamespace(
            user_id=-100,
            email="paid@example.com",
            telegram_id=None,
            panel_user_uuid="panel-email",
            email_verified_at=before,
            username=None,
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
            channel_subscription_verified=False,
            channel_subscription_checked_at=None,
            channel_subscription_verified_for=None,
            lifetime_used_traffic_bytes=0,
            referred_by_id=None,
            referral_code=None,
        )
        target = SimpleNamespace(
            user_id=42,
            email=None,
            telegram_id=42,
            panel_user_uuid="panel-telegram",
            email_verified_at=None,
            username="old",
            first_name=None,
            last_name=None,
            language_code="ru",
            telegram_photo_url=None,
            channel_subscription_verified=False,
            channel_subscription_checked_at=None,
            channel_subscription_verified_for=None,
            lifetime_used_traffic_bytes=0,
            referred_by_id=None,
            referral_code=None,
        )
        source_active_sub = SimpleNamespace(
            end_date=before + timedelta(days=30),
            is_active=True,
            skip_notifications=False,
            last_notification_sent=before,
            status_from_panel="ACTIVE",
            panel_user_uuid="panel-email",
        )
        expired_target_sub = SimpleNamespace(
            end_date=before - timedelta(days=3),
            is_active=False,
            skip_notifications=False,
            last_notification_sent=before,
            status_from_panel="EXPIRED",
            panel_user_uuid="panel-telegram",
        )
        session = SimpleNamespace(
            execute=AsyncMock(side_effect=lambda stmt: FakeResult()),
            delete=AsyncMock(),
            flush=AsyncMock(),
            refresh=AsyncMock(),
        )

        async def fake_get_user_by_id(_session, user_id):
            if user_id == source.user_id:
                return source
            if user_id == target.user_id:
                return target
            return None

        async def fake_get_active_subscription(_session, user_id, panel_user_uuid=None):
            if user_id == source.user_id and panel_user_uuid == source.panel_user_uuid:
                return source_active_sub
            return None

        async def fake_get_latest_subscription(_session, user_id, panel_user_uuid=None, **_kwargs):
            if user_id == target.user_id and panel_user_uuid == target.panel_user_uuid:
                return expired_target_sub
            return None

        with (
            patch("db.dal.user_dal.get_user_by_id", side_effect=fake_get_user_by_id),
            patch(
                "db.dal.user_dal._get_active_subscription_for_user",
                side_effect=fake_get_active_subscription,
            ),
            patch(
                "db.dal.user_dal._get_latest_subscription_for_user",
                side_effect=fake_get_latest_subscription,
            ),
        ):
            merged = await user_dal.merge_users(
                session,
                source_user_id=source.user_id,
                target_user_id=target.user_id,
            )

        self.assertIs(merged, target)
        self.assertEqual(target.email, "paid@example.com")
        self.assertTrue(expired_target_sub.is_active)
        self.assertEqual(expired_target_sub.status_from_panel, "ACTIVE_EXTENDED_BY_MERGE")
        self.assertIsNone(expired_target_sub.last_notification_sent)
        self.assertGreater(expired_target_sub.end_date, before + timedelta(days=29))
        self.assertLess(expired_target_sub.end_date, before + timedelta(days=31))
        self.assertFalse(source_active_sub.is_active)
        self.assertTrue(source_active_sub.skip_notifications)
        self.assertEqual(source_active_sub.status_from_panel, "MERGED_INTO_ACCOUNT")
