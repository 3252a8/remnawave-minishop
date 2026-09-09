from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from sqlalchemy.sql.dml import Update

from db.dal import user_merge_dal
from db.dal.user_merge_entitlements import (
    merge_active_subscription_entitlements,
    merge_subscription_state,
)


class UserMergeEntitlementTests(IsolatedAsyncioTestCase):
    def test_merge_does_not_stack_two_free_grants(self):
        now = datetime(2026, 7, 13, tzinfo=UTC)
        source = SimpleNamespace(
            end_date=now + timedelta(days=7),
            duration_months=0,
            provider="trial",
            status_from_panel="TRIAL",
        )
        target = SimpleNamespace(
            end_date=now + timedelta(days=5),
            duration_months=0,
            provider=None,
            status_from_panel="ACTIVE_BONUS",
        )

        end_date, status = user_merge_dal._merged_subscription_end(source, target, now=now)

        self.assertEqual(end_date, now + timedelta(days=7))
        self.assertEqual(status, "ACTIVE_MERGED_FREE_GRANT")

    def test_merge_preserves_both_paid_subscription_balances(self):
        now = datetime(2026, 7, 13, tzinfo=UTC)
        source = SimpleNamespace(
            end_date=now + timedelta(days=30),
            duration_months=1,
            provider="stripe",
            status_from_panel="ACTIVE",
        )
        target = SimpleNamespace(
            end_date=now + timedelta(days=10),
            duration_months=1,
            provider="yookassa",
            status_from_panel="ACTIVE",
        )

        end_date, status = user_merge_dal._merged_subscription_end(source, target, now=now)

        self.assertEqual(end_date, now + timedelta(days=40))
        self.assertEqual(status, "ACTIVE_EXTENDED_BY_MERGE")

    def test_merge_does_not_add_free_grant_to_paid_balance(self):
        now = datetime(2026, 7, 13, tzinfo=UTC)
        free_source = SimpleNamespace(
            end_date=now + timedelta(days=7),
            duration_months=0,
            provider="trial",
            status_from_panel="TRIAL",
        )
        paid_target = SimpleNamespace(
            end_date=now + timedelta(days=30),
            duration_months=1,
            provider="stripe",
            status_from_panel="ACTIVE",
        )

        end_date, status = user_merge_dal._merged_subscription_end(
            free_source, paid_target, now=now
        )

        self.assertEqual(end_date, now + timedelta(days=30))
        self.assertEqual(status, "ACTIVE_MERGED_FREE_GRANT")

    def test_merge_keeps_stronger_tariff_and_combines_additive_limits(self):
        now = datetime(2026, 7, 13, tzinfo=UTC)
        source = SimpleNamespace(
            subscription_id=10,
            start_date=now - timedelta(days=20),
            end_date=now + timedelta(days=30),
            duration_months=1,
            duration_days=None,
            period_semantics="calendar_month",
            provider="yookassa",
            status_from_panel="ACTIVE",
            tariff_key="premium",
            tariff_binding_source="application",
            tier_baseline_bytes=500,
            premium_baseline_bytes=200,
            premium_is_limited=True,
            effective_monthly_price_rub=500,
            hwid_device_limit=3,
            hwid_device_limit_is_override=False,
            tariff_managed_squad_uuids=["premium"],
            topup_balance_bytes=70,
            regular_bonus_bytes=30,
            premium_topup_balance_bytes=20,
            premium_bonus_bytes=10,
            regular_unlimited_override=False,
            premium_unlimited_override=False,
            extra_hwid_devices=2,
            auto_renew_enabled=False,
        )
        target = SimpleNamespace(
            subscription_id=20,
            start_date=now - timedelta(days=10),
            end_date=now + timedelta(days=10),
            duration_months=1,
            duration_days=None,
            period_semantics="calendar_month",
            provider="cryptomus",
            status_from_panel="ACTIVE",
            tariff_key="basic",
            tier_baseline_bytes=100,
            premium_baseline_bytes=0,
            effective_monthly_price_rub=100,
            hwid_device_limit=1,
            hwid_device_limit_is_override=False,
            topup_balance_bytes=50,
            regular_bonus_bytes=20,
            premium_topup_balance_bytes=5,
            premium_bonus_bytes=4,
            regular_unlimited_override=False,
            premium_unlimited_override=False,
            extra_hwid_devices=1,
            auto_renew_enabled=False,
        )

        merge_subscription_state(
            source,
            target,
            now=now,
            source_has_recurring=False,
            target_has_recurring=False,
        )

        self.assertEqual(target.tariff_key, "premium")
        self.assertEqual(target.hwid_device_limit, 3)
        self.assertEqual(target.extra_hwid_devices, 3)
        self.assertEqual(target.topup_balance_bytes, 120)
        self.assertEqual(target.regular_bonus_bytes, 50)
        self.assertEqual(target.premium_topup_balance_bytes, 25)
        self.assertEqual(target.premium_bonus_bytes, 14)
        self.assertEqual(target.end_date, now + timedelta(days=40))
        self.assertFalse(source.is_active)

    def test_merge_preserves_larger_explicit_device_override(self):
        now = datetime(2026, 7, 13, tzinfo=UTC)
        source = SimpleNamespace(
            end_date=now + timedelta(days=30),
            duration_months=1,
            provider="stripe",
            status_from_panel="ACTIVE",
            effective_monthly_price_rub=500,
            hwid_device_limit=3,
            hwid_device_limit_is_override=False,
        )
        target = SimpleNamespace(
            end_date=now + timedelta(days=10),
            duration_months=1,
            provider="yookassa",
            status_from_panel="ACTIVE",
            effective_monthly_price_rub=100,
            hwid_device_limit=8,
            hwid_device_limit_is_override=True,
        )

        merge_subscription_state(
            source,
            target,
            now=now,
            source_has_recurring=False,
            target_has_recurring=False,
        )

        self.assertEqual(target.hwid_device_limit, 8)
        self.assertTrue(target.hwid_device_limit_is_override)

    def test_merge_transfers_the_only_recurring_payment(self):
        now = datetime(2026, 7, 13, tzinfo=UTC)
        source = SimpleNamespace(
            end_date=now + timedelta(days=30),
            duration_months=3,
            duration_days=None,
            period_semantics="fixed_days",
            provider="yookassa",
            status_from_panel="ACTIVE",
            auto_renew_enabled=True,
            auto_renew_consent_version=4,
        )
        target = SimpleNamespace(
            end_date=now + timedelta(days=10),
            duration_months=1,
            duration_days=None,
            period_semantics="calendar_month",
            provider="cryptomus",
            status_from_panel="ACTIVE",
            auto_renew_enabled=False,
            auto_renew_consent_version=0,
        )

        merge_subscription_state(
            source,
            target,
            now=now,
            source_has_recurring=True,
            target_has_recurring=False,
        )

        self.assertTrue(target.auto_renew_enabled)
        self.assertEqual(target.provider, "yookassa")
        self.assertEqual(target.duration_months, 3)
        self.assertEqual(target.auto_renew_consent_version, 4)
        self.assertFalse(source.auto_renew_enabled)

    async def test_merge_moves_active_purchase_windows_to_surviving_subscription(self):
        now = datetime(2026, 7, 13, tzinfo=UTC)
        source = SimpleNamespace(
            subscription_id=10,
            end_date=now + timedelta(days=30),
            duration_months=1,
            provider="stripe",
            status_from_panel="ACTIVE",
            auto_renew_enabled=False,
        )
        target = SimpleNamespace(
            subscription_id=20,
            end_date=now + timedelta(days=10),
            duration_months=1,
            provider="yookassa",
            status_from_panel="ACTIVE",
            auto_renew_enabled=False,
        )
        session = SimpleNamespace(execute=AsyncMock())

        await merge_active_subscription_entitlements(
            session,
            source,
            target,
            now=now,
            source_has_recurring=False,
            target_has_recurring=False,
        )

        moved_tables = {
            call.args[0].table.name
            for call in session.execute.await_args_list
            if isinstance(call.args[0], Update)
        }
        self.assertEqual(
            moved_tables,
            {"traffic_topups", "flexible_traffic_limits", "hwid_device_purchases"},
        )
        for call in session.execute.await_args_list:
            statement = call.args[0]
            self.assertIn(20, statement.compile().params.values())
