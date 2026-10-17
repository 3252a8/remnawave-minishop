"""Exercise plan selection and filtering against real overlapping SQL rows."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.app.web.admin_api_impl import users_listing
from bot.app.web.admin_api_impl.subscription_plans import (
    admin_active_tariffs,
    admin_subscription_plan,
    admin_tariff_options,
)
from bot.app.web.admin_api_impl.users_queries import _filter_and_sort_users
from config.settings import Settings
from config.tariffs_config import TariffsConfig
from db.dal.user_broadcast_dal import get_enhanced_user_statistics
from db.dal.user_subscription_plans import (
    get_active_subscription_plan_counts,
    get_subscription_plan_tariff_keys,
    get_user_subscription_plans,
)
from db.models import Subscription, User


class AdminSubscriptionPlansTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.now = datetime(2026, 10, 15, 12, tzinfo=UTC)
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(
                lambda conn: User.metadata.create_all(
                    conn, tables=[User.__table__, Subscription.__table__]
                )
            )
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.settings = cast(
            Settings,
            SimpleNamespace(
                tariffs_config=TariffsConfig.model_validate(
                    {
                        "default_tariff": "standard",
                        "tariffs": [
                            {
                                "key": key,
                                "names": {"en": key.title()},
                                "enabled": enabled,
                                "billing_model": "period",
                                "monthly_gb": 100,
                                "enabled_periods": [1],
                                "prices_rub": {"1": 100},
                            }
                            for key, enabled in (
                                ("standard", True),
                                ("premium", True),
                                ("retired", False),
                                ("unused", True),
                            )
                        ],
                    }
                )
            ),
        )
        async with self.factory() as session:
            session.add_all(
                [User(user_id=user_id, is_banned=user_id == 7) for user_id in range(1, 16)]
            )
            for subscription_id, (uid, key, provider, days, active, status) in enumerate(
                [
                    (1, "standard", "payment", 3, True, "ACTIVE"),
                    (1, "premium", "trial", 30, True, "ACTIVE"),
                    (2, "standard", "TrIaL", 3, True, "ACTIVE"),
                    (3, None, None, 3, True, "ACTIVE"),
                    (4, "retired", "payment", 3, True, "ACTIVE"),
                    (5, "historical:plan|", "payment", -3, False, "EXPIRED"),
                    (7, "旧:plan|", "payment", 3, True, "ACTIVE"),
                    (8, "removed|plan:ß", "payment", 3, True, "ACTIVE"),
                    (9, "standard", "payment", 3, True, "ACTIVE"),
                    (9, "premium", "payment", 3, True, "ACTIVE"),
                    (10, "standard", "trial", -2, False, "EXPIRED"),
                    (11, "   ", None, 3, True, "ACTIVE"),
                    (12, "standard", "payment", 5, False, "DISABLED"),
                    (13, "standard", "payment", 0, True, "ACTIVE"),
                    (14, "standard", "payment", 3, True, "trial"),
                    (15, "standard", None, 3, True, "ACTIVE"),
                ],
                start=1,
            ):
                session.add(
                    Subscription(
                        subscription_id=subscription_id,
                        user_id=uid,
                        panel_user_uuid=f"panel-{uid}",
                        tariff_key=key,
                        provider=provider,
                        end_date=self.now + timedelta(days=days),
                        is_active=active,
                        status_from_panel=status,
                    )
                )
            await session.commit()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _users(
        self, tariff_filter: str, *, active_only: bool = False, page: int = 0, page_size: int = 100
    ) -> tuple[list[int], int]:
        async with self.factory() as session:
            users, total = await _filter_and_sort_users(
                session,
                filter_value="active_subscription" if active_only else "all",
                tariff_filter=tariff_filter,
                sort_value="registered_asc",
                page=page,
                page_size=page_size,
                now=self.now,
            )
        return sorted(int(user.user_id) for user in users), total

    async def test_display_uses_paid_precedence_trial_and_latest_history(self) -> None:
        async with self.factory() as session:
            plans = await get_user_subscription_plans(session, list(range(1, 16)), now=self.now)
        self.assertEqual(plans[1]["tariff_key"], "standard")
        self.assertEqual(plans[9]["tariff_key"], "premium")
        self.assertIsNone(admin_subscription_plan(self.settings, plans.get(6)))
        trial = admin_subscription_plan(self.settings, plans[2])
        self.assertIsNotNone(trial)
        assert trial is not None
        self.assertEqual((trial["kind"], trial["tariff_key"]), ("trial", None))
        historical = admin_subscription_plan(self.settings, plans[5])
        assert historical is not None
        self.assertEqual(historical["tariff_key"], "historical:plan|")
        self.assertFalse(historical["is_active"])
        self.assertFalse(historical["is_configured"])
        retired = admin_subscription_plan(self.settings, plans[4])
        assert retired is not None
        self.assertTrue(retired["is_configured"])
        self.assertFalse(retired["is_enabled"])
        self.assertFalse(plans[13]["is_active"])

    async def test_plan_filters_include_history_but_distinguish_no_subscription(self) -> None:
        expected = {
            "trial": [2, 10, 14],
            "no_subscription": [6],
            "no_tariff": [3, 11],
            "tariff:standard": [1, 12, 13, 15],
            "tariff:retired": [4],
            "tariff:旧:plan|": [7],
            "tariff:removed|plan:ß": [8],
        }
        for tariff_filter, expected_users in expected.items():
            with self.subTest(tariff_filter=tariff_filter):
                users, total = await self._users(tariff_filter)
                self.assertEqual(users, expected_users)
                self.assertEqual(total, len(expected_users))
        first, total = await self._users("trial", page_size=2)
        second, second_total = await self._users("trial", page=1, page_size=2)
        self.assertEqual((total, second_total), (3, 3))
        self.assertEqual(sorted(first + second), [2, 10, 14])
        self.assertEqual(len(set(first) & set(second)), 0)

    async def test_distribution_reconciles_dashboard_total_and_each_drilldown(self) -> None:
        async with self.factory() as session:
            statistics = await get_enhanced_user_statistics(session, now=self.now)
            counts = await get_active_subscription_plan_counts(session, now=self.now)
        distribution = admin_active_tariffs(self.settings, counts)
        self.assertEqual(sum(row["active_users"] for row in distribution), 10)
        self.assertEqual(statistics["active_subscriptions"], 10)
        self.assertEqual(
            {
                row["tariff_key"]: row["active_users"]
                for row in distribution
                if row["kind"] == "tariff"
            },
            {
                "standard": 2,
                "premium": 1,
                "retired": 1,
                "unused": 0,
                "removed|plan:ß": 1,
                "旧:plan|": 1,
            },
        )
        for row in distribution:
            tariff_filter = (
                "trial"
                if row["kind"] == "trial"
                else "no_tariff"
                if row["kind"] == "unassigned"
                else f"tariff:{row['tariff_key']}"
            )
            with self.subTest(tariff_filter=tariff_filter):
                users, total = await self._users(tariff_filter, active_only=True)
                self.assertEqual(total, row["active_users"])
                self.assertEqual(len(users), total)

    async def test_options_keep_disabled_zero_and_observed_historical_tariffs(self) -> None:
        async with self.factory() as session:
            keys = await get_subscription_plan_tariff_keys(session, now=self.now)
        options = admin_tariff_options(self.settings, keys)
        by_key = {row["tariff_key"]: row for row in options}
        self.assertIn("unused", by_key)
        self.assertIn("historical:plan|", by_key)
        self.assertIn("旧:plan|", by_key)
        self.assertFalse(by_key["retired"]["is_enabled"])
        self.assertFalse(by_key["historical:plan|"]["is_configured"])
        self.assertEqual(len(options), len(by_key))

    async def test_route_preserves_exact_filter_and_rejects_invalid_syntax(self) -> None:
        load = AsyncMock(return_value={"users": [], "total": 0})
        with (
            patch.object(users_listing, "_require_admin_user_id", return_value=42),
            patch.object(users_listing, "get_settings", return_value=self.settings),
            patch.object(users_listing, "get_session_factory", return_value=self.factory),
            patch.object(users_listing, "_load_admin_users_list_payload", load),
        ):
            response = await users_listing.admin_users_list_route(
                cast(Any, SimpleNamespace(query={"tariff_filter": "tariff:旧:plan|"}))
            )
            self.assertEqual(response.status, 200)
            assert load.await_args is not None
            self.assertEqual(load.await_args.kwargs["tariff_filter"], "tariff:旧:plan|")
            for invalid in ("garbage", "tariff:"):
                response = await users_listing.admin_users_list_route(
                    cast(Any, SimpleNamespace(query={"tariff_filter": invalid}))
                )
                self.assertEqual(response.status, 400)
                self.assertEqual(json.loads(response.body)["error"], "invalid_tariff_filter")
            self.assertEqual(load.await_count, 1)

    async def test_legacy_alias_resolves_metadata_without_changing_exact_identity(self) -> None:
        alias = "old|retired:ß"
        trial_alias = "trial:only|alias"
        config = self.settings.tariffs_config
        assert config is not None
        tariff = config.get("retired")
        assert tariff is not None
        tariff.legacy_keys = [alias, trial_alias]
        async with self.factory() as session:
            session.add_all([User(user_id=16), User(user_id=17)])
            session.add_all(
                [
                    Subscription(
                        subscription_id=100 + user_id,
                        user_id=user_id,
                        panel_user_uuid=f"panel-{user_id}",
                        tariff_key=key,
                        provider=provider,
                        end_date=self.now + timedelta(days=3),
                        is_active=True,
                    )
                    for user_id, key, provider in (
                        (16, alias, "payment"),
                        (17, trial_alias, "trial"),
                    )
                ]
            )
            await session.commit()
            plans = await get_user_subscription_plans(session, [16, 17], now=self.now)
            keys = await get_subscription_plan_tariff_keys(session, now=self.now)
            counts = await get_active_subscription_plan_counts(session, now=self.now)
        plan = admin_subscription_plan(self.settings, plans[16])
        assert plan is not None
        self.assertEqual(plan["tariff_key"], alias)
        self.assertEqual(plan["tariff_names"], {"en": "Retired"})
        self.assertTrue(plan["is_configured"])
        self.assertFalse(plan["is_enabled"])
        options = {row["tariff_key"]: row for row in admin_tariff_options(self.settings, keys)}
        self.assertTrue(options[alias]["is_configured"])
        self.assertFalse(options[alias]["is_enabled"])
        self.assertNotIn(trial_alias, options)
        distribution = admin_active_tariffs(self.settings, counts)
        alias_group = next(row for row in distribution if row["tariff_key"] == alias)
        self.assertEqual(alias_group["active_users"], 1)
        self.assertTrue(alias_group["is_configured"])
        self.assertFalse(alias_group["is_enabled"])
        self.assertEqual(await self._users(f"tariff:{alias}", active_only=True), ([16], 1))
        self.assertEqual(await self._users(f"tariff:{trial_alias}", active_only=True), ([], 0))
