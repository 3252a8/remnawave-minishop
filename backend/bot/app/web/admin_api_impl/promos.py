from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from db.dal import promo_code_dal

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
)
from .schemas import PromoCreateBody, PromoOut, PromoUpdateBody

register_contract(
    "admin_promos_list_route",
    RouteContract(
        response_schema=ok_envelope_for(
            PromoOut,
            key="promos",
            many=True,
            extra={
                "page": {"type": "integer", "minimum": 0},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                "total": {"type": "integer", "minimum": 0},
            },
        ),
        models=(PromoOut,),
    ),
)
register_contract(
    "admin_promo_create_route",
    RouteContract(
        request_model=PromoCreateBody,
        response_schema=ok_envelope_for(PromoOut, key="promo"),
        models=(PromoCreateBody, PromoOut),
    ),
)
register_contract(
    "admin_promo_update_route",
    RouteContract(
        request_model=PromoUpdateBody,
        response_schema=ok_envelope_for(PromoOut, key="promo"),
        models=(PromoUpdateBody, PromoOut),
    ),
)
register_contract(
    "admin_promo_delete_route",
    RouteContract(response_schema=ok_envelope_for()),
)


async def admin_promos_list_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))
    async with async_session_factory() as session:
        promos = await promo_code_dal.get_all_promo_codes_with_details(
            session, limit=page_size, offset=page * page_size
        )
        total = await promo_code_dal.get_promo_codes_count(session)
    return _ok(
        {
            "promos": [PromoOut.from_orm_promo(p).model_dump(mode="json") for p in promos],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }
    )


async def admin_promo_create_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, PromoCreateBody)
    code = body.code
    bonus_days = body.bonus_days
    max_activations = body.max_activations

    valid_until = None
    if body.valid_days:
        try:
            valid_until = datetime.now(timezone.utc) + timedelta(days=int(body.valid_days))
        except (TypeError, ValueError):
            return _error(400, "invalid_valid_days")

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        existing = await promo_code_dal.get_promo_code_by_code(session, code)
        if existing:
            return _error(409, "duplicate_code")
        promo = await promo_code_dal.create_promo_code(
            session,
            {
                "code": code,
                "bonus_days": bonus_days,
                "max_activations": max_activations,
                "valid_until": valid_until,
                "created_by_admin_id": actor_id,
                "is_active": True,
            },
        )
        await session.commit()
    return _ok({"promo": PromoOut.from_orm_promo(promo).model_dump(mode="json")})


async def admin_promo_update_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    promo_id = int(request.match_info["promo_id"])
    body = await parse_body_or_400(request, PromoUpdateBody)
    update_data: Dict[str, Any] = {}
    fields_set = body.model_fields_set
    if "is_active" in fields_set:
        update_data["is_active"] = bool(body.is_active)
    if "bonus_days" in fields_set and body.bonus_days is not None:
        update_data["bonus_days"] = int(body.bonus_days)
    if "max_activations" in fields_set and body.max_activations is not None:
        update_data["max_activations"] = int(body.max_activations)

    if not update_data:
        return _error(400, "no_changes")

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        promo = await promo_code_dal.update_promo_code(session, promo_id, update_data)
        if not promo:
            return _error(404, "not_found")
        await session.commit()
        await session.refresh(promo)
    return _ok({"promo": PromoOut.from_orm_promo(promo).model_dump(mode="json")})


async def admin_promo_delete_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    promo_id = int(request.match_info["promo_id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        promo = await promo_code_dal.delete_promo_code(session, promo_id)
        if not promo:
            return _error(404, "not_found")
        await session.commit()
    return _ok({})
