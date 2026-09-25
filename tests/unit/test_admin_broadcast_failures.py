import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.app.web.admin_api_impl import broadcast as broadcast_routes
from db.broadcast_models import AdminBroadcastDelivery
from db.dal import broadcast_dal


class BroadcastFailureQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_paginates_only_failed_deliveries_for_the_requested_broadcast(self) -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(AdminBroadcastDelivery.__table__.create)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                session.add_all(
                    [
                        AdminBroadcastDelivery(
                            broadcast_id=broadcast_id,
                            user_id=user_id,
                            channel="telegram",
                            destination=str(user_id),
                            status=status,
                            error="blocked" if status == "failed" else None,
                        )
                        for broadcast_id, user_id, status in (
                            (1, 10, "failed"),
                            (1, 11, "sent"),
                            (1, 12, "failed"),
                            (2, 13, "failed"),
                        )
                    ]
                )
                await session.commit()
                total, page = await broadcast_dal.list_failed_deliveries(
                    session, 1, limit=1, offset=1
                )
            self.assertEqual(total, 2)
            self.assertEqual([item.user_id for item in page], [12])
        finally:
            await engine.dispose()


class BroadcastFailureRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_hidden_broadcast_does_not_expose_delivery_errors(self) -> None:
        request = cast(
            Any,
            SimpleNamespace(match_info={"id": "7"}, query={"limit": "50", "offset": "0"}),
        )
        session_factory = MagicMock()
        session_factory.return_value.__aenter__.return_value = object()
        get_broadcast = AsyncMock(return_value=SimpleNamespace(is_visible=False))
        list_failures = AsyncMock()
        with (
            patch.object(broadcast_routes, "_require_admin_user_id", return_value=42),
            patch.object(broadcast_routes, "get_session_factory", return_value=session_factory),
            patch.object(broadcast_routes.broadcast_dal, "get_broadcast", get_broadcast),
            patch.object(broadcast_routes.broadcast_dal, "list_failed_deliveries", list_failures),
        ):
            response = await broadcast_routes.admin_broadcast_failures_route(request)
        self.assertEqual(response.status, 404)
        list_failures.assert_not_awaited()

    async def test_route_returns_bounded_page_without_destination(self) -> None:
        request = cast(
            Any,
            SimpleNamespace(match_info={"id": "7"}, query={"limit": "500", "offset": "2"}),
        )
        session_factory = MagicMock()
        session_factory.return_value.__aenter__.return_value = object()
        failure = SimpleNamespace(
            delivery_id=9,
            user_id=123,
            channel="telegram",
            destination="private@example.test",
            error="Forbidden: bot was blocked by the user",
            finished_at=datetime.now(UTC),
        )
        list_failures = AsyncMock(return_value=(3, [failure]))
        with (
            patch.object(broadcast_routes, "_require_admin_user_id", return_value=42),
            patch.object(broadcast_routes, "get_session_factory", return_value=session_factory),
            patch.object(
                broadcast_routes.broadcast_dal,
                "get_broadcast",
                AsyncMock(return_value=SimpleNamespace(is_visible=True)),
            ),
            patch.object(broadcast_routes.broadcast_dal, "list_failed_deliveries", list_failures),
        ):
            response = await broadcast_routes.admin_broadcast_failures_route(request)
        self.assertEqual(response.status, 200)
        payload = json.loads(response.text)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["failures"][0]["user_id"], 123)
        self.assertNotIn("destination", payload["failures"][0])
        self.assertNotIn("private@example.test", response.text)
        call = list_failures.await_args
        assert call is not None
        self.assertEqual(call.kwargs, {"limit": 100, "offset": 2})
