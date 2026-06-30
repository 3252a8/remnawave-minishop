from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_bot_username,
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.services.promo_code_service import PromoCodeService
from bot.services.promo_effects import PromoEffects, validate_effects
from db.dal import promo_code_dal

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _build_admin_promo_bot_link,
    _build_admin_promo_webapp_link,
    _error,
    _ok,
)
from .schemas import PromoActivationOut, PromoCreateBody, PromoOut, PromoUpdateBody

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
    "admin_promo_activations_route",
    RouteContract(
        response_schema=ok_envelope_for(
            PromoActivationOut,
            key="activations",
            many=True,
            extra={
                "page": {"type": "integer", "minimum": 0},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                "total": {"type": "integer", "minimum": 0},
            },
        ),
        models=(PromoActivationOut,),
    ),
)
register_contract(
    "admin_promo_delete_route",
    RouteContract(response_schema=ok_envelope_for()),
)


def _serialize_promo_for_request(request: web.Request, promo: Any) -> dict[str, Any]:
    settings = get_settings(request)
    code = str(getattr(promo, "code", "") or "")
    return PromoOut.from_orm_promo(
        promo,
        bot_link=_build_admin_promo_bot_link(get_bot_username(request), code),
        webapp_link=_build_admin_promo_webapp_link(
            settings.SUBSCRIPTION_MINI_APP_URL,
            code,
        ),
    ).model_dump(mode="json")


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
            "promos": [_serialize_promo_for_request(request, p) for p in promos],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }
    )


async def admin_promo_create_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, PromoCreateBody)
    max_activations = body.max_activations

    valid_until = None
    if body.valid_days:
        try:
            valid_until = datetime.now(timezone.utc) + timedelta(days=int(body.valid_days))
        except (TypeError, ValueError):
            return _error(400, "invalid_valid_days")

    settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        try:
            promo = await PromoCodeService.issue_code(
                session,
                effects=body.to_effects(),
                code=body.code,
                max_activations=max_activations,
                valid_until=valid_until,
                origin=body.origin,
                created_by_admin_id=actor_id,
                max_duration_multiplier=float(settings.PROMO_DURATION_MULTIPLIER_MAX),
                max_traffic_multiplier=float(settings.PROMO_TRAFFIC_MULTIPLIER_MAX),
            )
        except ValueError as exc:
            if str(exc) == "duplicate_code":
                return _error(409, "duplicate_code")
            return _error(400, str(exc) or "invalid_effects")
        await session.commit()
    return _ok({"promo": _serialize_promo_for_request(request, promo)})


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
    if "bonus_requires_payment" in fields_set:
        update_data["bonus_requires_payment"] = bool(body.bonus_requires_payment)
    for field in (
        "discount_percent",
        "duration_multiplier",
        "traffic_multiplier",
        "applies_to",
        "min_subscription_months",
        "min_traffic_gb",
        "origin",
    ):
        if field in fields_set:
            update_data[field] = getattr(body, field)
    if "max_activations" in fields_set and body.max_activations is not None:
        update_data["max_activations"] = int(body.max_activations)
    if "clear_valid_until" in fields_set and bool(body.clear_valid_until):
        update_data["valid_until"] = None
    elif "valid_until" in fields_set:
        update_data["valid_until"] = body.valid_until

    if not update_data:
        return _error(400, "no_changes")

    settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        current = await promo_code_dal.get_promo_code_by_id(session, promo_id)
        if not current:
            return _error(404, "not_found")
        if "max_activations" in update_data and int(update_data["max_activations"]) < int(
            current.current_activations or 0
        ):
            return _error(400, "max_activations_below_current")
        effect_fields = {
            "bonus_days",
            "discount_percent",
            "duration_multiplier",
            "traffic_multiplier",
            "bonus_requires_payment",
            "applies_to",
            "min_subscription_months",
            "min_traffic_gb",
        }
        should_validate_effects = bool(effect_fields & update_data.keys()) or (
            update_data.get("is_active") is True
        )
        if should_validate_effects:
            merged = {
                "bonus_days": getattr(current, "bonus_days", 0),
                "discount_percent": getattr(current, "discount_percent", None),
                "duration_multiplier": getattr(current, "duration_multiplier", None),
                "traffic_multiplier": getattr(current, "traffic_multiplier", None),
                "bonus_requires_payment": getattr(current, "bonus_requires_payment", False),
                "applies_to": getattr(current, "applies_to", "all"),
                "min_subscription_months": getattr(current, "min_subscription_months", None),
                "min_traffic_gb": getattr(current, "min_traffic_gb", None),
            }
            merged.update({key: value for key, value in update_data.items() if key in merged})
            try:
                validate_effects(
                    PromoEffects.from_payload(merged),
                    max_duration_multiplier=float(settings.PROMO_DURATION_MULTIPLIER_MAX),
                    max_traffic_multiplier=float(settings.PROMO_TRAFFIC_MULTIPLIER_MAX),
                )
            except ValueError as exc:
                return _error(400, str(exc) or "invalid_effects")
        promo = await promo_code_dal.update_promo_code(session, promo_id, update_data)
        await session.commit()
        await session.refresh(promo)
    return _ok({"promo": _serialize_promo_for_request(request, promo)})


async def admin_promo_activations_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    promo_id = int(request.match_info["promo_id"])
    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(100, max(1, int(request.query.get("page_size", 25) or 25)))
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        promo = await promo_code_dal.get_promo_code_by_id(session, promo_id)
        if not promo:
            return _error(404, "not_found")
        activations = await promo_code_dal.get_promo_activations_by_code_id(
            session,
            promo_id,
            limit=page_size,
            offset=page * page_size,
        )
        total = await promo_code_dal.count_promo_activations_by_code_id(session, promo_id)
        rows = [
            PromoActivationOut.from_orm_activation(activation).model_dump(mode="json")
            for activation in activations
        ]
    return _ok(
        {
            "activations": rows,
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }
    )


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
