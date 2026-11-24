from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.base import Base
from db.dal import partner_reporting_dal
from db.partner_models import PartnerApplication, PartnerWithdrawal


@pytest.mark.parametrize(
    ("sort", "sql_fragment"),
    [
        ("user_asc", "display_label_snapshot"),
        ("status_desc", "partner_profiles.status"),
        ("rate_desc", "commission_bps"),
        ("clients_desc", "clients_count"),
        ("gross_desc", "gross_minor"),
        ("earned_desc", "earned_minor"),
        ("available_desc", "available_minor"),
        ("", "clients_count"),
    ],
)
def test_partner_list_sorting_compiles_for_postgres(sort: str, sql_fragment: str) -> None:
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = []
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [count_result, rows_result]

    profiles, total = asyncio.run(
        partner_reporting_dal.list_profiles(
            session,
            status=None,
            search=None,
            currency="RUB",
            sort=sort,
            limit=25,
            offset=0,
        )
    )

    assert profiles == []
    assert total == 0
    assert session.execute.await_count == 2
    list_call = session.execute.await_args_list[1]
    statement = list_call.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY" in compiled
    assert sql_fragment in compiled


def test_partner_overview_all_time_has_no_date_cutoff() -> None:
    commission_result = MagicMock()
    commission_result.all.return_value = [
        SimpleNamespace(day=date(2023, 5, 4), gross=1000, commission=100),
    ]
    payout_result = MagicMock()
    payout_result.all.return_value = [
        SimpleNamespace(day=date(2024, 6, 5), paid=75),
    ]
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [commission_result, payout_result]

    series = asyncio.run(partner_reporting_dal.overview_series(session, currency="RUB", since=None))

    assert series == [
        {
            "date": "2023-05-04",
            "gross_minor": 1000,
            "commission_minor": 100,
            "paid_minor": 0,
        },
        {
            "date": "2024-06-05",
            "gross_minor": 0,
            "commission_minor": 0,
            "paid_minor": 75,
        },
    ]
    commission_sql = str(
        session.execute.await_args_list[0].args[0].compile(dialect=postgresql.dialect())
    )
    payout_sql = str(
        session.execute.await_args_list[1].args[0].compile(dialect=postgresql.dialect())
    )
    assert "partner_commissions.created_at >=" not in commission_sql
    assert "partner_withdrawals.paid_at >=" not in payout_sql


def test_workspace_counts_include_all_applications_and_only_open_withdrawals_in_currency() -> (
    None
):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[PartnerApplication.__table__, PartnerWithdrawal.__table__]
    )
    with Session(engine) as db:
        session = AsyncMock(spec=AsyncSession)
        session.execute.side_effect = db.execute
        db.add(PartnerApplication(display_label_snapshot="Reviewed", message="", status="approved"))
        db.flush()
        assert asyncio.run(partner_reporting_dal.workspace_counts(session, currency="USD")) == {
            "pending_applications": 0,
            "has_applications": True,
            "open_withdrawals": 0,
        }
        db.add_all(
            PartnerApplication(display_label_snapshot="Applicant", message="", status="pending")
            for _ in range(7)
        )
        for index, (status, currency) in enumerate(
            [
                ("processing", "RUB"),
                ("requested", "RUB"),
                ("paid", "RUB"),
                ("requested", "USD"),
            ]
        ):
            db.add(
                PartnerWithdrawal(
                    partner_id=1,
                    method_id_snapshot="test",
                    method_type_snapshot="manual",
                    method_snapshot_json="{}",
                    debit_amount_minor=1,
                    debit_currency=currency,
                    currency_scale=2,
                    requisites_key_id="test",
                    masked_requisites="",
                    client_idempotency_key=str(index),
                    status=status,
                )
            )
        db.flush()
        assert asyncio.run(partner_reporting_dal.workspace_counts(session, currency="rub")) == {
            "pending_applications": 7,
            "has_applications": True,
            "open_withdrawals": 2,
        }
