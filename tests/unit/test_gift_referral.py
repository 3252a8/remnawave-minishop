"""Gift qualification shares durable, recipient-scoped invitation accounting."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.referral_accrual_worker import ReferralAccrualWorker
from bot.services.referral_service import ReferralService
from bot.services.subscription_gifts import GiftError, claim_gift
from bot.services.subscription_order_terms import freeze_subscription_terms
from config.tariffs_config import TariffsConfig
from db.base import Base
from db.gift_models import SubscriptionGift
from db.models import Payment, User
from db.referral_accrual_models import ReferralPeriodAccrual


class GiftReferralTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = SimpleNamespace(
            tariffs_config=TariffsConfig.model_validate(
                {
                    "schema_version": 2,
                    "default_tariff": "base",
                    "tariffs": [
                        {
                            "key": "base",
                            "billing_model": "period",
                            "period_unit": "day",
                            "monthly_gb": 100,
                            "enabled_periods": [7],
                            "prices_rub": {"7": 100},
                            "referral_bonus_days_inviter": {"7": 3},
                            "referral_bonus_days_referee": {"7": 2},
                        }
                    ],
                }
            ),
            USER_HWID_DEVICE_LIMIT=3,
            USER_TRAFFIC_STRATEGY="NO_RESET",
            DEFAULT_LANGUAGE="en",
            REFERRAL_GIFT_ACTIVATION_ENABLED=True,
            REFERRAL_PROGRAM_ENABLED=True,
            REFERRAL_ONE_BONUS_PER_REFEREE=True,
            partner_settings=SimpleNamespace(enabled=False),
        )
        self.service = AsyncMock()
        self.service.settings = self.settings
        self.service.bot = None
        self.service.i18n = None
        self.service._subscription_billing_model = lambda _: "period"

        async def activate(*args, **kwargs):
            return {"end_date": kwargs["authoritative_end_at"]}

        self.service.activate_subscription.side_effect = activate
        async with self.factory() as session:
            session.add_all(
                [
                    User(user_id=7),
                    User(user_id=10, referred_by_id=7),
                    User(user_id=20, referred_by_id=7),
                ]
            )
            await session.commit()
        await self.issue_gift(77)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def issue_gift(self, payment_id):
        async with self.factory() as session:
            session.add(
                Payment(
                    payment_id=payment_id,
                    user_id=10,
                    status="succeeded",
                    sale_mode="subscription@base|d7|gift",
                    tariff_key="base",
                    amount=100,
                    currency="RUB",
                    subscription_duration_days=7,
                    subscription_duration_months=0,
                    subscription_terms_snapshot=freeze_subscription_terms(
                        self.settings, "subscription@base|d7|gift"
                    ),
                )
            )
            await session.flush()
            session.add(
                SubscriptionGift(payment_id=payment_id, purchaser_id=10, token=str(payment_id))
            )
            await session.commit()

    async def claim(self, payment_id=77):
        async with self.factory() as session:
            return await claim_gift(
                session, token=str(payment_id), user_id=20, service=self.service
            )

    async def rows(self):
        async with self.factory() as session:
            return list((await session.scalars(select(ReferralPeriodAccrual))).all())

    async def personal_purchase(self, payment_id=100, user_id=20):
        async with self.factory() as session:
            session.add(
                Payment(
                    payment_id=payment_id,
                    user_id=user_id,
                    status="succeeded",
                    sale_mode="subscription@base|d7",
                    tariff_key="base",
                    amount=100,
                    currency="RUB",
                    subscription_duration_days=7,
                    subscription_terms_snapshot=freeze_subscription_terms(
                        self.settings, "subscription@base|d7"
                    ),
                )
            )
            await session.flush()
            await ReferralService(
                self.settings, self.service, None, None
            ).apply_referral_bonuses_for_payment(
                session,
                user_id,
                0,
                current_payment_db_id=payment_id,
                duration_days=7,
                tariff_key="base",
                skip_if_active_before_payment=False,
                defer=True,
            )
            await session.commit()

    async def test_frozen_terms_recipient_event_and_replay(self):
        # Purchase recovery must not reward the purchaser or consume their first purchase.
        worker = ReferralAccrualWorker(self.factory, AsyncMock(), self.service)
        await worker._recover_decisions()
        self.assertEqual(await self.rows(), [])
        self.settings.tariffs_config.tariffs.clear()
        gift = await self.claim()
        await self.claim()
        rows = await self.rows()
        self.assertTrue(gift.referral_qualified)
        self.assertEqual(
            [(r.role, r.user_id, r.days) for r in rows], [("inviter", 7, 3), ("referee", 20, 2)]
        )
        self.assertTrue(all(r.gift_id == gift.gift_id for r in rows))
        self.service.activate_subscription.assert_awaited_once()

        async def extend(_session, **kwargs):
            return kwargs["target_end_date"]

        self.service.extend_active_subscription_days.side_effect = extend
        with patch("bot.services.referral_accrual_worker.events.emit_model", AsyncMock()) as emit:
            await worker.tick()
            self.assertEqual(emit.await_count, 2)
            for call in emit.await_args_list:
                payload = call.args[0].to_payload()
                self.assertEqual(payload["reason"], "gift_activation")
                self.assertEqual(payload["gift_id"], gift.gift_id)
                self.assertEqual(payload["referee_user_id"], 20)
                self.assertEqual(payload["payment_db_id"], 77)

    async def test_gift_then_purchase_and_second_gift_share_first_qualification(self):
        await self.claim()
        await self.personal_purchase()
        await self.issue_gift(78)
        await self.claim(78)
        self.assertEqual(len(await self.rows()), 2)
        # Buying a gift never occupies the purchaser's personal qualification.
        await self.personal_purchase(101, user_id=10)
        self.assertEqual(len(await self.rows()), 4)

    async def test_purchase_before_gift_prevents_second_accrual(self):
        await self.personal_purchase()
        await self.claim()
        self.assertEqual(len(await self.rows()), 2)
        self.assertTrue(all(r.gift_id is None for r in await self.rows()))

    async def test_disabled_gifts_do_not_consume_first_or_replay_when_enabled(self):
        self.settings.REFERRAL_GIFT_ACTIVATION_ENABLED = False
        gift = await self.claim()
        self.assertFalse(gift.referral_qualified)
        self.settings.REFERRAL_GIFT_ACTIVATION_ENABLED = True
        await self.claim()
        self.assertEqual(await self.rows(), [])
        await self.personal_purchase()
        self.assertEqual(len(await self.rows()), 2)

    async def test_disabling_option_does_not_erase_prior_qualification(self):
        await self.claim()
        self.settings.REFERRAL_GIFT_ACTIVATION_ENABLED = False
        await self.personal_purchase()
        self.assertEqual(len(await self.rows()), 2)

    async def test_repeat_rule_awards_each_gift_once(self):
        self.settings.REFERRAL_ONE_BONUS_PER_REFEREE = False
        await self.claim()
        await self.issue_gift(78)
        await self.claim(78)
        await self.claim(78)
        await self.personal_purchase()
        self.assertEqual(len(await self.rows()), 6)

    async def test_failed_activation_never_qualifies_until_success(self):
        activate = self.service.activate_subscription.side_effect
        self.service.activate_subscription.side_effect = None
        self.service.activate_subscription.return_value = None
        with self.assertRaisesRegex(GiftError, "gift_activation_retry"):
            await self.claim()
        self.assertEqual(await self.rows(), [])
        async with self.factory() as session:
            gift = await session.scalar(select(SubscriptionGift))
            self.assertFalse(gift.referral_qualified)
            self.assertEqual(gift.status, "activating")
        self.service.activate_subscription.side_effect = activate
        await self.claim()
        self.assertEqual(len(await self.rows()), 2)

    async def test_no_invitation_or_disabled_program_grants_nothing(self):
        async with self.factory() as session:
            recipient = await session.get(User, 20)
            recipient.referred_by_id = None
            await session.commit()
        with patch("bot.services.referral_service.PartnerProgramService") as partner:
            await self.claim()
            partner.assert_not_called()
        self.assertEqual(await self.rows(), [])
        self.settings.REFERRAL_PROGRAM_ENABLED = False
        await self.issue_gift(78)
        self.assertFalse((await self.claim(78)).referral_qualified)
