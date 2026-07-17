import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from bot.app.web.admin_api_impl import users as users_module


class FakeResult:
    def __init__(self, rows=None, scalar_value=0):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar_one(self):
        return self._scalar_value


def _compile_sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


class AdminUsersListMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_bulk_user_payment_summaries_returns_succeeded_totals(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=FakeResult([(101, 1234.5, 3, "RUB")]))
        )

        result = await users_module._bulk_user_payment_summaries(session, [101])

        self.assertEqual(
            result,
            {
                101: {
                    "total_amount": 1234.5,
                    "count": 3,
                    "currency": "RUB",
                }
            },
        )
        sql = _compile_sql(session.execute.await_args.args[0])
        self.assertIn("payments.status = 'succeeded'", sql)
        self.assertIn("sum(payments.amount)", sql)
        self.assertIn("count(payments.payment_id)", sql)

    async def test_bulk_user_referral_counts_groups_invited_users(self):
        session = SimpleNamespace(execute=AsyncMock(return_value=FakeResult([(101, 7)])))

        result = await users_module._bulk_user_referral_counts(session, [101])

        self.assertEqual(result, {101: 7})
        sql = _compile_sql(session.execute.await_args.args[0])
        self.assertIn("referred_by_id", sql)
        self.assertIn("group by", sql)

    async def test_filter_sort_users_supports_payment_total_sort(self):
        session = SimpleNamespace(
            execute=AsyncMock(side_effect=[FakeResult([]), FakeResult(scalar_value=0)])
        )

        await users_module._filter_and_sort_users(
            session,
            query="",
            filter_value="all",
            panel_status="all",
            premium_traffic="all",
            sort_value="payments_total_desc",
            page=0,
            page_size=25,
        )

        sql = _compile_sql(session.execute.await_args_list[0].args[0])
        self.assertIn("user_payment_summary", sql)
        self.assertIn("payments_total_amount", sql)
        self.assertIn("order by coalesce", sql)
        self.assertIn("desc", sql)

    async def test_active_panel_filter_requires_live_unbanned_subscription(self):
        session = SimpleNamespace(
            execute=AsyncMock(side_effect=[FakeResult([]), FakeResult(scalar_value=0)])
        )

        await users_module._filter_and_sort_users(
            session,
            query="",
            filter_value="all",
            panel_status="active",
            premium_traffic="all",
            sort_value="created_desc",
            page=0,
            page_size=25,
        )

        sql = _compile_sql(session.execute.await_args_list[0].args[0])
        self.assertIn("users.is_banned is false", sql)
        self.assertIn("subscriptions.is_active is true", sql)
        self.assertIn("subscriptions.end_date >", sql)

    async def test_subscription_segment_filters_match_dashboard_priority(self):
        expected_conditions = {
            "paid": ("active_subscription_segment_flags.has_paid_subscription = 1",),
            "trial": (
                "active_subscription_segment_flags.has_paid_subscription = 0",
                "active_subscription_segment_flags.has_trial_subscription = 1",
            ),
            "free": (
                "active_subscription_segment_flags.has_paid_subscription = 0",
                "active_subscription_segment_flags.has_trial_subscription = 0",
                "active_subscription_segment_flags.has_free_subscription = 1",
            ),
        }

        for filter_value, conditions in expected_conditions.items():
            with self.subTest(filter_value=filter_value):
                session = SimpleNamespace(
                    execute=AsyncMock(side_effect=[FakeResult([]), FakeResult(scalar_value=0)])
                )

                await users_module._filter_and_sort_users(
                    session,
                    query="",
                    filter_value=filter_value,
                    panel_status="all",
                    premium_traffic="all",
                    sort_value="registered_desc",
                    page=0,
                    page_size=25,
                )

                sql = _compile_sql(session.execute.await_args_list[0].args[0])
                self.assertIn("subscriptions.is_active is true", sql)
                self.assertIn("subscriptions.end_date >", sql)
                for condition in conditions:
                    self.assertIn(condition, sql)

    async def test_bulk_user_statuses_treats_expired_active_rows_as_expired(self):
        now = datetime.now(UTC)
        session = SimpleNamespace(
            execute=AsyncMock(
                return_value=FakeResult(
                    [
                        (101, "ACTIVE", True, now - timedelta(days=1)),
                        (202, "ACTIVE", True, now + timedelta(days=1)),
                        (303, None, False, now - timedelta(days=1)),
                    ]
                )
            )
        )

        result = await users_module._bulk_user_statuses(session, [101, 202, 303, 404])

        self.assertEqual(result[101]["status"], "expired")
        self.assertEqual(result[202]["status"], "active")
        self.assertEqual(result[303]["status"], "expired")
        self.assertEqual(result[404]["status"], "bot_only")

    async def test_filter_sort_users_supports_referral_and_subscription_sorts(self):
        for sort_value, expected_alias in (
            ("invited_users_count_desc", "user_referral_count"),
            ("subscription_expires_at_asc", "user_subscription_expiry"),
        ):
            with self.subTest(sort_value=sort_value):
                session = SimpleNamespace(
                    execute=AsyncMock(side_effect=[FakeResult([]), FakeResult(scalar_value=0)])
                )

                await users_module._filter_and_sort_users(
                    session,
                    query="",
                    filter_value="all",
                    panel_status="all",
                    premium_traffic="all",
                    sort_value=sort_value,
                    page=0,
                    page_size=25,
                )

                sql = _compile_sql(session.execute.await_args_list[0].args[0])
                self.assertIn(expected_alias, sql)
                self.assertIn("order by", sql)


if __name__ == "__main__":
    unittest.main()
