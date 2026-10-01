"""Currency-separated cash, product purchases and acquisition cohorts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.advertising_models import (
    AdExternalMetric,
    AdImportBatch,
    AdPurchaseAttribution,
    AdSpendEntry,
    AdTouchpoint,
)
from db.dal.ad_statistics import payment_campaign
from db.models import AdAttribution, AdCampaign, Payment

from .capture import utc
from .validation import currency_scale


def payment_minor(payment: Payment) -> int:
    return int(
        (Decimal(str(payment.amount or 0)) * 10 ** currency_scale(str(payment.currency))).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator / denominator) if denominator else None


def bucket(currency: str) -> dict[str, Any]:
    return {
        "currency": currency,
        "scale": currency_scale(currency),
        "cash_minor": 0,
        "product_minor": 0,
        "refund_minor": 0,
        "net_minor": 0,
        "first_purchase_minor": 0,
        "repeat_purchase_minor": 0,
        "spend_minor": None,
        "purchases": 0,
        "roas": None,
        "cac_minor": None,
        "average_order_minor": None,
        "d7_minor": 0,
        "d30_minor": 0,
        "d90_minor": 0,
    }


async def campaign_report(
    session: AsyncSession,
    campaign: AdCampaign,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    period_mode: str = "events",
    link_id: int | None = None,
    evidence: str | None = None,
    channel: str | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    selected_currency = currency
    campaign_id = int(campaign.ad_campaign_id)
    now = datetime.now(UTC)
    start = utc(start) if start else None
    end = utc(end) if end else None

    def in_period(moment: datetime | None) -> bool:
        return (
            moment is not None
            and (start is None or utc(moment) >= start)
            and (end is None or utc(moment) < end)
        )

    acquired_conditions = [AdAttribution.ad_campaign_id == campaign_id]
    if start:
        acquired_conditions.append(AdAttribution.first_start_at >= start)
    if end:
        acquired_conditions.append(AdAttribution.first_start_at < end)
    cohort_ids = select(AdAttribution.user_id).where(*acquired_conditions)
    first_source_ids = select(AdAttribution.user_id).where(
        AdAttribution.ad_campaign_id == campaign_id
    )
    cohort_counts = (
        await session.execute(
            select(
                func.count(),
                *[
                    func.sum(
                        case(
                            (AdAttribution.first_start_at <= now - timedelta(days=days), 1), else_=0
                        )
                    )
                    for days in (7, 30, 90)
                ],
            )
            .select_from(AdAttribution)
            .where(*acquired_conditions)
        )
    ).one()
    contact_conditions = [AdTouchpoint.campaign_id == campaign_id]
    if period_mode == "cohort":
        contact_conditions.append(AdTouchpoint.user_id.in_(cohort_ids))
    else:
        if start:
            contact_conditions.append(AdTouchpoint.occurred_at >= start)
        if end:
            contact_conditions.append(AdTouchpoint.occurred_at < end)
    if link_id:
        contact_conditions.append(AdTouchpoint.link_id == link_id)
    if evidence:
        contact_conditions.append(AdTouchpoint.evidence == evidence)
    if channel:
        contact_conditions.append(AdTouchpoint.channel == channel)
    inputs = func.coalesce(
        AdTouchpoint.visit_id,
        case(
            (AdTouchpoint.user_id.is_not(None), "user:" + cast(AdTouchpoint.user_id, String)),
            else_="event:" + cast(AdTouchpoint.id, String),
        ),
    )
    contact_counts = (
        await session.execute(
            select(
                func.count(),
                func.count(
                    func.distinct(
                        case(
                            (
                                (AdTouchpoint.is_new_user.is_(True))
                                & AdTouchpoint.user_id.in_(first_source_ids),
                                AdTouchpoint.user_id,
                            )
                        )
                    )
                ),
                func.count(
                    func.distinct(case((AdTouchpoint.is_new_user.is_(False), AdTouchpoint.user_id)))
                ),
                func.count(func.distinct(inputs)),
            )
            .select_from(AdTouchpoint)
            .where(*contact_conditions)
        )
    ).one()
    trial_conditions = [
        AdAttribution.ad_campaign_id == campaign_id,
        AdAttribution.trial_activated_at.is_not(None),
    ]
    if period_mode == "cohort":
        trial_conditions.extend(acquired_conditions)
    else:
        if start:
            trial_conditions.append(AdAttribution.trial_activated_at >= start)
        if end:
            trial_conditions.append(AdAttribution.trial_activated_at < end)
    trial_count = int(
        (
            await session.execute(
                select(func.count()).select_from(AdAttribution).where(*trial_conditions)
            )
        ).scalar()
        or 0
    )
    payment_conditions = []
    if link_id:
        payment_conditions.append(AdPurchaseAttribution.link_id == link_id)
    if evidence:
        payment_conditions.append(
            func.coalesce(AdPurchaseAttribution.evidence, "legacy_bot_start") == evidence
        )
    if channel:
        payment_conditions.append(AdTouchpoint.channel == channel)
    if currency:
        payment_conditions.append(
            func.coalesce(AdPurchaseAttribution.currency, Payment.currency) == currency
        )
    rows = await session.stream(
        select(
            Payment,
            AdPurchaseAttribution,
            AdAttribution.ad_campaign_id,
            AdAttribution.first_start_at,
        )
        .outerjoin(
            AdPurchaseAttribution,
            AdPurchaseAttribution.payment_id == Payment.payment_id,
        )
        .outerjoin(AdTouchpoint, AdTouchpoint.id == AdPurchaseAttribution.touchpoint_id)
        .outerjoin(AdAttribution, AdAttribution.user_id == Payment.user_id)
        .where(
            Payment.user_id.in_(cohort_ids)
            if period_mode == "cohort"
            else or_(payment_campaign() == campaign_id, Payment.user_id.in_(cohort_ids)),
            Payment.status.in_(("succeeded", "refunded", "reversed")),
            *payment_conditions,
        )
        .order_by(Payment.created_at, Payment.payment_id)
    )
    currencies: dict[str, dict[str, Any]] = {}
    payers: set[int] = set()
    first_payers: set[int] = set()
    currency_first_payers: dict[str, set[int]] = {}
    purchase_count = 0
    legacy_payment_count = 0
    async for payment, decision, acquisition_campaign, acquisition_date in rows:
        uid = int(payment.user_id)
        date = decision.succeeded_at if decision and decision.succeeded_at else payment.created_at
        belongs = acquisition_campaign == campaign_id
        cohort_member = belongs and in_period(acquisition_date)
        if decision is None and belongs and utc(payment.created_at) < utc(acquisition_date):
            continue
        attributed_here = decision.campaign_id == campaign_id if decision else belongs
        visible = cohort_member if period_mode == "cohort" else in_period(date) and attributed_here
        currency = decision.currency if decision else str(payment.currency).upper()
        result = currencies.setdefault(currency, bucket(currency))
        if decision:
            result["scale"] = decision.currency_scale
        amount = decision.amount_minor if decision else payment_minor(payment)
        external = (
            str(
                decision.funding_source
                if decision and decision.funding_source
                else payment.funding_source
            )
            == "external"
        )
        balance = int(payment.user_balance_amount_minor or 0) + int(
            payment.partner_balance_amount_minor or 0
        )
        product = str(
            (decision.sale_mode if decision and decision.sale_mode else payment.sale_mode) or ""
        ).split("|")[0] != "balance_topup" and (
            amount > 0 or balance > 0 or payment.promo_code_id is not None
        )
        if decision and decision.product_order is not None:
            product = decision.product_order
        reversed_payment = payment.status in {"refunded", "reversed"}
        product_amount = (
            decision.product_amount_minor
            if decision and decision.product_amount_minor is not None
            else amount + balance
            if external
            else amount
        )
        refund_visible = (
            cohort_member
            if period_mode == "cohort"
            else attributed_here and in_period(decision.refunded_at if decision else date)
        )
        if reversed_payment and refund_visible and product:
            result["refund_minor"] += product_amount
        acquired = utc(acquisition_date) if cohort_member else None
        if product and acquired and date and utc(date) >= acquired:
            for days in (7, 30, 90):
                if acquired + timedelta(days=days) <= now and utc(date) < acquired + timedelta(
                    days=days
                ):
                    result[f"d{days}_minor"] += product_amount
                    if (
                        reversed_payment
                        and decision
                        and decision.refunded_at
                        and utc(decision.refunded_at) < acquired + timedelta(days=days)
                    ):
                        result[f"d{days}_minor"] -= product_amount
        if not visible:
            continue
        if decision is None or decision.succeeded_at is None:
            legacy_payment_count += 1
        if external:
            result["cash_minor"] += (
                decision.cash_amount_minor
                if decision and decision.cash_amount_minor is not None
                else amount
            )
        if product:
            result["product_minor"] += product_amount
            result["purchases"] += 1
            purchase_count += 1
            payers.add(uid)
            if decision and decision.first_product_purchase:
                first_payers.add(uid)
                if cohort_member:
                    currency_first_payers.setdefault(currency, set()).add(uid)
                result["first_purchase_minor"] += product_amount
            elif decision and decision.first_product_purchase is False:
                result["repeat_purchase_minor"] += product_amount
            result["net_minor"] = result["product_minor"] - result["refund_minor"]
    spends = list(
        (
            await session.execute(
                select(AdSpendEntry).where(AdSpendEntry.campaign_id == campaign_id)
            )
        ).scalars()
    )
    if campaign.spend_source == "manual":
        for spend in spends:
            if in_period(spend.occurred_at):
                result = currencies.setdefault(spend.currency, bucket(spend.currency))
                result["spend_minor"] = (result["spend_minor"] or 0) + spend.amount_minor
    elif campaign.spend_source == "legacy" and start is None and end is None:
        currencies.setdefault("RUB", bucket("RUB"))["spend_minor"] = int(
            Decimal(str(campaign.cost or 0)) * 100
        )
    external_metrics = (
        await session.execute(
            select(AdExternalMetric)
            .join(AdImportBatch)
            .where(
                AdImportBatch.campaign_id == campaign_id,
                AdImportBatch.status == "confirmed",
                AdExternalMetric.is_current.is_(True),
            )
        )
    ).scalars()
    presence: dict[str, set[str]] = {}
    for rows_json in (
        await session.execute(
            select(AdImportBatch.rows_json).where(
                AdImportBatch.campaign_id == campaign_id,
                AdImportBatch.status == "confirmed",
                AdImportBatch.id.in_(
                    select(AdExternalMetric.batch_id).where(AdExternalMetric.is_current.is_(True))
                ),
            )
        )
    ).scalars():
        for row in json.loads(rows_json):
            presence[row["logical_key"]] = set(row.get("available_metrics", []))
    missing_metrics: set[str] = set()
    platform: dict[str, int | None] = {"impressions": None, "clicks": None, "starts": None}
    for metric in external_metrics:
        if not in_period(metric.interval_start) or (end and utc(metric.interval_end) > end):
            continue
        for metric_name in ("impressions", "clicks", "starts"):
            if metric_name not in presence.get(metric.logical_key, set()):
                missing_metrics.add(metric_name)
            else:
                platform[metric_name] = (platform[metric_name] or 0) + int(
                    getattr(metric, metric_name)
                )
        if campaign.spend_source == "import" and metric.cost_minor is not None and metric.currency:
            result = currencies.setdefault(metric.currency, bucket(metric.currency))
            result["spend_minor"] = (result["spend_minor"] or 0) + metric.cost_minor
    for metric_name in missing_metrics:
        platform[metric_name] = None
    currencies = {
        key: value
        for key, value in currencies.items()
        if any(
            value[field]
            for field in (
                "cash_minor",
                "product_minor",
                "refund_minor",
                "spend_minor",
                "purchases",
                "d7_minor",
                "d30_minor",
                "d90_minor",
            )
        )
    }
    # Campaign expenses and platform aggregates cannot be allocated to contact facets.
    if link_id or evidence or channel:
        platform = {"impressions": None, "clicks": None, "starts": None}
        for result in currencies.values():
            result["spend_minor"] = None
    for result in currencies.values():
        result["net_minor"] = result["product_minor"] - result["refund_minor"]
        result["roas"] = ratio(result["net_minor"], result["spend_minor"] or 0)
        result["cac_minor"] = (
            ratio(
                result["spend_minor"] or 0,
                len(currency_first_payers.get(result["currency"], set())),
            )
            if result["spend_minor"] is not None
            else None
        )
        result["average_order_minor"] = ratio(result["product_minor"], result["purchases"])
    return {
        "contacts": int(contact_counts[0]),
        "attributed_users": int(cohort_counts[0]),
        "registrations": int(contact_counts[1]),
        "returning_users": int(contact_counts[2]),
        "trials": trial_count,
        "payers": len(payers),
        "first_payers": len(first_payers),
        "purchases": purchase_count,
        "currencies": [
            value
            for key, value in currencies.items()
            if selected_currency is None or key == selected_currency
        ],
        "platform": platform,
        "ctr": ratio(platform["clicks"] or 0, platform["impressions"] or 0),
        "registration_conversion": ratio(int(contact_counts[1]), int(contact_counts[3])),
        "legacy_payment_count": legacy_payment_count,
        "period_mode": period_mode,
        "mature_cohorts": {
            str(days): int(cohort_counts[index + 1] or 0) for index, days in enumerate((7, 30, 90))
        },
    }
