"""Trial eligibility for users who received the referral welcome bonus."""

import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.base import Base
from db.dal import subscription_dal
from db.models import Subscription, User

INVITEE = 42
INVITER = 7


class TrialEligibilityAfterWelcomeBonusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.now = datetime.now(UTC)
        self.claimed_at = self.now - timedelta(days=10)
        self.next_subscription = 0
        async with self.factory() as session:
            session.add_all(
                [
                    User(user_id=INVITER),
                    User(
                        user_id=INVITEE,
                        referred_by_id=INVITER,
                        referral_welcome_bonus_claimed_at=self.claimed_at,
                    ),
                ]
            )
            await session.commit()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _subscription(
        self,
        *,
        start: datetime,
        end: datetime,
        provider: str | None,
        is_active: bool,
        user_id: int = INVITEE,
    ) -> None:
        self.next_subscription += 1
        async with self.factory() as session:
            session.add(
                Subscription(
                    user_id=user_id,
                    panel_user_uuid=f"panel-user-{user_id}",
                    panel_subscription_uuid=f"panel-sub-{self.next_subscription}",
                    start_date=start,
                    end_date=end,
                    is_active=is_active,
                    status_from_panel="ACTIVE" if is_active else "EXPIRED",
                    provider=provider,
                )
            )
            await session.commit()

    async def _blocks_trial(self, user_id: int = INVITEE) -> bool:
        async with self.factory() as session:
            blocked = await subscription_dal.has_trial_blocking_subscription_for_user(
                session, user_id
            )
        return bool(blocked)

    async def _ended_welcome_bonus(self, *, provider: str | None = "referral") -> None:
        welcome_start = self.claimed_at - timedelta(seconds=1)
        await self._subscription(
            start=welcome_start,
            end=welcome_start + timedelta(days=3),
            provider=provider,
            is_active=False,
        )

    async def test_active_welcome_bonus_still_blocks_trial(self) -> None:
        claimed_at = self.now - timedelta(days=1)
        async with self.factory() as session:
            invitee = await session.get(User, INVITEE)
            assert invitee is not None
            invitee.referral_welcome_bonus_claimed_at = claimed_at
            await session.commit()
        await self._subscription(
            start=claimed_at - timedelta(seconds=1),
            end=self.now + timedelta(days=2),
            provider="referral",
            is_active=True,
        )

        self.assertTrue(await self._blocks_trial())

    async def test_ended_welcome_bonus_no_longer_blocks_trial(self) -> None:
        await self._ended_welcome_bonus()

        self.assertFalse(await self._blocks_trial())

    async def test_purchase_on_welcome_subscription_keeps_blocking_trial(self) -> None:
        await self._ended_welcome_bonus(provider="yookassa")

        self.assertTrue(await self._blocks_trial())

    async def test_subscription_without_provider_keeps_blocking_trial(self) -> None:
        await self._ended_welcome_bonus(provider=None)

        self.assertTrue(await self._blocks_trial())

    async def test_referral_days_granted_after_the_welcome_bonus_keep_blocking_trial(
        self,
    ) -> None:
        await self._ended_welcome_bonus()
        later_start = self.claimed_at + timedelta(days=4)
        await self._subscription(
            start=later_start,
            end=later_start + timedelta(days=7),
            provider="referral",
            is_active=False,
        )

        self.assertTrue(await self._blocks_trial())

    async def test_referral_days_without_a_welcome_bonus_keep_blocking_trial(self) -> None:
        start = self.now - timedelta(days=20)
        await self._subscription(
            start=start,
            end=start + timedelta(days=7),
            provider="referral",
            is_active=False,
            user_id=INVITER,
        )

        self.assertTrue(await self._blocks_trial(INVITER))


if __name__ == "__main__":
    unittest.main()
