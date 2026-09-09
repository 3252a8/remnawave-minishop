import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine, text

from bot.payment_providers.shared.common import build_payment_record_payload
from bot.services.promo_effects import PromoEffects
from config.subscription_periods import with_period_days
from db.dal.payment_periods import normalize_payment_period
from db.migrator.chain_0075_period_days import _migration_0075_add_period_days
from db.models import Payment


@pytest.mark.parametrize("days,alias", [(7, None), (30, 1), (360, None), (365, 12), (730, 24)])
def test_order_duration_survives_provider_callback_and_orm(days: int, alias: int | None) -> None:
    data = build_payment_record_payload(
        user_id=42,
        amount=100,
        currency="RUB",
        status="pending",
        description="test",
        months=days,
        provider="test",
        sale_mode=with_period_days("subscription@base", days),
    )
    order = Payment(**normalize_payment_period(data))
    assert order.subscription_duration_days == days
    assert order.subscription_duration_months == alias
    assert order.period_semantics == "fixed_days"


def test_legacy_pending_order_keeps_its_calendar_semantics() -> None:
    payload = {"sale_mode": "subscription@base", "subscription_duration_months": 12}
    assert normalize_payment_period(payload) == payload
    with pytest.raises(ValueError, match="conflicts"):
        normalize_payment_period(
            {**payload, "sale_mode": "subscription@base|d365", "subscription_duration_days": 360}
        )
    with pytest.raises(ValueError, match="non-subscription"):
        normalize_payment_period(
            {"sale_mode": "traffic_package@base", "subscription_duration_days": 7}
        )


def test_promo_minimum_distinguishes_360_and_365_without_changing_bonus() -> None:
    effects = PromoEffects(bonus_days=7, min_subscription_days=365)
    assert not effects.meets_threshold(
        sale_mode_base="subscription", months=None, duration_days=360, traffic_gb=None
    )
    assert effects.meets_threshold(
        sale_mode_base="subscription", months=None, duration_days=365, traffic_gb=None
    )
    assert effects.bonus_days == 7


def test_migration_is_repeatable_and_does_not_shift_active_dates_or_daily_grants() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE subscriptions (duration_months INTEGER, end_date TEXT)")
        )
        connection.execute(
            text("CREATE TABLE payments (sale_mode TEXT, subscription_duration_months INTEGER)")
        )
        end_date = datetime(2027, 1, 31, 12, tzinfo=UTC).isoformat()
        connection.execute(
            text("INSERT INTO subscriptions VALUES (12, :end_date), (0, :end_date)"),
            {"end_date": end_date},
        )
        connection.execute(
            text(
                "INSERT INTO payments VALUES ('subscription|bot', 12), ('traffic_package@base', 12)"
            )
        )
        _migration_0075_add_period_days(connection)
        _migration_0075_add_period_days(connection)
        rows = connection.execute(
            text("SELECT duration_months, duration_days, end_date FROM subscriptions")
        ).all()
        assert rows == [(12, 365, end_date), (0, None, end_date)]
        assert connection.execute(
            text("SELECT subscription_duration_days, period_semantics FROM payments")
        ).all() == [(365, "calendar_months"), (None, None)]
    engine.dispose()


@pytest.mark.parametrize("days,legacy_alias", [(7, None), (30, 1), (360, None), (365, 12)])
def test_old_clients_never_receive_unrepresentable_periods(
    days: int, legacy_alias: int | None
) -> None:
    from aiohttp.test_utils import make_mocked_request

    from bot.app.web.webapp.period_contracts import periods_for_client

    plan = {"duration_days": days, "months": legacy_alias}
    old = make_mocked_request("GET", "/api/subscription")
    new = make_mocked_request("GET", "/api/subscription", headers={"X-Billing-Period-Unit": "day"})
    assert periods_for_client(new, [plan]) == [plan]
    assert periods_for_client(old, [plan]) == ([plan] if legacy_alias else [])


def test_new_and_old_bot_back_buttons_keep_explicit_units() -> None:
    from bot.keyboards.inline.user_keyboards_context import payment_methods_back_callback

    assert (
        payment_methods_back_callback("365", "subscription@base|d365|bot")
        == "tariff:period:base:d365:bot"
    )
    assert (
        payment_methods_back_callback("12", "subscription@base|bot") == "tariff:period:base:12:bot"
    )


def test_payment_link_message_uses_days_for_fixed_period() -> None:
    from bot.payment_providers.shared.callbacks import (
        PaymentCallbackParts,
        payment_link_message_text,
    )

    calls: list[tuple[str, dict[str, object]]] = []

    def translator(key: str, **kwargs: object) -> str:
        calls.append((key, kwargs))
        return key

    text = payment_link_message_text(
        translator,
        PaymentCallbackParts(months=90, price=100, sale_mode="subscription@base|d90"),
    )

    assert text == "payment_link_message_days"
    assert calls == [("payment_link_message_days", {"days": 90})]


def test_corrupt_or_overflowing_periods_fail_before_payment() -> None:
    from types import SimpleNamespace

    from config.subscription_periods import checkout_duration_days

    with pytest.raises(ValueError, match="out of range"):
        checkout_duration_days(SimpleNamespace(), 2147483647, "subscription@base|d2147483647")


def test_migration_backfills_provider_schedules_and_keeps_daily_bonus_values() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE tribute_entitlements (duration_months INTEGER)"))
        connection.execute(text("INSERT INTO tribute_entitlements VALUES (12)"))
        connection.execute(
            text("CREATE TABLE promo_codes (min_subscription_months INTEGER, bonus_days INTEGER)")
        )
        connection.execute(text("INSERT INTO promo_codes VALUES (12, 7)"))
        _migration_0075_add_period_days(connection)
        assert connection.execute(
            text("SELECT duration_days, period_semantics FROM tribute_entitlements")
        ).one() == (365, "provider_managed")
        assert connection.execute(
            text("SELECT min_subscription_days, bonus_days FROM promo_codes")
        ).one() == (365, 7)
    engine.dispose()


def test_subscription_terms_preserve_referral_values_after_catalog_changes() -> None:
    from types import SimpleNamespace

    from bot.services.subscription_order_terms import (
        freeze_subscription_terms,
        read_subscription_terms,
    )
    from config.tariffs_config import TariffsConfig

    catalog = TariffsConfig.model_validate(
        {
            "schema_version": 2,
            "period_unit": "day",
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
                    "referral_bonus_days_referee": {"7": 1},
                }
            ],
        }
    )
    snapshot = freeze_subscription_terms(
        SimpleNamespace(tariffs_config=catalog), "subscription@base|d7"
    )
    catalog.tariffs.clear()
    terms = read_subscription_terms(
        SimpleNamespace(
            subscription_terms_snapshot=snapshot, subscription_duration_days=7, tariff_key="base"
        )
    )
    assert terms is not None
    assert (terms.duration_days, terms.inviter_days, terms.referee_days) == (7, 3, 1)
    assert terms.tariff is not None and terms.tariff.monthly_gb == 100


def test_recurring_snapshot_replay_keeps_days_and_supports_old_versions() -> None:
    import json

    from bot.payment_providers.shared.recurring import RecurringRequestSnapshot

    raw = {
        "amount": 100,
        "currency": "RUB",
        "months": 1,
        "sale_mode": "subscription",
        "description": "old invoice",
        "metadata": {},
        "hwid_quote": None,
        "entitlement_context_snapshot": None,
    }
    old = RecurringRequestSnapshot.from_json(json.dumps(raw))
    assert old.duration_days is None
    assert RecurringRequestSnapshot.from_json(old.to_json()) == old
    raw.update(
        {
            "version": 2,
            "months": 0,
            "duration_days": 7,
            "sale_mode": "subscription|d7",
            "subscription_terms_snapshot": "frozen terms",
        }
    )
    new = RecurringRequestSnapshot.from_json(json.dumps(raw))
    assert RecurringRequestSnapshot.from_json(new.to_json()) == new
    assert new.duration_days == 7


def test_migration_does_not_turn_old_imported_trials_into_paid_periods() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE subscriptions (duration_months INTEGER, provider TEXT, "
                "status_from_panel TEXT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO subscriptions VALUES (1, 'trial', 'ACTIVE'), "
                "(1, 'promo', 'ACTIVE_BONUS'), (1, 'test', 'ACTIVE')"
            )
        )
        _migration_0075_add_period_days(connection)
        assert connection.execute(
            text("SELECT duration_days FROM subscriptions ORDER BY provider")
        ).scalars().all() == [None, 30, None]
    engine.dispose()


@pytest.mark.parametrize("billing_model", ["subscription", "trial", "traffic", None])
def test_quote_preserves_trial_days_and_ignores_traffic_expiry(
    monkeypatch: pytest.MonkeyPatch, billing_model: str | None
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from bot.app.web.webapp import billing_checkout_quote
    from bot.services.subscription_service_impl.core import SubscriptionService

    end_date = datetime(2030, 1, 31, tzinfo=UTC)
    active = SimpleNamespace(end_date=end_date) if billing_model is not None else None
    lookup = AsyncMock(return_value=active)
    monkeypatch.setattr(
        billing_checkout_quote.subscription_dal, "get_active_subscription_by_user_id", lookup
    )
    service = Mock(spec=SubscriptionService)
    service._subscription_billing_model.return_value = billing_model
    session = AsyncMock(spec=AsyncSession)

    async def check_quote() -> None:
        start = await billing_checkout_quote._resolve_quote_period_start(
            session, 42, None, service, None
        )
        assert start == (end_date if billing_model in {"subscription", "trial"} else None)
        lookup.assert_awaited_once()
        lookup.reset_mock()
        assert (
            await billing_checkout_quote._resolve_quote_period_start(
                session, 42, None, service, end_date
            )
            == end_date
        )
        lookup.assert_not_awaited()

    asyncio.run(check_quote())
