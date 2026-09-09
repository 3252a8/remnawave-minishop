import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from bot.app.web.admin_api_impl import users as users_module
from db.dal import partner_dal, user_balance_dal


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
    async def test_bulk_user_balances_use_one_grouped_currency_query(self):
        session = SimpleNamespace(
            execute=AsyncMock(
                return_value=FakeResult(
                    [
                        SimpleNamespace(user_id=101, amount=12500),
                        SimpleNamespace(user_id=202, amount=-300),
                    ]
                )
            )
        )

        result = await user_balance_dal.balance_minor_by_user_ids(
            session,
            [101, 202, 101],
            "USD",
        )

        self.assertEqual(result, {101: 12500, 202: -300})
        sql = _compile_sql(session.execute.await_args.args[0])
        self.assertIn("user_balance_ledger_entries.user_id in (101, 202)", sql)
        self.assertIn("upper(user_balance_ledger_entries.currency) = 'usd'", sql)
        self.assertIn("state = 'posted'", sql)
        self.assertIn("group by user_balance_ledger_entries.user_id", sql)

    async def test_bulk_partner_balances_map_profiles_to_users(self):
        session = SimpleNamespace(
            execute=AsyncMock(return_value=FakeResult([SimpleNamespace(user_id=101, amount=4200)]))
        )

        result = await partner_dal.balance_minor_by_user_ids(session, [101, 202], "EUR")

        self.assertEqual(result, {101: 4200})
        sql = _compile_sql(session.execute.await_args.args[0])
        self.assertIn("partner_profiles", sql)
        self.assertIn("partner_ledger_entries", sql)
        self.assertIn("partner_profiles.user_id in (101, 202)", sql)
        self.assertIn("upper(partner_ledger_entries.currency) = 'eur'", sql)
        self.assertIn("state = 'posted'", sql)
        self.assertIn("group by partner_profiles.user_id", sql)

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

    async def test_filter_sort_users_orders_premium_by_used_bytes(self):
        for sort_value, direction in (
            ("premium_ratio_asc", "asc"),
            ("premium_ratio_desc", "desc"),
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
                order_by = sql.split(" order by ", 1)[1]
                self.assertIn("premium_used_bytes", order_by)
                self.assertIn(direction, order_by)
                self.assertNotIn(" / ", order_by)

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

    async def test_dashboard_counter_filters_match_statistics_queries(self):
        expected_conditions = {
            "active_today": ("users.registration_date >=",),
            "referred": ("users.referred_by_id is not null",),
            "active_subscription": (
                "subscriptions_1.is_active is true",
                "subscriptions_1.end_date >",
                "exists",
            ),
            "inactive_subscription": (
                "subscriptions_1.is_active is true",
                "subscriptions_1.end_date >",
                "not (exists",
            ),
            "expired_subscription": (
                "lower(coalesce(subscriptions_1.status_from_panel, '')) = 'expired'",
                "subscriptions_2.is_active is true",
                "not (exists",
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
                for condition in conditions:
                    self.assertIn(condition, sql)

    async def test_unmapped_tariff_filter_includes_missing_and_unknown_catalog_keys(self):
        session = SimpleNamespace(
            execute=AsyncMock(side_effect=[FakeResult([]), FakeResult(scalar_value=0)])
        )

        await users_module._filter_and_sort_users(
            session,
            query="",
            filter_value="unmapped_tariff",
            panel_status="all",
            premium_traffic="all",
            sort_value="registered_desc",
            page=0,
            page_size=25,
            valid_tariff_keys={"standard", "premium"},
        )

        sql = _compile_sql(session.execute.await_args_list[0].args[0])
        self.assertIn("tariff_key is null", sql)
        self.assertIn("trim(", sql)
        self.assertIn("not in ('premium', 'standard')", sql)

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
