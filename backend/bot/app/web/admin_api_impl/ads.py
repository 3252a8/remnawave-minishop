from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from db.dal import ad_dal

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
)
from .schemas import AdCreateBody, AdminAdsListOut, AdOut, AdToggleBody

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
    "admin_ad_delete_route",
    RouteContract(response_schema=ok_envelope_for()),
)


async def admin_ads_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        campaigns = await ad_dal.list_campaigns(session)
        totals = await ad_dal.get_totals(session)
        results = []
        for campaign in campaigns:
            try:
                stats = await ad_dal.get_campaign_stats(session, campaign.ad_campaign_id)
            except Exception:
                stats = {}
            results.append(AdOut.from_orm_ad(campaign, stats).model_dump(mode="json"))
    return _ok({"campaigns": results, "totals": totals})


async def admin_ad_create_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdCreateBody)
    source = body.source
    start_param = body.start_param
    cost = body.cost

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        existing = await ad_dal.get_campaign_by_start_param(session, start_param)
        if existing:
            return _error(409, "duplicate_start_param")
        campaign = await ad_dal.create_campaign(
            session,
            source=source,
            start_param=start_param,
            cost=cost,
        )
        await session.commit()
        await session.refresh(campaign)
    return _ok({"campaign": AdOut.from_orm_ad(campaign).model_dump(mode="json")})


async def admin_ad_toggle_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    body = await parse_body_or_400(request, AdToggleBody)
    is_active = bool(body.is_active)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ok = await ad_dal.toggle_campaign_active(session, campaign_id, is_active)
        if not ok:
            return _error(404, "not_found")
        await session.commit()
    return _ok({})


async def admin_ad_delete_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ok = await ad_dal.delete_campaign(session, campaign_id)
        if not ok:
            return _error(404, "not_found")
        await session.commit()
    return _ok({})
