from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_reporting_dal
from db.models import Payment


def test_first_subscription_count_excludes_other_purchase_kinds():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from db.dal.payment_dal import count_user_succeeded_payments
    from db.models import Payment, User

    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(
                    lambda c: User.metadata.create_all(
                        c, tables=[User.__table__, Payment.__table__]
                    )
                )
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                session.add(User(user_id=42))
                for index, mode in enumerate(
                    ["balance_topup", "gift@standard", "traffic", "subscription"]
                ):
                    session.add(
                        Payment(
                            payment_id=index + 1,
                            user_id=42,
                            sale_mode=mode,
                            status="succeeded",
                            amount=0 if mode == "subscription" else 100,
                            currency="RUB",
                            provider="test",
                        )
                    )
                await session.flush()
                assert (
                    await count_user_succeeded_payments(
                        session, 42, qualifying_subscription_only=True
                    )
                    == 0
                )
                session.add(
                    Payment(
                        payment_id=5,
                        user_id=42,
                        sale_mode="subscription@standard",
                        status="succeeded",
                        amount=100,
                        currency="RUB",
                        provider="user_balance",
                    )
                )
                await session.flush()
                assert (
                    await count_user_succeeded_payments(
                        session, 42, qualifying_subscription_only=True
                    )
                    == 1
                )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_subscription_mrr_uses_one_paid_period_per_live_plan_and_keeps_currencies_separate():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from db.models import Subscription, User

    now = datetime(2026, 11, 11, tzinfo=UTC)

    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(
                    lambda c: User.metadata.create_all(
                        c, tables=[User.__table__, Payment.__table__, Subscription.__table__]
                    )
                )
            async with async_sessionmaker(engine)() as session:
                for user_id in range(1, 10):
                    session.add(User(user_id=user_id))
                    session.add(
                        Subscription(
                            subscription_id=user_id,
                            user_id=user_id,
                            panel_user_uuid=f"panel-{user_id}",
                            start_date=now - timedelta(days=90),
                            end_date=now + timedelta(days=300 if user_id != 4 else 0),
                            provider="trial" if user_id == 5 else "test",
                            is_active=user_id != 6,
                        )
                    )
                session.add(
                    Subscription(
                        subscription_id=11,
                        user_id=1,
                        panel_user_uuid="panel-overlap",
                        start_date=now - timedelta(days=120),
                        end_date=now + timedelta(days=100),
                        provider="test",
                        is_active=True,
                    )
                )

                def payment(user_id: int, age: int, **fields: object) -> Payment:
                    defaults: dict[str, object] = {
                        "user_id": user_id,
                        "provider": "test",
                        "status": "succeeded",
                        "sale_mode": "subscription@standard",
                        "amount": 1200,
                        "subscription_duration_months": 12,
                        "currency": "RUB",
                        "created_at": now - timedelta(days=age),
                    }
                    return Payment(**(defaults | fields))

                session.add_all(
                    [
                        payment(1, 60, amount=3600),
                        payment(1, 45),  # Annual prepayment still contributes 100/month.
                        payment(1, 20, renewal_subscription_id=11, amount=6000),
                        payment(1, 2, status="refunded"),
                        payment(1, 1, sale_mode="traffic"),
                        payment(
                            2,
                            45,
                            amount=300,
                            funding_source="internal_user_balance",
                            period_semantics="fixed_days",
                            subscription_duration_months=1,
                            subscription_duration_days=60,
                        ),
                        payment(3, 45),
                        payment(3, 20, amount=240, currency="USD"),
                        payment(4, 5),  # Expired at the reporting instant.
                        payment(5, 5),  # Trial.
                        payment(6, 5),  # Disabled despite its future end date.
                        payment(7, 92),  # From before the active subscription.
                        payment(8, 5, funding_source="admin_grant"),
                        payment(9, 5, subscription_duration_months=None),
                        payment(9, -1),  # Not yet settled at the reporting instant.
                    ]
                )
                await session.flush()

                for currency, expected in (("RUB", 250), ("USD", 20), ("EUR", 0)):
                    assert (
                        await payment_reporting_dal.get_active_subscription_mrr(
                            session, currency=currency, now=now
                        )
                        == expected
                    )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_complimentary_gifts_are_separate_from_cash_revenue(monkeypatch):
    session = AsyncMock(spec=AsyncSession)
    revenue = MagicMock()
    revenue.one.return_value = (100, 200, 300, 3.5, 7, 10.5, 400, 14, 1)
    gifts = MagicMock()
    gifts.one.return_value = (12, 8)
    session.execute.side_effect = [revenue, gifts]
    monkeypatch.setattr(
        payment_reporting_dal, "_daily_revenue_series_utc", AsyncMock(return_value=[])
    )
    result = asyncio.run(
        payment_reporting_dal.get_financial_statistics(
            session,
            currency="RUB",
            provider_fee_rates={"yookassa": {"": 3.5, "sbp": 0, "bank_card": 5}},
        )
    )
    assert result["all_time_revenue"] == 400
    assert result["today_fees"] == 3.5
    assert result["all_time_fees"] == 14
    assert result["today_payments_count"] == 1
    assert result["admin_gifts_count"] == 12
    assert result["admin_gifts_activated_count"] == 8
    queries = [
        str(
            call.args[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        for call in session.execute.await_args_list
    ]
    assert "payments.funding_source = 'external'" in queries[0]
    assert "payments.currency = 'RUB'" in queries[0]
    assert "coalesce(payments.provider_fee_amount," in queries[0]
    assert "payments.provider_method = 'sbp') THEN 0.0" in queries[0]
    assert "payments.provider_method = 'bank_card') THEN 0.05" in queries[0]
    assert "CASE payments.provider WHEN 'yookassa' THEN 0.035 ELSE 0.0 END" in queries[0]
    assert "payments.funding_source = 'admin_grant'" in queries[1]
    assert "payments.status = 'succeeded'" in queries[1]
    assert "subscription_gifts.status != 'revoked'" in queries[1]


def test_reporting_rates_override_shared_and_method_specific_provider_keys(monkeypatch):
    from bot.payment_providers import registry
    from bot.payment_providers.base import ProviderConfigBundle
    from bot.payment_providers.platega.config import PlategaConfig
    from bot.payment_providers.rollypay.config import RollyPayConfig

    monkeypatch.setattr(
        registry,
        "_provider_configs",
        {
            "platega_service": ProviderConfigBundle(
                config=PlategaConfig(
                    REPORTING_FEE_PERCENT=3.5,
                    SBP_REPORTING_FEE_PERCENT=5,
                    CRYPTO_REPORTING_FEE_PERCENT=0,
                )
            ),
            "rollypay_service": ProviderConfigBundle(
                config=RollyPayConfig(
                    REPORTING_FEE_PERCENT=4,
                    CRYPTO_REPORTING_FEE_PERCENT=1,
                )
            ),
        },
    )
    monkeypatch.setattr(registry, "_reporting_fee_sources", registry._build_reporting_fee_sources())
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = []
    rates = asyncio.run(payment_reporting_dal.load_reporting_fee_rates(session))
    assert rates["platega"] == {"": 3.5, "sbp": 5, "crypto": 0}
    assert rates["rollypay"] == {"": 4}
    assert rates["rollypay_crypto"] == {"": 1}
    assert rates["rollypay_sbp"] == {"": 4}


def test_saved_fee_survives_rate_change_and_explicit_zero(monkeypatch):
    from bot.payment_providers import registry

    base_key = "PLATEGA_REPORTING_FEE_PERCENT"
    method_key = "PLATEGA_SBP_REPORTING_FEE_PERCENT"
    monkeypatch.setattr(
        registry,
        "_reporting_fee_sources",
        {"platega": {"": [(base_key, None)], "sbp": [(method_key, None)]}},
    )
    overrides = {base_key: 3.5, method_key: 5.0}
    load = AsyncMock(return_value=overrides)
    monkeypatch.setattr(payment_reporting_dal, "get_override_values", load)
    session = AsyncMock(spec=AsyncSession)

    def payment() -> Payment:
        return Payment(
            provider="platega", provider_method="sbp", funding_source="external", amount=1000
        )

    first = payment()
    second = payment()
    zero = payment()
    missing = payment()

    async def scenario() -> None:
        await payment_reporting_dal.snapshot_payment_provider_fee(session, first)
        overrides[method_key] = 1.5
        await payment_reporting_dal.snapshot_payment_provider_fee(session, first)
        await payment_reporting_dal.snapshot_payment_provider_fee(session, second)
        overrides[method_key] = 0
        await payment_reporting_dal.snapshot_payment_provider_fee(session, zero)
        overrides.clear()
        await payment_reporting_dal.snapshot_payment_provider_fee(session, zero)
        await payment_reporting_dal.snapshot_payment_provider_fee(session, missing)

    asyncio.run(scenario())
    assert first.provider_fee_amount == 50
    assert second.provider_fee_amount == 15
    assert zero.provider_fee_amount == 0
    assert missing.provider_fee_amount is None
    assert session.flush.await_count == 3
    assert load.await_count == 4


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> _FrozenDateTime:
        del tz
        return cls(2025, 1, 2, 12, tzinfo=UTC)


def test_all_time_daily_revenue_starts_at_first_matching_payment(monkeypatch) -> None:
    monkeypatch.setattr(payment_reporting_dal, "datetime", _FrozenDateTime)
    result = MagicMock()
    result.all.return_value = [
        (date(2024, 12, 31), 5, 0.25),
        (date(2025, 1, 2), 7, 0.7),
    ]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    series = asyncio.run(payment_reporting_dal._daily_revenue_series_utc(session, days=None))

    assert series == [
        {"date": "2024-12-31", "amount": 5.0, "fees": 0.25},
        {"date": "2025-01-01", "amount": 0.0, "fees": 0.0},
        {"date": "2025-01-02", "amount": 7.0, "fees": 0.7},
    ]
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "payments.created_at >=" not in sql


def test_all_time_daily_revenue_without_payments_returns_today(monkeypatch) -> None:
    monkeypatch.setattr(payment_reporting_dal, "datetime", _FrozenDateTime)
    result = MagicMock()
    result.all.return_value = []
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    series = asyncio.run(payment_reporting_dal._daily_revenue_series_utc(session, days=None))

    assert series == [{"date": "2025-01-02", "amount": 0.0, "fees": 0.0}]
