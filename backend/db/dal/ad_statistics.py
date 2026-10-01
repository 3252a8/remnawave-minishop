"""Batch compatibility statistics; separate currencies and preserve all receipts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.advertising_models import AdPurchaseAttribution
from db.models import AdAttribution, AdCampaign, Payment


def payment_campaign() -> Any:
    # A checkout explicitly recorded as unknown must stay unknown after a later contact.
    return case(
        (AdPurchaseAttribution.payment_id.is_not(None), AdPurchaseAttribution.campaign_id),
        else_=AdAttribution.ad_campaign_id,
    )


async def campaign_statistics(session: AsyncSession, ids: list[int]) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {
        ident: {"starts": 0, "trials": 0, "payers": 0, "revenue": 0.0, "revenue_by_currency": {}}
        for ident in ids
    }
    contacts = (
        await session.execute(
            select(
                AdAttribution.ad_campaign_id,
                func.count(AdAttribution.user_id),
                func.count(AdAttribution.trial_activated_at),
            )
            .join(AdCampaign, AdCampaign.ad_campaign_id == AdAttribution.ad_campaign_id)
            .where(
                AdAttribution.ad_campaign_id.in_(ids),
                or_(
                    AdCampaign.stats_reset_at.is_(None),
                    AdAttribution.first_start_at >= AdCampaign.stats_reset_at,
                ),
            )
            .group_by(AdAttribution.ad_campaign_id)
        )
    ).all()
    for ident, starts, trials in contacts:
        output[ident].update(starts=int(starts), trials=int(trials))
    campaign_expr = payment_campaign()
    payments = (
        await session.execute(
            select(
                campaign_expr,
                Payment.currency,
                func.sum(Payment.amount),
                func.count(
                    func.distinct(
                        case((Payment.sale_mode.not_like("balance_topup%"), Payment.user_id))
                    )
                ),
            )
            .outerjoin(
                AdPurchaseAttribution, AdPurchaseAttribution.payment_id == Payment.payment_id
            )
            .outerjoin(
                AdAttribution,
                AdAttribution.user_id == Payment.user_id,
            )
            .join(AdCampaign, AdCampaign.ad_campaign_id == campaign_expr)
            .where(
                campaign_expr.in_(ids),
                Payment.status == "succeeded",
                Payment.funding_source == "external",
                Payment.amount > 0,
                or_(
                    AdPurchaseAttribution.payment_id.is_not(None),
                    Payment.created_at >= AdAttribution.first_start_at,
                ),
                or_(
                    AdCampaign.stats_reset_at.is_(None),
                    AdAttribution.first_start_at >= AdCampaign.stats_reset_at,
                ),
            )
            .group_by(campaign_expr, Payment.currency)
        )
    ).all()
    # Payers across currencies are counted separately below, rather than summing duplicates.
    for ident, currency, amount, _ in payments:
        output[ident]["revenue_by_currency"][currency] = float(amount or 0)
        if currency == "RUB":
            output[ident]["revenue"] = float(amount or 0)
    payers = (
        await session.execute(
            select(campaign_expr, func.count(func.distinct(Payment.user_id)))
            .outerjoin(
                AdPurchaseAttribution,
                AdPurchaseAttribution.payment_id == Payment.payment_id,
            )
            .outerjoin(AdAttribution, AdAttribution.user_id == Payment.user_id)
            .join(
                AdCampaign,
                AdCampaign.ad_campaign_id == campaign_expr,
            )
            .where(
                campaign_expr.in_(ids),
                Payment.status == "succeeded",
                or_(
                    Payment.amount > 0,
                    Payment.user_balance_amount_minor > 0,
                    Payment.partner_balance_amount_minor > 0,
                    Payment.promo_code_id.is_not(None),
                ),
                Payment.sale_mode.not_like("balance_topup%"),
                or_(
                    AdPurchaseAttribution.payment_id.is_not(None),
                    Payment.created_at >= AdAttribution.first_start_at,
                ),
                or_(
                    AdCampaign.stats_reset_at.is_(None),
                    AdAttribution.first_start_at >= AdCampaign.stats_reset_at,
                ),
            )
            .group_by(campaign_expr)
        )
    ).all()
    for ident, count in payers:
        output[ident]["payers"] = int(count)
    return output
