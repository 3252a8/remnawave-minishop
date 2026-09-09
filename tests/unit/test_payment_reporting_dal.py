from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_reporting_dal


def test_complimentary_gifts_are_separate_from_cash_revenue(monkeypatch):
    session = AsyncMock(spec=AsyncSession)
    revenue = MagicMock()
    revenue.one.return_value = (100, 200, 300, 400, 1)
    gifts = MagicMock()
    gifts.one.return_value = (12, 8)
    session.execute.side_effect = [revenue, gifts]
    monkeypatch.setattr(
        payment_reporting_dal, "_daily_revenue_series_utc", AsyncMock(return_value=[])
    )
    result = asyncio.run(payment_reporting_dal.get_financial_statistics(session))
    assert result["all_time_revenue"] == 400
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
    assert "payments.funding_source = 'admin_grant'" in queries[1]
    assert "payments.status = 'succeeded'" in queries[1]
    assert "subscription_gifts.status != 'revoked'" in queries[1]


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> _FrozenDateTime:
        del tz
        return cls(2025, 1, 2, 12, tzinfo=UTC)


def test_all_time_daily_revenue_starts_at_first_matching_payment(monkeypatch) -> None:
    monkeypatch.setattr(payment_reporting_dal, "datetime", _FrozenDateTime)
    result = MagicMock()
    result.all.return_value = [
        (date(2024, 12, 31), 5),
        (date(2025, 1, 2), 7),
    ]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    series = asyncio.run(payment_reporting_dal._daily_revenue_series_utc(session, days=None))

    assert series == [
        {"date": "2024-12-31", "amount": 5.0},
        {"date": "2025-01-01", "amount": 0.0},
        {"date": "2025-01-02", "amount": 7.0},
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

    assert series == [{"date": "2025-01-02", "amount": 0.0}]
