"""Bounded, batched profile summaries for admin lists and individual profiles."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.partner_models import (
    PartnerClient,
    PartnerCommission,
    PartnerLedgerEntry,
    PartnerWithdrawal,
)


async def balance_summaries_by_ids(
    session: AsyncSession,
    partner_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    if not partner_ids:
        return {}
    ledger_rows = (
        await session.execute(
            select(
                PartnerLedgerEntry.partner_id,
                PartnerLedgerEntry.currency,
                PartnerLedgerEntry.currency_scale,
                func.coalesce(
                    func.sum(
                        case(
                            (PartnerLedgerEntry.state == "posted", PartnerLedgerEntry.amount_minor),
                            else_=0,
                        )
                    ),
                    0,
                ).label("available"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    PartnerLedgerEntry.state == "pending",
                                    PartnerLedgerEntry.kind == "commission_credit",
                                ),
                                PartnerLedgerEntry.amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("pending"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    PartnerLedgerEntry.kind.in_(
                                        ("commission_credit", "commission_reversal")
                                    ),
                                    PartnerLedgerEntry.state != "void",
                                ),
                                PartnerLedgerEntry.amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("lifetime_earned"),
            )
            .where(PartnerLedgerEntry.partner_id.in_(partner_ids))
            .group_by(
                PartnerLedgerEntry.partner_id,
                PartnerLedgerEntry.currency,
                PartnerLedgerEntry.currency_scale,
            )
        )
    ).all()
    active_reserves = {
        (int(row[0]), str(row[1]).upper()): int(row[2] or 0)
        for row in (
            await session.execute(
                select(
                    PartnerWithdrawal.partner_id,
                    PartnerWithdrawal.debit_currency,
                    func.coalesce(func.sum(PartnerWithdrawal.debit_amount_minor), 0),
                )
                .where(
                    PartnerWithdrawal.partner_id.in_(partner_ids),
                    PartnerWithdrawal.status.in_(("requested", "processing")),
                )
                .group_by(PartnerWithdrawal.partner_id, PartnerWithdrawal.debit_currency)
            )
        ).all()
    }
    summaries: dict[int, list[dict[str, Any]]] = {partner_id: [] for partner_id in partner_ids}
    for row in ledger_rows:
        summaries[int(row.partner_id)].append(
            {
                "currency": str(row.currency).upper(),
                "currency_scale": int(row.currency_scale),
                "available_minor": int(row.available or 0),
                "pending_minor": int(row.pending or 0),
                "reserved_minor": active_reserves.get(
                    (int(row.partner_id), str(row.currency).upper()), 0
                ),
                "lifetime_earned_minor": int(row.lifetime_earned or 0),
            }
        )
    return summaries


async def currency_metrics_by_ids(
    session: AsyncSession,
    partner_ids: list[int],
    currency: str,
) -> dict[int, dict[str, int]]:
    if not partner_ids:
        return {}
    rows = (
        await session.execute(
            select(
                PartnerCommission.partner_id,
                func.coalesce(
                    func.sum(
                        case(
                            (PartnerCommission.status != "excluded", 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("payments_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                PartnerCommission.status != "excluded",
                                PartnerCommission.gross_amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("gross"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                PartnerCommission.status == "reversed",
                                -PartnerCommission.commission_amount_minor,
                            ),
                            (
                                PartnerCommission.status != "excluded",
                                PartnerCommission.commission_amount_minor,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("earned"),
            )
            .where(
                PartnerCommission.partner_id.in_(partner_ids),
                func.upper(PartnerCommission.currency) == currency.upper(),
            )
            .group_by(PartnerCommission.partner_id)
        )
    ).all()
    summaries = {
        partner_id: {"payments_count": 0, "gross_minor": 0, "earned_minor": 0}
        for partner_id in partner_ids
    }
    for row in rows:
        summaries[int(row.partner_id)] = {
            "payments_count": int(row.payments_count or 0),
            "gross_minor": int(row.gross or 0),
            "earned_minor": int(row.earned or 0),
        }
    return summaries


async def client_summaries_by_ids(
    session: AsyncSession, partner_ids: list[int]
) -> dict[int, dict[str, Any]]:
    if not partner_ids:
        return {}
    ranked = (
        select(
            PartnerClient.partner_id,
            PartnerClient.public_label_snapshot.label("latest_client"),
            func.count().over(partition_by=PartnerClient.partner_id).label("clients_count"),
            func.row_number()
            .over(
                partition_by=PartnerClient.partner_id,
                order_by=(
                    PartnerClient.attributed_at.desc(),
                    PartnerClient.partner_client_id.desc(),
                ),
            )
            .label("position"),
        )
        .where(PartnerClient.partner_id.in_(partner_ids))
        .subquery()
    )
    rows = (await session.execute(select(ranked).where(ranked.c.position == 1))).all()
    summaries: dict[int, dict[str, Any]] = {
        partner_id: {"clients_count": 0, "latest_client": None} for partner_id in partner_ids
    }
    for row in rows:
        summaries[int(row.partner_id)] = {
            "clients_count": int(row.clients_count),
            "latest_client": str(row.latest_client),
        }
    return summaries
