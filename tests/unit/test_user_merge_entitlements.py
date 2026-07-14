from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase

from db.dal import user_merge_dal


class UserMergeEntitlementTests(TestCase):
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
