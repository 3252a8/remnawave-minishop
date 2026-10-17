"""Destructive cleanup must prove eligibility and preserve trial-use history."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services import account_cleanup_worker as worker_module
from bot.services.account_cleanup_worker import AccountCleanupWorker
from bot.services.panel_activity import panel_user_is_confirmed_unused
from config.settings import Settings
from config.settings_trial import TrialSettings
from db.auth_models import AccountRole
from db.base import Base
from db.cleaned_trial_models import AccountCleanupIntent
from db.dal import account_cleanup_dal, subscription_dal
from db.models import Payment, Subscription, User


class AccountCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = Settings(
            _env_file=None,
            BOT_TOKEN="123456:TEST",
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            ADMIN_IDS="99",
            PANEL_WRITE_MODE="live",
            UNUSED_ACCOUNTS_CLEANUP_ENABLED=True,
            UNUSED_ACCOUNTS_NO_TRIAL_ENABLED=True,
            UNUSED_ACCOUNTS_UNUSED_TRIAL_ENABLED=True,
        )
        self.now = datetime.now(UTC)
        self.panel = AsyncMock()
        self.panel.get_user_by_uuid_lookup.return_value = {
            "ok": True,
            "not_found": False,
            "user": {"firstConnectedAt": None, "userTraffic": {"lifetimeUsedTrafficBytes": 0}},
        }
        self.panel.delete_user_from_panel.return_value = True
        self.worker = AccountCleanupWorker(self.settings, self.factory, self.panel)
        self.invalidations = [
            patch.object(worker_module, "invalidate_webapp_user_caches", AsyncMock()),
            patch.object(worker_module, "cache_delete_pattern", AsyncMock()),
        ]
        for invalidation in self.invalidations:
            invalidation.start()

    async def asyncTearDown(self) -> None:
        for invalidation in self.invalidations:
            invalidation.stop()
        await self.engine.dispose()

    async def add_account(self, user_id: int = 42, *, trial: bool = False) -> None:
        async with self.factory() as session:
            session.add(
                User(
                    user_id=user_id,
                    telegram_id=user_id,
                    registration_date=self.now - timedelta(days=60),
                    panel_user_uuid=str(user_id) if trial else None,
                )
            )
            if trial:
                session.add(
                    Subscription(
                        user_id=user_id,
                        panel_user_uuid=str(user_id),
                        provider="trial",
                        start_date=self.now - timedelta(days=40),
                        end_date=self.now - timedelta(days=37),
                        is_active=False,
                        traffic_used_bytes=0,
                    )
                )
            await session.commit()

    async def candidates(self) -> list[int]:
        async with self.factory() as session:
            return [
                int(value)
                for value in await account_cleanup_dal.cleanup_candidate_ids(
                    session, self.settings, self.now, 0
                )
            ]

    def test_cleanup_is_disabled_by_default(self) -> None:
        settings = TrialSettings(_env_file=None)
        self.assertFalse(settings.UNUSED_ACCOUNTS_CLEANUP_ENABLED)
        self.assertFalse(settings.UNUSED_ACCOUNTS_NO_TRIAL_ENABLED)
        self.assertFalse(settings.UNUSED_ACCOUNTS_UNUSED_TRIAL_ENABLED)

    async def test_admin_and_payment_history_are_protected(self) -> None:
        await self.add_account(99)
        await self.add_account(42)
        await self.add_account(110)
        async with self.factory() as session:
            session.add(AccountRole(user_id=110, role="owner"))
            session.add(
                Payment(user_id=42, amount=100, currency="RUB", status="pending", provider="qa")
            )
            await session.commit()
        self.assertEqual(await self.candidates(), [])

    async def test_expired_never_connected_trial_is_deleted_and_cannot_be_reused(self) -> None:
        await self.add_account(trial=True)
        self.assertEqual(await self.candidates(), [42])
        self.assertTrue(await self.worker.cleanup_user(42))
        self.panel.delete_user_from_panel.assert_awaited_once_with("42", log_response=False)
        async with self.factory() as session:
            self.assertIsNone(await session.get(User, 42))
            session.add(User(user_id=84, telegram_id=42))
            await session.commit()
            self.assertTrue(
                await subscription_dal.has_trial_blocking_subscription_for_user(session, 84)
            )

    async def test_no_trial_account_does_not_consume_first_trial(self) -> None:
        await self.add_account()
        self.assertTrue(await self.worker.cleanup_user(42))
        self.panel.delete_user_from_panel.assert_not_awaited()
        async with self.factory() as session:
            self.assertFalse(await account_cleanup_dal.has_cleaned_trial(session, 42))

    async def test_unknown_panel_state_and_panel_error_preserve_local_user(self) -> None:
        await self.add_account(trial=True)
        self.panel.get_user_by_uuid_lookup.return_value = {"ok": False, "not_found": False}
        self.assertFalse(await self.worker.cleanup_user(42))
        self.panel.delete_user_from_panel.assert_not_awaited()
        self.panel.get_user_by_uuid_lookup.return_value = {
            "ok": True,
            "user": {"firstConnectedAt": None},
            "not_found": False,
        }
        self.panel.delete_user_from_panel.return_value = False
        self.assertFalse(await self.worker.cleanup_user(42))
        async with self.factory() as session:
            self.assertIsNotNone(await session.get(User, 42))

    async def test_connection_even_without_traffic_protects_account(self) -> None:
        await self.add_account(trial=True)
        self.panel.get_user_by_uuid_lookup.return_value = {
            "ok": True,
            "user": {"firstConnectedAt": self.now.isoformat()},
        }
        self.assertFalse(await self.worker.cleanup_user(42))
        self.panel.delete_user_from_panel.assert_not_awaited()

    async def test_durable_intent_resumes_after_remote_deletion(self) -> None:
        await self.add_account(trial=True)
        async with self.factory() as session:
            user = await session.get(User, 42)
            assert user is not None
            session.add(
                AccountCleanupIntent(
                    account_id=str(user.__dict__["account_id"]),
                    panel_uuids=json.dumps(["42"]),
                    started_at=self.now,
                )
            )
            await session.commit()
        self.panel.get_user_by_uuid_lookup.return_value = {"ok": False, "not_found": True}
        self.panel.delete_user_from_panel.return_value = False
        self.assertTrue(await self.worker.cleanup_user(42))

    async def test_disabled_master_and_dry_run_do_not_delete(self) -> None:
        await self.add_account()
        self.settings.UNUSED_ACCOUNTS_CLEANUP_ENABLED = False
        self.assertFalse(await self.worker.cleanup_user(42))
        self.settings.UNUSED_ACCOUNTS_CLEANUP_ENABLED = True
        self.settings.PANEL_WRITE_MODE = "dry_run"
        self.assertFalse(await self.worker.cleanup_user(42))

    def test_uncertain_or_reset_panel_history_never_authorizes_deletion(self) -> None:
        cases = [
            {"onlineAt": None, "usedTrafficBytes": 0},
            {"firstConnectedAt": None},
            {"firstConnectedAt": "invalid", "lifetimeUsedTrafficBytes": 0},
            {"firstConnectedAt": None, "lifetimeUsedTrafficBytes": None},
            {"firstConnectedAt": None, "lifetimeUsedTrafficBytes": -1},
            {"firstConnectedAt": None, "lifetimeUsedTrafficBytes": 3},
            {
                "firstConnectedAt": None,
                "lifetimeUsedTrafficBytes": 0,
                "expireAt": (self.now + timedelta(days=1)).isoformat(),
            },
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertFalse(panel_user_is_confirmed_unused(case, self.now))

    async def test_recent_live_paid_and_locally_used_trials_are_protected(self) -> None:
        cases: list[dict[str, datetime | str | int]] = [
            {"start_date": self.now - timedelta(days=1)},
            {"end_date": self.now + timedelta(days=1)},
            {"provider": "qa"},
            {"last_connected_at": self.now - timedelta(days=20)},
            {"traffic_used_bytes": 100},
            {"premium_used_bytes": 100},
        ]
        for user_id, changes in enumerate(cases, start=110):
            await self.add_account(user_id, trial=True)
            async with self.factory() as session:
                await session.execute(
                    update(Subscription).where(Subscription.user_id == user_id).values(**changes)
                )
                await session.commit()
        self.assertEqual(await self.candidates(), [])
