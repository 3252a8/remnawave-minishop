from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.base import Base
from db.dal import partner_dal, partner_profile_reporting_dal
from db.partner_models import (
    PartnerClient,
    PartnerCommission,
    PartnerLedgerEntry,
    PartnerProfile,
    PartnerWithdrawal,
)


@pytest.mark.parametrize("page_size", [1, 50])
def test_profile_summaries_keep_query_count_constant_and_preserve_accounting(
    page_size: int,
) -> None:
    engine = create_engine("sqlite://")
    tables = [
        model.__table__
        for model in (
            PartnerProfile,
            PartnerClient,
            PartnerCommission,
            PartnerLedgerEntry,
            PartnerWithdrawal,
        )
    ]
    Base.metadata.create_all(engine, tables=tables)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(
            [
                PartnerProfile(
                    partner_id=i, partner_code=f"code-{i}", display_label_snapshot=f"Partner {i}"
                )
                for i in range(1, page_size + 1)
            ]
        )
        session.add_all(
            [
                PartnerClient(
                    partner_client_id=i,
                    partner_id=1,
                    public_client_id=f"client-{i}",
                    public_label_snapshot=f"Client {i}",
                    source="partner_web_link",
                    attributed_at=now,
                )
                for i in (1, 2)
            ]
        )
        session.add_all(
            [
                PartnerCommission(
                    commission_id=i,
                    partner_id=1,
                    partner_client_id=1,
                    gross_amount_minor=1000,
                    commission_amount_minor=100,
                    currency=currency,
                    currency_scale=2,
                    commission_bps_snapshot=1000,
                    status=status,
                    source_paid_at=now,
                    available_at=now,
                )
                for i, currency, status in [
                    (1, "RUB", "available"),
                    (2, "RUB", "pending"),
                    (3, "RUB", "reversed"),
                    (4, "RUB", "excluded"),
                    (5, "USD", "available"),
                ]
            ]
        )
        session.add_all(
            [
                PartnerLedgerEntry(
                    partner_id=1,
                    currency=currency,
                    currency_scale=2,
                    amount_minor=amount,
                    kind=kind,
                    state=state,
                    reference_type="test",
                    reference_id=str(i),
                    idempotency_key=f"entry-{i}",
                )
                for i, currency, amount, kind, state in [
                    (1, "RUB", 100, "commission_credit", "posted"),
                    (2, "RUB", 100, "commission_credit", "pending"),
                    (3, "RUB", -100, "commission_reversal", "posted"),
                    (4, "RUB", 500, "manual_adjustment", "posted"),
                    (5, "RUB", 999, "commission_credit", "void"),
                    (6, "USD", 200, "commission_credit", "posted"),
                ]
            ]
        )
        session.add_all(
            [
                PartnerWithdrawal(
                    partner_id=1,
                    method_id_snapshot="test",
                    method_type_snapshot="manual",
                    method_snapshot_json="{}",
                    debit_amount_minor=amount,
                    debit_currency=currency,
                    currency_scale=2,
                    requisites_key_id="test",
                    masked_requisites="test",
                    client_idempotency_key=f"withdrawal-{i}",
                    status=status,
                )
                for i, currency, amount, status in [
                    (1, "RUB", 25, "requested"),
                    (2, "RUB", 50, "processing"),
                    (3, "RUB", 900, "rejected"),
                    (4, "USD", 10, "requested"),
                ]
            ]
        )
        session.commit()
        async_session = AsyncMock(spec=AsyncSession)
        async_session.execute.side_effect = session.execute
        ids = list(range(1, page_size + 1))

        async def run() -> None:
            balances = await partner_profile_reporting_dal.balance_summaries_by_ids(
                async_session, ids
            )
            clients = await partner_profile_reporting_dal.client_summaries_by_ids(
                async_session, ids
            )
            metrics = await partner_profile_reporting_dal.currency_metrics_by_ids(
                async_session, ids, "rub"
            )
            assert async_session.execute.await_count == 4
            rub = next(item for item in balances[1] if item["currency"] == "RUB")
            assert rub == {
                "currency": "RUB",
                "currency_scale": 2,
                "available_minor": 500,
                "pending_minor": 100,
                "reserved_minor": 75,
                "lifetime_earned_minor": 100,
            }
            assert (
                next(item for item in balances[1] if item["currency"] == "USD")["reserved_minor"]
                == 10
            )
            assert clients[1] == {"clients_count": 2, "latest_client": "Client 2"}
            assert metrics[1] == {"payments_count": 3, "gross_minor": 3000, "earned_minor": 100}
            for partner_id in ids[1:]:
                assert balances[partner_id] == []
                assert clients[partner_id] == {"clients_count": 0, "latest_client": None}
                assert metrics[partner_id] == {
                    "payments_count": 0,
                    "gross_minor": 0,
                    "earned_minor": 0,
                }
            assert await partner_dal.balance_summaries(async_session, 1) == balances[1]
            assert await partner_dal.profile_currency_metrics(async_session, 1, "RUB") == metrics[1]
            count = async_session.execute.await_count
            assert (
                await partner_profile_reporting_dal.balance_summaries_by_ids(async_session, [])
                == {}
            )
            assert (
                await partner_profile_reporting_dal.client_summaries_by_ids(async_session, []) == {}
            )
            assert (
                await partner_profile_reporting_dal.currency_metrics_by_ids(
                    async_session, [], "RUB"
                )
                == {}
            )
            assert async_session.execute.await_count == count

        asyncio.run(run())
    engine.dispose()
