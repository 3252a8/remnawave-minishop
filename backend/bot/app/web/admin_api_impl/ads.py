from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from db.dal import ad_dal, user_dal
from db.models import AdCampaign, User

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
    advertiser_id = body.advertiser_id

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        existing = await ad_dal.get_campaign_by_start_param(session, start_param)
        if existing:
            return _error(409, "duplicate_start_param")
        if advertiser_id is not None:
            user = await user_dal.get_user_by_telegram_id(
                session, advertiser_id
            ) or await user_dal.get_user_by_id(session, advertiser_id)
            if not user:
                user = User(user_id=advertiser_id, telegram_id=advertiser_id)
                session.add(user)
                await session.flush()
            advertiser_id = int(user.user_id)
        campaign = await ad_dal.create_campaign(
            session,
            source=source,
            start_param=start_param,
            cost=cost,
            advertiser_id=advertiser_id,
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


async def admin_ad_assign_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    body = await parse_body_or_400(request, AdAssignBody)
    advertiser_id = body.advertiser_id
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        campaign = await session.get(AdCampaign, campaign_id)
        if not campaign:
            return _error(404, "not_found")
        if advertiser_id is not None:
            user = await user_dal.get_user_by_telegram_id(
                session, advertiser_id
            ) or await user_dal.get_user_by_id(session, advertiser_id)
            if not user:
                user = User(user_id=advertiser_id, telegram_id=advertiser_id)
                session.add(user)
                await session.flush()
            advertiser_id = int(user.user_id)
        campaign.advertiser_id = advertiser_id
        await session.commit()
    return _ok({})


async def admin_ad_reset_stats_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ok = await ad_dal.reset_campaign_stats(session, campaign_id)
        if not ok:
            return _error(404, "not_found")
        await session.commit()
    return _ok({})


async def admin_ad_purchases_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    campaign_id = int(request.match_info["campaign_id"])
    page = int(request.query.get("page", "0"))
    page_size = int(request.query.get("page_size", "50"))
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        purchases = await ad_dal.list_campaign_purchases(
            session, campaign_id, page=page, page_size=page_size
        )
        formatted = [AdPurchaseItem.model_validate(p).model_dump(mode="json") for p in purchases]
    return _ok({"purchases": formatted})


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
