"""Invitation bonus days shown on the Bonuses tab."""

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.services.referral_service import ReferralService
from db.base import Base
from db.dal import referral_stats_dal
from db.models import Payment, User
from db.referral_accrual_models import ReferralPeriodAccrual

INVITER = 7
INVITEE = 42


class ReceivedInviterBonusDaysTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                text(
                    "CREATE TABLE schema_migrations "
                    "(id VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
                )
            )
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            session.add_all(
                [
                    User(user_id=INVITER),
                    User(user_id=INVITEE, referred_by_id=INVITER),
                    User(user_id=99),
                ]
            )
            await session.commit()
        self.next_payment_id = 100

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _start_ledger(self, applied_at: str = "2026-10-01 12:00:00.000000") -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO schema_migrations (id, applied_at) VALUES (:id, :applied_at)"),
                {"id": referral_stats_dal.LEDGER_MIGRATION_ID, "applied_at": applied_at},
            )

    async def _purchase(
        self,
        created_at: datetime,
        *,
        user_id: int = INVITEE,
        sale_mode: str = "subscription@standard",
        amount: float = 299.0,
        status: str = "succeeded",
    ) -> int:
        self.next_payment_id += 1
        async with self.factory() as session:
            session.add(
                Payment(
                    payment_id=self.next_payment_id,
                    user_id=user_id,
                    amount=amount,
                    currency="RUB",
                    status=status,
                    sale_mode=sale_mode,
                    created_at=created_at,
                    referral_accrual_processed=True,
                )
            )
            await session.commit()
        return self.next_payment_id

    async def _accrual(
        self,
        payment_id: int,
        *,
        user_id: int = INVITER,
        role: str = "inviter",
        days: int = 7,
        state: str = "applied",
    ) -> None:
        async with self.factory() as session:
            session.add(
                ReferralPeriodAccrual(
                    payment_id=payment_id,
                    referee_user_id=INVITEE,
                    user_id=user_id,
                    role=role,
                    days=days,
                    state=state,
                )
            )
            await session.commit()

    async def _received(self, user_id: int = INVITER) -> referral_stats_dal.ReceivedInviterBonus:
        async with self.factory() as session:
            received: referral_stats_dal.ReceivedInviterBonus = (
                await referral_stats_dal.get_received_inviter_bonus(session, user_id)
            )
        return received

    async def test_counts_only_applied_inviter_accruals_of_the_user(self) -> None:
        await self._start_ledger()
        first = await self._purchase(datetime(2026, 10, 2, tzinfo=UTC))
        second = await self._purchase(datetime(2026, 10, 3, tzinfo=UTC))
        elsewhere = await self._purchase(datetime(2026, 10, 4, tzinfo=UTC))
        await self._accrual(first, days=7)
        await self._accrual(second, days=5, state="pending")
        await self._accrual(first, user_id=INVITEE, role="referee", days=3)
        await self._accrual(elsewhere, user_id=99, days=11)

        self.assertEqual(await self._received(), referral_stats_dal.ReceivedInviterBonus(7))

    async def test_is_zero_before_any_bonus_was_received(self) -> None:
        await self._start_ledger()

        self.assertEqual(await self._received(), referral_stats_dal.ReceivedInviterBonus(0))

    async def test_counts_from_the_ledger_start_when_an_invitee_bought_before_it(self) -> None:
        await self._start_ledger()
        await self._purchase(datetime(2026, 9, 20, tzinfo=UTC))
        later = await self._purchase(datetime(2026, 10, 2, tzinfo=UTC))
        await self._accrual(later, days=7)

        received = await self._received()

        self.assertEqual(received.days, 7)
        assert received.since is not None
        self.assertEqual(received.since.replace(tzinfo=UTC), datetime(2026, 10, 1, 12, tzinfo=UTC))

    async def test_refunded_purchase_before_the_ledger_still_marks_the_start(self) -> None:
        await self._start_ledger()
        await self._purchase(datetime(2026, 9, 20, tzinfo=UTC), status="refunded")

        received = await self._received()

        self.assertEqual(received.days, 0)
        self.assertIsNotNone(received.since)

    async def test_purchases_that_never_earn_a_bonus_keep_the_total_known(self) -> None:
        await self._start_ledger()
        before = datetime(2026, 9, 20, tzinfo=UTC)
        await self._purchase(before, sale_mode="balance_topup")
        await self._purchase(before, sale_mode="traffic@standard")
        await self._purchase(before, amount=0)
        await self._purchase(before, status="pending")
        await self._purchase(before, user_id=99)
        later = await self._purchase(datetime(2026, 10, 2, tzinfo=UTC))
        await self._accrual(later, days=7)

        self.assertEqual(await self._received(), referral_stats_dal.ReceivedInviterBonus(7))

    async def test_schema_without_migration_history_has_no_unrecorded_bonuses(self) -> None:
        await self._purchase(datetime(2026, 9, 20, tzinfo=UTC))

        self.assertEqual(await self._received(), referral_stats_dal.ReceivedInviterBonus(0))

    async def test_failed_optional_lookup_rolls_back_only_its_savepoint(self) -> None:
        service = object.__new__(ReferralService)

        async def fail_after_write(
            lookup_session: AsyncSession, user_id: int
        ) -> referral_stats_dal.ReceivedInviterBonus:
            lookup_session.add(User(user_id=124))
            await lookup_session.flush()
            raise RuntimeError("ledger unavailable")

        async with self.factory() as session:
            session.add(User(user_id=123))
            await session.flush()
            with patch.object(
                referral_stats_dal, "get_received_inviter_bonus", side_effect=fail_after_write
            ):
                received = await service._received_bonus(session, INVITER)
            self.assertIsNone(received)
            self.assertIsNone(await session.scalar(select(User.user_id).where(User.user_id == 124)))
            self.assertEqual(
                await session.scalar(select(User.user_id).where(User.user_id == 123)), 123
            )
            await session.commit()
        async with self.factory() as session:
            self.assertEqual(
                await session.scalar(select(User.user_id).where(User.user_id == 123)), 123
            )


if __name__ == "__main__":
    unittest.main()
