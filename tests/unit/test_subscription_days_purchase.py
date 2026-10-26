"""Day-funded add-ons exercise real SQL rows, fulfillment and reversal boundaries."""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.services.panel_api_service import PanelApiService
from bot.services.payment_fulfillment import PaymentFulfillmentError, reverse_payment_fulfillment
from bot.services.subscription_days_purchase import purchase_with_days
from bot.services.subscription_days_quotes import (
    AddonSelection,
    SubscriptionDaysError,
    attach_days_quotes,
    aware,
    read_quote,
    sign_quote,
)
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.base import Base
from db.gift_models import SubscriptionGift
from db.models import HwidDevicePurchase, Payment, Subscription, TrafficTopup, User


class SubscriptionDaysPurchaseTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        tariff = {
            "key": "standard",
            "names": {"en": "Standard"},
            "enabled": True,
            "billing_model": "period",
            "monthly_gb": 100,
            "hwid_device_limit": 3,
            "squad_uuids": ["main"],
            "premium_squad_uuids": ["premium"],
            "premium_monthly_gb": 100,
            "prices_rub": {"1": 300},
            "enabled_periods": [1],
            "topup_packages": {"rub": [{"gb": 5, "price": 31}]},
            "premium_topup_packages": {"rub": [{"gb": 2, "price": 20}]},
            "hwid_device_packages": {"rub": [{"count": 1, "price": 31}]},
        }
        path = Path(self.temp.name) / "tariffs.json"
        path.write_text(
            json.dumps({"default_tariff": "standard", "tariffs": [tariff]}), encoding="utf-8"
        )
        self.settings = Settings(
            _env_file=None,
            BOT_TOKEN="test",
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            TARIFFS_CONFIG_PATH=str(path),
            MY_DEVICES_SECTION_ENABLED=True,
            SUBSCRIPTION_DAYS_DEVICES_ENABLED=True,
            SUBSCRIPTION_DAYS_TRAFFIC_ENABLED=True,
            WEBAPP_SESSION_SECRET="test-only-signing-secret",
        )
        self.service = SubscriptionService(self.settings, AsyncMock(spec=PanelApiService))
        self.service.sync_main_traffic_limit_to_panel = AsyncMock(return_value=True)
        self.service.sync_premium_squad_access_to_panel = AsyncMock(return_value=True)
        self.service._confirmed_panel_entitlement = AsyncMock(return_value={"shortUuid": "short"})
        self.service._sync_panel_squads_if_needed = AsyncMock(return_value=True)
        self.service.build_effective_panel_squad_fields = AsyncMock(return_value={})
        self.service._send_payment_success_email = AsyncMock()
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.end = datetime.now(UTC) + timedelta(days=30)
        async with self.sessions() as session:
            session.add(User(user_id=42, telegram_id=42, panel_user_uuid="panel-42"))
            session.add(
                Subscription(
                    subscription_id=11,
                    user_id=42,
                    panel_user_uuid="panel-42",
                    panel_subscription_uuid="short",
                    tariff_key="standard",
                    provider="yookassa",
                    start_date=self.end - timedelta(days=30),
                    end_date=self.end,
                    is_active=True,
                    status_from_panel="ACTIVE",
                    duration_months=1,
                    duration_days=30,
                    period_semantics="fixed_days",
                    effective_monthly_price_rub=300,
                    hwid_device_limit=3,
                    tier_baseline_bytes=100 * 1024**3,
                    premium_baseline_bytes=100 * 1024**3,
                )
            )
            session.add(
                Payment(
                    payment_id=1,
                    user_id=42,
                    provider="yookassa",
                    amount=300,
                    currency="RUB",
                    status="succeeded",
                    tariff_key="standard",
                    sale_mode="subscription@standard",
                    subscription_duration_days=30,
                    fulfilled_at=self.end - timedelta(days=31),
                )
            )
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.temp.cleanup()

    async def quote(self, mode="topup"):
        plan = {
            "sale_mode": mode,
            "tariff_key": "standard",
            "currency": "RUB",
            "traffic_gb": 2 if mode == "premium_topup" else 5,
            "device_count": 1,
        }
        async with self.sessions() as session:
            sub = await session.get(Subscription, 11)
            await attach_days_quotes(session, self.service, sub, [plan])
        return plan.get("subscription_days")

    async def buy(self, quote, mode="topup"):
        selection = AddonSelection.parse(
            mode, "standard", 1 if mode == "hwid_devices" else 2 if mode == "premium_topup" else 5
        )
        async with self.sessions() as session:
            payment = await purchase_with_days(
                session,
                self.service,
                user_id=42,
                selection=selection,
                token=quote["quote_token"],
                description="Add-on",
            )
            await session.commit()
            return int(payment.payment_id)

    async def change_sub(self, **fields):
        async with self.sessions() as session:
            sub = await session.get(Subscription, 11)
            for key, value in fields.items():
                setattr(sub, key, value)
            await session.commit()

    async def test_rounds_up_and_shows_both_dates(self):
        quote = await self.quote()
        self.assertTrue(quote["eligible"])
        self.assertEqual(quote["days_to_charge"], 4)
        self.assertEqual(quote["current_expires_at"], self.end.isoformat())
        self.assertEqual(quote["next_expires_at"], (self.end - timedelta(days=4)).isoformat())
        self.assertEqual(quote["price_amount"], 31)

    async def test_flags_are_separate_and_disabled_by_default(self):
        self.settings.SUBSCRIPTION_DAYS_TRAFFIC_ENABLED = False
        self.assertIsNone(await self.quote())
        self.assertTrue((await self.quote("hwid_devices"))["eligible"])
        self.settings.SUBSCRIPTION_DAYS_DEVICES_ENABLED = False
        self.assertIsNone(await self.quote("hwid_devices"))

    async def test_paid_rate_falls_back_to_payment_period(self):
        await self.change_sub(effective_monthly_price_rub=None)
        self.assertEqual((await self.quote())["days_to_charge"], 4)

    async def test_paid_snapshot_must_cover_the_current_subscription(self):
        for subscription_id, end_date in (
            (12, self.end),
            (11, datetime.now(UTC) - timedelta(days=1)),
            (11, self.end - timedelta(days=1)),
        ):
            with self.subTest(subscription_id=subscription_id, end_date=end_date):
                async with self.sessions() as session:
                    paid = await session.get(Payment, 1)
                    paid.fulfillment_after_snapshot = json.dumps(
                        {
                            "users": [
                                {
                                    "subscriptions": [
                                        {
                                            "subscription_id": subscription_id,
                                            "end_date": end_date.isoformat(),
                                        }
                                    ]
                                }
                            ]
                        }
                    )
                    await session.commit()
                quote = await self.quote()
                self.assertEqual(quote["disabled_reason"], "paid_subscription_required")
                self.assertIsNone(quote["quote_token"])

    async def test_internal_balance_payment_is_paid_but_currency_must_match(self):
        async with self.sessions() as session:
            paid = await session.get(Payment, 1)
            paid.amount = 0
            paid.checkout_total_amount = 300
            paid.funding_source = "internal_user_balance"
            await session.commit()
        self.assertTrue((await self.quote())["eligible"])
        async with self.sessions() as session:
            paid = await session.get(Payment, 1)
            paid.currency = "USD"
            await session.commit()
        self.assertEqual((await self.quote())["disabled_reason"], "price_unavailable")

    def test_rejects_unbounded_and_sub_byte_quantities(self):
        for value in ("1e999999", "1e-999999", "Infinity", "NaN", "-1", "0"):
            with self.subTest(value=value), self.assertRaises(SubscriptionDaysError):
                AddonSelection.parse("topup", "standard", value)

    async def test_minimum_and_non_paid_subscription_guards(self):
        cases = [
            ({"provider": "trial"}, "paid_subscription_required"),
            ({"provider": "admin"}, "paid_subscription_required"),
            ({"status_from_panel": "TRIAL"}, "paid_subscription_required"),
            ({"duration_days": None, "duration_months": None}, "duration_required"),
            ({"end_date": datetime.now(UTC) + timedelta(days=4)}, "insufficient_days"),
        ]
        for fields, reason in cases:
            with self.subTest(fields=fields):
                await self.change_sub(
                    provider="yookassa",
                    status_from_panel="ACTIVE",
                    duration_days=30,
                    duration_months=1,
                    end_date=self.end,
                )
                await self.change_sub(**fields)
                quote = await self.quote()
                self.assertFalse(quote["eligible"])
                self.assertEqual(quote["disabled_reason"], reason)
                self.assertIsNone(quote["quote_token"])

    async def test_free_later_period_cannot_reuse_older_paid_history(self):
        async with self.sessions() as session:
            session.add(
                Payment(
                    user_id=42,
                    provider="internal",
                    amount=0,
                    currency="RUB",
                    status="succeeded",
                    tariff_key="standard",
                    sale_mode="subscription@standard",
                )
            )
            await session.commit()
        self.assertEqual((await self.quote())["disabled_reason"], "paid_subscription_required")

    async def test_no_paid_history_cannot_use_catalog_price(self):
        async with self.sessions() as session:
            payment = await session.get(Payment, 1)
            payment.status = "refunded"
            await session.commit()
        self.assertEqual((await self.quote())["disabled_reason"], "paid_subscription_required")

    async def test_paid_gift_is_eligible_but_zero_value_gift_is_not(self):
        await self.change_sub(provider="gift", gift_terms_snapshot="{}")
        async with self.sessions() as session:
            session.add(
                SubscriptionGift(
                    payment_id=1,
                    purchaser_id=42,
                    recipient_id=42,
                    token="test-gift",
                    status="activated",
                    activated_at=datetime.now(UTC),
                    activation_end_at=self.end,
                )
            )
            await session.commit()
        self.assertTrue((await self.quote())["eligible"])
        async with self.sessions() as session:
            payment = await session.get(Payment, 1)
            payment.amount = 0
            await session.commit()
        self.assertEqual((await self.quote())["disabled_reason"], "paid_subscription_required")

    async def test_confirm_and_replay_charge_once_and_reverse_restores_days(self):
        quote = await self.quote()
        payment_id = await self.buy(quote)
        self.assertEqual(await self.buy(quote), payment_id)
        async with self.sessions() as session:
            sub = await session.get(Subscription, 11)
            payment = await session.get(Payment, payment_id)
            self.assertEqual(aware(sub.end_date), self.end - timedelta(days=4))
            self.assertEqual(sub.topup_balance_bytes, 5 * 1024**3)
            self.assertEqual(payment.amount, 0)
            self.assertEqual(payment.subscription_days_spent, 4)
            self.assertEqual(
                await session.scalar(select(func.count()).select_from(TrafficTopup)), 1
            )
            await reverse_payment_fulfillment(
                session,
                payment_id=payment_id,
                actor_admin_id=42,
                reason="Test reversal",
                restore_promo_usage=False,
                subscription_service=self.service,
            )
            await session.commit()
            self.assertEqual(aware(sub.end_date), self.end)
            self.assertEqual(sub.topup_balance_bytes, 0)
            self.assertEqual(payment.status, "reversed")
        with self.assertRaises(PaymentFulfillmentError):
            async with self.sessions() as session:
                await reverse_payment_fulfillment(
                    session,
                    payment_id=payment_id,
                    actor_admin_id=42,
                    reason="Repeated reversal",
                    restore_promo_usage=False,
                    subscription_service=self.service,
                )
        self.service._send_payment_success_email.assert_not_awaited()

    async def test_devices_expire_at_shortened_subscription_end(self):
        quote = await self.quote("hwid_devices")
        payment_id = await self.buy(quote, "hwid_devices")
        async with self.sessions() as session:
            sub = await session.get(Subscription, 11)
            purchase = await session.scalar(
                select(HwidDevicePurchase).where(HwidDevicePurchase.payment_id == payment_id)
            )
            self.assertEqual(aware(purchase.valid_until), aware(sub.end_date))
            self.assertEqual(sub.extra_hwid_devices, 1)
            await reverse_payment_fulfillment(
                session,
                payment_id=payment_id,
                actor_admin_id=42,
                reason="Undo devices",
                restore_promo_usage=False,
                subscription_service=self.service,
            )
            await session.commit()
            self.assertEqual(aware(sub.end_date), self.end)
            self.assertEqual(sub.extra_hwid_devices, 0)

    async def test_premium_traffic_reversal_also_restores_days(self):
        quote = await self.quote("premium_topup")
        payment_id = await self.buy(quote, "premium_topup")
        async with self.sessions() as session:
            sub = await session.get(Subscription, 11)
            self.assertEqual(aware(sub.end_date), self.end - timedelta(days=2))
            await reverse_payment_fulfillment(
                session,
                payment_id=payment_id,
                actor_admin_id=42,
                reason="Undo premium",
                restore_promo_usage=False,
                subscription_service=self.service,
            )
            await session.commit()
            self.assertEqual(aware(sub.end_date), self.end)
            self.assertEqual(sub.premium_topup_balance_bytes, 0)

    async def test_stale_dates_disabled_setting_and_expired_tokens_do_not_charge(self):
        quote = await self.quote()
        await self.change_sub(end_date=self.end + timedelta(days=1))
        with self.assertRaisesRegex(SubscriptionDaysError, "quote_stale"):
            await self.buy(quote)
        await self.change_sub(end_date=self.end)
        self.settings.SUBSCRIPTION_DAYS_TRAFFIC_ENABLED = False
        with self.assertRaisesRegex(SubscriptionDaysError, "unavailable"):
            await self.buy(quote)
        self.settings.SUBSCRIPTION_DAYS_TRAFFIC_ENABLED = True
        payload = read_quote(self.settings, quote["quote_token"], 42)
        payload["exp"] = 1
        quote["quote_token"] = sign_quote(self.settings, payload)
        with self.assertRaisesRegex(SubscriptionDaysError, "quote_stale"):
            await self.buy(quote)

    async def test_token_cannot_be_changed_or_used_for_another_account(self):
        quote = await self.quote()
        with self.assertRaises(SubscriptionDaysError):
            read_quote(self.settings, quote["quote_token"], 43)
        quote["quote_token"] += "0"
        with self.assertRaises(SubscriptionDaysError):
            await self.buy(quote)

    async def test_panel_failure_rolls_back_days_payment_and_grant(self):
        quote = await self.quote()
        with (
            patch.object(
                self.service, "sync_main_traffic_limit_to_panel", AsyncMock(return_value=False)
            ),
            self.assertRaisesRegex(SubscriptionDaysError, "panel_failed"),
        ):
            await self.buy(quote)
        async with self.sessions() as session:
            sub = await session.get(Subscription, 11)
            self.assertEqual(aware(sub.end_date), self.end)
            self.assertEqual(sub.topup_balance_bytes, 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Payment)), 1)
            self.assertEqual(
                await session.scalar(select(func.count()).select_from(TrafficTopup)), 0
            )
