"""Bounded-memory CSV exports using the same campaign period selection."""

import json
from typing import Any

from aiohttp import web
from pydantic import ValidationError
from sqlalchemy import Select, and_, func, or_, select

from bot.app.web.context import get_session_factory
from bot.services.advertising.imports import export_csv
from bot.services.advertising.reporting import campaign_report
from db.advertising_models import (
    AdImportBatch,
    AdMatchCandidate,
    AdPurchaseAttribution,
    AdTouchpoint,
)
from db.dal.ad_statistics import payment_campaign
from db.models import AdAttribution, AdCampaign, Payment

from .advertising_access import require_advertising_admin
from .advertising_schemas import AdReportQuery
from .common import _error


def acquisition_query(campaign_id: int, query: AdReportQuery) -> Select[Any]:
    statement = select(AdAttribution.user_id).where(AdAttribution.ad_campaign_id == campaign_id)
    if query.start:
        statement = statement.where(AdAttribution.first_start_at >= query.start)
    if query.end:
        statement = statement.where(AdAttribution.first_start_at < query.end)
    return statement


async def admin_ad_export_route(request: web.Request) -> web.StreamResponse:
    require_advertising_admin(request)
    try:
        query = AdReportQuery.model_validate(dict(request.query))
    except ValidationError:
        return _error(400, "invalid_ad_period")
    kind = request.query.get("kind", "contacts")
    if kind not in {"contacts", "purchases", "report", "matches"}:
        return _error(400, "invalid_ad_export")
    ident = int(request.match_info["campaign_id"])
    async with get_session_factory(request)() as session:
        campaign = await session.get(AdCampaign, ident)
        if campaign is None:
            return _error(404, "not_found")
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": f'attachment; filename="advertising-{kind}.csv"',
            }
        )
        if kind == "report":
            report = await campaign_report(
                session, campaign, start=query.start, end=query.end, period_mode=query.period_mode
            )
            await response.prepare(request)
            await response.write(export_csv(report["currencies"]).encode("utf-8-sig"))
        else:
            if kind == "contacts":
                statement = select(AdTouchpoint).where(AdTouchpoint.campaign_id == ident)
                date, user = AdTouchpoint.occurred_at, AdTouchpoint.user_id
                if query.link_id:
                    statement = statement.where(AdTouchpoint.link_id == query.link_id)
                if query.evidence:
                    statement = statement.where(AdTouchpoint.evidence == query.evidence)
                if query.channel:
                    statement = statement.where(AdTouchpoint.channel == query.channel)
            elif kind == "purchases":
                statement = (
                    select(Payment, AdPurchaseAttribution)
                    .outerjoin(
                        AdPurchaseAttribution,
                        AdPurchaseAttribution.payment_id == Payment.payment_id,
                    )
                    .outerjoin(AdAttribution, AdAttribution.user_id == Payment.user_id)
                )
                if query.period_mode != "cohort":
                    statement = statement.where(payment_campaign() == ident)
                date, user = (
                    func.coalesce(AdPurchaseAttribution.succeeded_at, Payment.created_at),
                    Payment.user_id,
                )
                statement = statement.outerjoin(
                    AdTouchpoint, AdTouchpoint.id == AdPurchaseAttribution.touchpoint_id
                )
                if query.link_id:
                    statement = statement.where(AdPurchaseAttribution.link_id == query.link_id)
                if query.evidence:
                    statement = statement.where(
                        func.coalesce(AdPurchaseAttribution.evidence, "legacy_bot_start")
                        == query.evidence
                    )
                if query.channel:
                    statement = statement.where(AdTouchpoint.channel == query.channel)
                if query.currency:
                    statement = statement.where(
                        func.coalesce(AdPurchaseAttribution.currency, Payment.currency)
                        == query.currency
                    )
            else:
                statement = (
                    select(AdMatchCandidate, AdImportBatch.created_at)
                    .join(AdImportBatch)
                    .where(AdImportBatch.campaign_id == ident)
                )
                date, user = AdImportBatch.created_at, None
            if query.period_mode == "cohort" and user is not None:
                statement = statement.where(user.in_(acquisition_query(ident, query)))
            else:
                dates = []
                if query.start:
                    dates.append(date >= query.start)
                if query.end:
                    dates.append(date < query.end)
                if dates and kind == "purchases":
                    refunds = []
                    if query.start:
                        refunds.append(AdPurchaseAttribution.refunded_at >= query.start)
                    if query.end:
                        refunds.append(AdPurchaseAttribution.refunded_at < query.end)
                    statement = statement.where(or_(and_(*dates), and_(*refunds)))
                elif dates:
                    statement = statement.where(*dates)
            stream = await session.stream(statement.execution_options(yield_per=250))
            await response.prepare(request)
            first = True
            async for row in stream:
                item = row[0]
                values = {
                    column.key: getattr(item, column.key) for column in item.__table__.columns
                }
                if kind == "purchases" and row[1]:
                    values.update(
                        {
                            "evidence": row[1].evidence,
                            "first_product_purchase": row[1].first_product_purchase,
                            "product_amount_minor": row[1].product_amount_minor,
                        }
                    )
                elif kind == "purchases":
                    values.update(
                        evidence="legacy_bot_start",
                        first_product_purchase=None,
                        product_amount_minor=None,
                    )
                for key, value in values.items():
                    if isinstance(value, (dict, list)):
                        values[key] = json.dumps(value)
                csv = export_csv([values])
                await response.write(
                    (csv if first else csv.split("\n", 1)[1]).encode(
                        "utf-8-sig" if first else "utf-8"
                    )
                )
                first = False
        await response.write_eof()
        return response
