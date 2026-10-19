"""Paid renewal preserves entitlement when replacing a deleted panel profile."""

import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.utils.date_utils import add_months
from db.base import Base
from db.dal.subscription_dal import deactivate_other_active_subscriptions
from db.models import Subscription, User
from tests.unit.test_subscription_service_behavior import (
    _configure_persisted_panel_echo,
    _make_service,
    _make_settings,
    _tariffs_config_payload,
)


class DeletedPanelActivationTests(IsolatedAsyncioTestCase):
    async def test_replacement_keeps_remaining_period_and_retires_only_after_confirmation(self):
        for confirmed in (True, False):
            with self.subTest(confirmed=confirmed), tempfile.TemporaryDirectory() as tmpdir:
                service = _make_service(_make_settings(_tariffs_config_payload(), tmpdir))
                service._record_payment_context = AsyncMock()
                service._send_payment_success_email = AsyncMock()
                service._get_or_create_panel_user_link_details = AsyncMock(
                    return_value=("new-panel-user", "new-panel-sub", "new-short", True)
                )
                service.deactivate_panel_managed_internal_overrides = AsyncMock(return_value=0)
                service.build_effective_panel_squad_fields = AsyncMock(return_value={})
                _configure_persisted_panel_echo(service)
                if not confirmed:
                    service._apply_paid_panel_entitlement = AsyncMock(return_value=None)
                now = datetime.now(UTC)
                current_sub = SimpleNamespace(
                    subscription_id=10,
                    panel_user_uuid="deleted-profile",
                    start_date=now - timedelta(days=30),
                    end_date=now + timedelta(days=10),
                    tariff_key="standard",
                    provider="platega",
                    tier_baseline_bytes=100 * 1024**3,
                    topup_balance_bytes=12345,
                    premium_baseline_bytes=25 * 1024**3,
                    extra_hwid_devices=0,
                )
                user = SimpleNamespace(
                    user_id=42,
                    panel_user_uuid="deleted-profile",
                    telegram_id=42,
                    username="client",
                    email=None,
                    language_code="en",
                )
                session = AsyncMock()
                retire = AsyncMock()
                upsert = AsyncMock(return_value=SimpleNamespace(subscription_id=11))
                targets = {
                    "user_dal.get_user_by_id": AsyncMock(return_value=user),
                    "payment_dal.get_payment_by_db_id": AsyncMock(return_value=None),
                    "subscription_dal.get_active_subscription_by_user_id": AsyncMock(
                        return_value=current_sub
                    ),
                    "subscription_dal.deactivate_other_active_subscriptions": retire,
                    "subscription_dal.upsert_subscription": upsert,
                    "tariff_dal.get_hwid_device_entitlement_summary": AsyncMock(
                        return_value={"active_devices": 0, "active_until": None}
                    ),
                }
                with ExitStack() as stack:
                    for target, mock in targets.items():
                        stack.enter_context(
                            patch(
                                "bot.services.subscription_service_impl.lifecycle_activation."
                                + target,
                                mock,
                            )
                        )
                    stack.enter_context(
                        patch(
                            "bot.services.subscription_service_impl.traffic.tariff_dal."
                            "get_active_flexible_traffic_limits",
                            AsyncMock(return_value={}),
                        )
                    )
                    stack.enter_context(
                        patch(
                            "bot.services.tariff_worker_shared.tariff_dal."
                            "get_flexible_traffic_limit_history_start",
                            AsyncMock(return_value=None),
                        )
                    )
                    result = await service.activate_subscription(
                        session=session,
                        user_id=42,
                        months=6,
                        payment_amount=900,
                        payment_db_id=99,
                        provider="platega",
                        sale_mode="subscription@standard",
                    )
                payload = upsert.await_args.args[1]
                self.assertEqual(payload["end_date"], add_months(current_sub.end_date, 6))
                self.assertEqual(payload["topup_balance_bytes"], 12345)
                self.assertEqual(payload["panel_user_uuid"], "new-panel-user")
                if confirmed:
                    self.assertIsNotNone(result)
                    retire.assert_any_await(session, "deleted-profile", None, user_id=42)
                else:
                    self.assertIsNone(result)
                    self.assertEqual(retire.await_count, 1)
                    retire.assert_awaited_once_with(session, "new-panel-user", "new-panel-sub")

    async def test_retirement_preserves_history_and_other_accounts(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add_all([User(user_id=42), User(user_id=43)])
            rows = [
                Subscription(
                    user_id=owner,
                    panel_user_uuid=reference,
                    panel_subscription_uuid=f"sub-{index}",
                    end_date=datetime(2099, 1, 1, tzinfo=UTC),
                    is_active=True,
                )
                for index, (owner, reference) in enumerate(
                    ((42, "deleted-profile"), (42, "new-panel-user"), (43, "deleted-profile"))
                )
            ]
            session.add_all(rows)
            await session.flush()
            await deactivate_other_active_subscriptions(
                session, "deleted-profile", None, user_id=42
            )
            for row in rows:
                await session.refresh(row)
            self.assertEqual([row.is_active for row in rows], [False, True, True])
            self.assertEqual(len((await session.scalars(select(Subscription))).all()), 3)
