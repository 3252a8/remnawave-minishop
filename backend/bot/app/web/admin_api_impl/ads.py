from aiohttp import web
from pydantic import ValidationError
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from db.dal import ad_dal, user_dal
from db.models import AdCampaign

from .advertising import audit
from .advertising_schemas import AdListQuery
from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
)
from .schemas import (
    AdAssignBody,
    AdCreateBody,
    AdminAdsListOut,
    AdOut,
    AdPurchaseItem,
    AdPurchasesListOut,
    AdToggleBody,
)

register_contract(
    "admin_ads_list_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminAdsListOut),
        models=(AdminAdsListOut, AdOut),
    ),
)
register_contract(
    "admin_ad_create_route",
    RouteContract(
        request_model=AdCreateBody,
        response_schema=ok_envelope_for(AdOut, key="campaign"),
        models=(AdCreateBody, AdOut),
    ),
)
register_contract(
    "admin_ad_toggle_route",
    RouteContract(
        request_model=AdToggleBody,
        response_schema=ok_envelope_for(),
        models=(AdToggleBody,),
    ),
)
register_contract(
    "admin_ad_assign_route",
    RouteContract(
        request_model=AdAssignBody,
        response_schema=ok_envelope_for(),
        models=(AdAssignBody,),
    ),
)
register_contract(
    "admin_ad_reset_stats_route",
    RouteContract(
        response_schema=ok_envelope_for(),
    ),
)
register_contract(
    "admin_ad_purchases_route",
    RouteContract(
        response_schema=ok_envelope_for(AdPurchasesListOut),
        models=(AdPurchasesListOut, AdPurchaseItem),
    ),
)
register_contract(
    "admin_ad_delete_route",
    RouteContract(response_schema=ok_envelope_for()),
)


async def admin_ads_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        query = AdListQuery.model_validate(dict(request.query))
    except ValidationError:
        return _error(400, "invalid_ad_period")
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        statement = select(AdCampaign)
        if query.search:
            term = "%" + query.search.replace("%", r"\%").replace("_", r"\_") + "%"
            statement = statement.where(
                or_(
                    AdCampaign.name.ilike(term),
                    AdCampaign.source.ilike(term),
                    AdCampaign.start_param.ilike(term),
                )
            )
        if query.source:
            statement = statement.where(AdCampaign.source == query.source)
        if query.status == "archived":
            statement = statement.where(AdCampaign.archived_at.is_not(None))
        elif query.status != "all":
            statement = statement.where(
                AdCampaign.archived_at.is_(None), AdCampaign.is_active.is_(query.status == "active")
            )
        if query.start:
            statement = statement.where(AdCampaign.created_at >= query.start)
        if query.end:
            statement = statement.where(AdCampaign.created_at < query.end)
        filtered = statement.subquery()
        total = int(
            (await session.execute(select(func.count()).select_from(filtered))).scalar() or 0
        )
        ids = list((await session.execute(select(filtered.c.ad_campaign_id))).scalars())
        from db.dal.ad_statistics import campaign_statistics

        statistics = await campaign_statistics(session, ids)
        cost = (await session.execute(select(func.sum(filtered.c.cost)))).scalar() or 0
        currencies: dict[str, float] = {}
        for item in statistics.values():
            for currency, amount in item["revenue_by_currency"].items():
                currencies[currency] = currencies.get(currency, 0) + amount
        key, direction = query.sort.rsplit("_", 1)
        if key in {"registrations", "conversions"} and ids:
            metric = "starts" if key == "registrations" else "payers"
            sorted_ids = sorted(
                ids,
                key=lambda ident: (statistics[ident][metric], ident),
                reverse=direction == "desc",
            )
            ordering = case(
                {ident: index for index, ident in enumerate(sorted_ids)},
                value=AdCampaign.ad_campaign_id,
            )
        elif key in {"registrations", "conversions"}:
            ordering = AdCampaign.ad_campaign_id.desc()
        else:
            column = {
                "id": AdCampaign.ad_campaign_id,
                "source": AdCampaign.source,
                "param": AdCampaign.start_param,
                "advertiser": AdCampaign.advertiser_id,
                "cost": AdCampaign.cost,
                "status": AdCampaign.is_active,
            }[key]
            ordering = column.asc() if direction == "asc" else column.desc()
        campaigns = list(
            (
                await session.execute(
                    statement.order_by(ordering, AdCampaign.ad_campaign_id.desc())
                    .offset(query.page * query.page_size)
                    .limit(query.page_size)
                )
            ).scalars()
        )
        results = [
            AdOut.from_orm_ad(c, statistics.get(int(c.ad_campaign_id))).model_dump(mode="json")
            for c in campaigns
        ]
    return _ok(
        {
            "campaigns": results,
            "totals": {"cost": float(cost), "revenue": currencies.get("RUB", 0)},
            "revenue_by_currency": currencies,
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
        }
    )


async def admin_ad_create_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdCreateBody)
    source = body.source
    start_param = body.start_param
    cost = body.cost
    advertiser_id = body.advertiser_id

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        existing = await ad_dal.get_campaign_by_start_param(session, start_param)
        if existing:
            return _error(409, "duplicate_start_param")
        if advertiser_id is not None:
            user = await user_dal.get_user_by_id(session, advertiser_id)
            if user is None:
                return _error(404, "advertiser_not_found")
            advertiser_id = int(user.user_id)
        try:
            campaign = await ad_dal.create_campaign(
                session,
                source=source,
                start_param=start_param,
                cost=cost,
                advertiser_id=advertiser_id,
            )
        except ValueError:
            await session.rollback()
            return _error(409, "duplicate_start_param")
        audit(
            session,
            campaign.ad_campaign_id,
            actor,
            "campaign.created",
            {"start_param": start_param},
        )
        await session.commit()
        await session.refresh(campaign)
    return _ok({"campaign": AdOut.from_orm_ad(campaign).model_dump(mode="json")})


async def admin_ad_toggle_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    body = await parse_body_or_400(request, AdToggleBody)
    is_active = bool(body.is_active)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ok = await ad_dal.toggle_campaign_active(session, campaign_id, is_active)
        if not ok:
            return _error(404, "not_found")
        audit(session, campaign_id, actor, "campaign.toggled", {"is_active": is_active})
        await session.commit()
    return _ok({})


async def admin_ad_assign_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    body = await parse_body_or_400(request, AdAssignBody)
    advertiser_id = body.advertiser_id
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        campaign = await session.get(AdCampaign, campaign_id)
        if not campaign:
            return _error(404, "not_found")
        if advertiser_id is not None:
            user = await user_dal.get_user_by_id(session, advertiser_id)
            if user is None:
                return _error(404, "advertiser_not_found")
            advertiser_id = int(user.user_id)
        campaign.advertiser_id = advertiser_id
        audit(
            session,
            campaign_id,
            actor,
            "campaign.advertiser_assigned",
            {"advertiser_id": advertiser_id},
        )
        await session.commit()
    return _ok({})


async def admin_ad_reset_stats_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ok = await ad_dal.reset_campaign_stats(session, campaign_id)
        if not ok:
            return _error(404, "not_found")
        audit(session, campaign_id, actor, "campaign.legacy_reset", {})
        await session.commit()
    return _ok({})


async def admin_ad_purchases_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    from pydantic import ValidationError

    from .advertising_schemas import AdReportQuery

    try:
        query = AdReportQuery.model_validate(dict(request.query))
    except ValidationError:
        return _error(400, "invalid_ad_page")
    page, page_size = query.page, query.page_size
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        purchases = await ad_dal.list_campaign_purchases(
            session, campaign_id, page=page, page_size=page_size
        )
        formatted = [AdPurchaseItem.model_validate(p).model_dump(mode="json") for p in purchases]
        total = await ad_dal.count_campaign_purchases(session, campaign_id)
    return _ok({"purchases": formatted, "total": total, "page": page, "page_size": page_size})


async def admin_ad_delete_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ok = await ad_dal.delete_campaign(session, campaign_id)
        if not ok:
            return _error(404, "not_found")
        audit(session, campaign_id, actor, "campaign.archived", {})
        await session.commit()
    return _ok({})
