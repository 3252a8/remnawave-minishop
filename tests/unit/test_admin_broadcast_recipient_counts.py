"""Planned broadcast totals persist before the worker prepares any deliveries."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.app.web.admin_api_impl import broadcast as broadcast_routes
from bot.services.admin_broadcast_delivery import AdminBroadcastDeliveryService
from db.base import Base
from db.broadcast_models import AdminBroadcast, AdminBroadcastDelivery
from db.dal import broadcast_dal
from db.models import User


class BroadcastRecipientCountTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(self.engine.dispose)
        async with self.engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.create_all,
                tables=[User.__table__, AdminBroadcast.__table__, AdminBroadcastDelivery.__table__],
            )
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            session.add_all(
                [
                    User(user_id=1, telegram_id=101, email="one@example.test"),
                    User(user_id=2, telegram_id=202),
                    User(user_id=3, notification_email="three@example.test"),
                    User(
                        user_id=4,
                        telegram_id=404,
                        telegram_notifications_status="blocked",
                        email="four@example.test",
                    ),
                    User(user_id=5, telegram_id=505, email="five@example.test", is_banned=True),
                    User(
                        user_id=6,
                        telegram_id=606,
                        email="six@example.test",
                        marketing_notifications_telegram_enabled=False,
                        marketing_notifications_email_enabled=False,
                    ),
                    User(user_id=7),
                ]
            )
            await session.commit()

    async def _create(
        self,
        *,
        scheduled: bool = True,
        channels: list[str] | None = None,
        exclude_blocked: bool = True,
        user_ids: list[int] | None = None,
    ) -> AdminBroadcast:
        async with self.factory() as session:
            return await broadcast_dal.create_broadcast(
                session,
                actor_id=99,
                target="all",
                user_ids=user_ids if user_ids is not None else [1, 2, 3, 4, 5, 6, 7, 1, 3, 999],
                channels=channels if channels is not None else ["telegram", "email"],
                exclude_blocked_telegram=exclude_blocked,
                texts={"en": "Hello"},
                email_subjects={},
                buttons=[],
                scheduled_at=datetime.now(UTC) + timedelta(hours=1 if scheduled else -1),
            )

    async def test_queued_and_scheduled_history_has_totals_before_delivery_preparation(
        self,
    ) -> None:
        for scheduled in (False, True):
            with self.subTest(scheduled=scheduled):
                item = await self._create(scheduled=scheduled)
                self.assertEqual(item.status, "scheduled" if scheduled else "queued")
                self.assertEqual(item.recipient_count, 4)
                self.assertEqual(item.total_deliveries, 5)
        request = cast(Any, SimpleNamespace(app={"async_session_factory": self.factory}))
        with patch.object(broadcast_routes, "_require_admin_user_id", return_value=99):
            response = await broadcast_routes.admin_broadcasts_list_route(request)
        history = json.loads(response.text)["broadcasts"]
        self.assertEqual(len(history), 2)
        for item in history:
            self.assertEqual(item["recipient_count"], 4)
            self.assertEqual(item["total_deliveries"], 5)
            self.assertEqual(item["successful_deliveries"], 0)
            self.assertEqual(item["failed_deliveries"], 0)
        async with self.factory() as session:
            self.assertEqual(
                await session.scalar(select(func.count(AdminBroadcastDelivery.delivery_id))), 0
            )

    async def test_only_selected_channels_contribute_to_totals(self) -> None:
        for channel, expected in (("telegram", 2), ("email", 3)):
            with self.subTest(channel=channel):
                item = await self._create(channels=[channel])
                self.assertEqual(item.recipient_count, expected)
                self.assertEqual(item.total_deliveries, expected)

    async def test_blocked_telegram_filter_does_not_remove_email_delivery(self) -> None:
        item = await self._create(exclude_blocked=False)
        self.assertEqual(item.recipient_count, 4)
        self.assertEqual(item.total_deliveries, 6)

    async def test_empty_audience_has_zero_totals(self) -> None:
        item = await self._create(user_ids=[])
        self.assertEqual(item.recipient_count, 0)
        self.assertEqual(item.total_deliveries, 0)

    async def test_worker_replaces_planned_totals_with_current_audience(self) -> None:
        item = await self._create()
        audience = SimpleNamespace(resolve_user_ids=AsyncMock(return_value=[2]))
        service = AdminBroadcastDeliveryService(
            settings=cast(Any, object()),
            session_factory=cast(Any, self.factory),
            i18n=cast(Any, object()),
            audience_service=cast(Any, audience),
            queue_manager=cast(Any, object()),
            bot_username=None,
        )
        with (
            patch.object(broadcast_dal, "begin_broadcast", AsyncMock(return_value=item)),
            patch.object(service, "_queue_deliveries", AsyncMock()),
        ):
            await service.dispatch(int(item.broadcast_id))
        audience.resolve_user_ids.assert_awaited_once_with("all")
        async with self.factory() as session:
            actual = await broadcast_dal.get_broadcast(session, int(item.broadcast_id))
            self.assertIsNotNone(actual)
            assert actual is not None
            self.assertEqual(actual.recipient_count, 1)
            self.assertEqual(actual.total_deliveries, 1)
