"""Lifecycle deduplication follows renewed expiry dates in a real SQL database."""

from datetime import UTC, datetime, timedelta
from unittest import IsolatedAsyncioTestCase

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.base import Base
from db.dal import subscription_dal
from db.models import (
    Subscription,
    SubscriptionLifecycleNotification,
    SubscriptionNotification,
    User,
)


class SubscriptionNotificationPeriodTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(self.engine.dispose)
        async with self.engine.begin() as connection:
            await connection.execute(text("PRAGMA foreign_keys=ON"))
            await connection.run_sync(Base.metadata.create_all)
        self.session = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.addAsyncCleanup(self.session.close)
        self.end = datetime(2026, 10, 6, 12, tzinfo=UTC)
        self.sub = Subscription(
            subscription_id=314,
            user_id=42,
            panel_user_uuid="panel-user-test",
            start_date=datetime(2026, 6, 1, tzinfo=UTC),
            period_start_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
            end_date=self.end,
        )
        self.session.add_all([User(user_id=42), self.sub])
        await self.session.commit()

    async def test_june_markers_do_not_block_the_october_period(self):
        keys = (
            "before_3d:telegram",
            "before_2d:telegram",
            "before_1d:telegram",
            "before_3h:telegram",
            "before_2d_autorenew:telegram",
            "expired:telegram",
            "expired_24h_after:telegram",
            "expired:event",
            "expired_24h_after:event",
            "before_1d:email",
            "before_1d",
        )
        self.session.add_all(
            SubscriptionNotification(
                subscription_id=self.sub.subscription_id,
                notification_key=key,
                sent_at=datetime(2026, 6, 20, 12, tzinfo=UTC),
            )
            for key in keys
        )
        await self.session.commit()
        for key in keys:
            with self.subTest(key=key):
                self.assertFalse(
                    await subscription_dal.has_subscription_notification(
                        self.session, self.sub.subscription_id, key
                    )
                )

    async def test_recent_legacy_markers_still_deduplicate_the_current_period(self):
        self.sub.period_start_at = datetime(2026, 10, 1, tzinfo=UTC)
        cases = (
            ("before_3d:telegram", -70),
            ("before_2d_autorenew:telegram", -47),
            ("before_1d:telegram", -23),
            ("before_1d:email", -23),
            ("before_1d", -23),
            ("before_3h:telegram", -2),
            ("expired:telegram", 2),
            ("expired_24h_after:telegram", 25),
            ("expired:event", 2),
            ("expired_24h_after:event", 25),
        )
        self.session.add_all(
            SubscriptionNotification(
                subscription_id=self.sub.subscription_id,
                notification_key=key,
                sent_at=self.end + timedelta(hours=hours),
            )
            for key, hours in cases
        )
        await self.session.commit()
        for key, _ in cases:
            with self.subTest(key=key):
                self.assertTrue(
                    await subscription_dal.has_subscription_notification(
                        self.session, self.sub.subscription_id, key
                    )
                )

    async def test_renewal_reuses_marker_without_changing_the_historical_start(self):
        key = "before_1d:telegram"
        await subscription_dal.record_subscription_notification(
            self.session, self.sub.subscription_id, key, sent_at=self.end - timedelta(hours=23)
        )
        await self.session.commit()
        self.assertTrue(
            await subscription_dal.has_subscription_notification(
                self.session, self.sub.subscription_id, key
            )
        )
        new_end = datetime(2026, 11, 6, 12, tzinfo=UTC)
        await subscription_dal.update_subscription_end_date(
            self.session, self.sub.subscription_id, new_end
        )
        await self.session.commit()
        self.assertFalse(
            await subscription_dal.has_subscription_notification(
                self.session, self.sub.subscription_id, key
            )
        )
        await subscription_dal.record_subscription_notification(
            self.session, self.sub.subscription_id, key, sent_at=new_end - timedelta(hours=23)
        )
        await self.session.commit()
        self.assertTrue(
            await subscription_dal.has_subscription_notification(
                self.session, self.sub.subscription_id, key
            )
        )
        markers = (
            (
                await self.session.execute(
                    select(SubscriptionLifecycleNotification).order_by(
                        SubscriptionLifecycleNotification.period_end_date
                    )
                )
            )
            .scalars()
            .all()
        )
        self.assertEqual(len(markers), 2)
        self.assertEqual(markers[0].period_end_date.replace(tzinfo=UTC), self.end)
        self.assertEqual(markers[1].period_end_date.replace(tzinfo=UTC), new_end)
        self.assertEqual(self.sub.start_date.replace(tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC))

    async def test_a_stale_legacy_marker_is_preserved_without_a_unique_key_conflict(self):
        key = "before_1d:telegram"
        self.session.add(
            SubscriptionNotification(
                subscription_id=self.sub.subscription_id,
                notification_key=key,
                sent_at=datetime(2026, 6, 20, 12, tzinfo=UTC),
            )
        )
        await self.session.commit()
        await subscription_dal.record_subscription_notification(
            self.session, self.sub.subscription_id, key, sent_at=self.end - timedelta(hours=23)
        )
        await self.session.commit()
        count = await self.session.scalar(
            select(func.count()).select_from(SubscriptionNotification)
        )
        self.assertEqual(count, 1)
        legacy = await self.session.scalar(select(SubscriptionNotification))
        self.assertEqual(legacy.sent_at.replace(tzinfo=UTC), datetime(2026, 6, 20, 12, tzinfo=UTC))
        marker = await self.session.scalar(select(SubscriptionLifecycleNotification))
        self.assertEqual(marker.period_end_date.replace(tzinfo=UTC), self.end)
        self.assertTrue(
            await subscription_dal.has_subscription_notification(
                self.session, self.sub.subscription_id, key
            )
        )

    async def test_shortened_expiry_is_a_different_notification_period(self):
        key = "before_1d:email"
        await subscription_dal.record_subscription_notification(
            self.session, self.sub.subscription_id, key, sent_at=self.end - timedelta(hours=23)
        )
        await self.session.commit()
        self.sub.end_date = self.end - timedelta(hours=1)
        await self.session.commit()
        self.assertFalse(
            await subscription_dal.has_subscription_notification(
                self.session, self.sub.subscription_id, key
            )
        )

    async def test_traffic_period_reset_does_not_resend_a_lifecycle_notification(self):
        key = "before_1d:telegram"
        await subscription_dal.record_subscription_notification(
            self.session, self.sub.subscription_id, key, sent_at=self.end - timedelta(hours=23)
        )
        await self.session.commit()
        self.sub.period_start_at = self.end - timedelta(hours=1)
        await self.session.commit()
        self.assertTrue(
            await subscription_dal.has_subscription_notification(
                self.session, self.sub.subscription_id, key
            )
        )

    async def test_a_traffic_reset_does_not_invalidate_a_current_legacy_marker(self):
        key = "before_1d:telegram"
        self.session.add(
            SubscriptionNotification(
                subscription_id=self.sub.subscription_id,
                notification_key=key,
                sent_at=self.end - timedelta(hours=23),
            )
        )
        self.sub.period_start_at = self.end - timedelta(hours=1)
        await self.session.commit()
        self.assertTrue(
            await subscription_dal.has_subscription_notification(
                self.session, self.sub.subscription_id, key
            )
        )
        self.assertEqual(
            await self.session.scalar(
                select(func.count()).select_from(SubscriptionLifecycleNotification)
            ),
            1,
        )

    async def test_device_fingerprints_keep_their_existing_deduplication(self):
        key = "hwid_device_added:telegram:opaque-device-fingerprint"
        self.session.add(
            SubscriptionNotification(
                subscription_id=self.sub.subscription_id,
                notification_key=key,
                sent_at=datetime(2026, 6, 20, 12, tzinfo=UTC),
            )
        )
        await self.session.commit()
        self.assertTrue(
            await subscription_dal.has_subscription_notification(
                self.session, self.sub.subscription_id, key
            )
        )

    async def test_deleting_a_subscription_cascades_its_period_markers(self):
        await subscription_dal.record_subscription_notification(
            self.session, self.sub.subscription_id, "expired:event", sent_at=self.end
        )
        await self.session.commit()
        self.assertEqual(
            await self.session.scalar(
                select(func.count()).select_from(SubscriptionLifecycleNotification)
            ),
            1,
        )
        await self.session.execute(
            delete(Subscription).where(Subscription.subscription_id == self.sub.subscription_id)
        )
        await self.session.commit()
        self.assertEqual(
            await self.session.scalar(
                select(func.count()).select_from(SubscriptionLifecycleNotification)
            ),
            0,
        )
