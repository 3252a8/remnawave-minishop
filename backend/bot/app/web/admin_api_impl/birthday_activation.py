from aiohttp import web

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.services.birthday_activation_config import (
    BIRTHDAY_CAMPAIGN_KEY,
    BirthdayActivationConfig,
    load_birthday_activation_config,
)
from db.dal import app_settings_dal

from .auth import _require_admin_user_id
from .common import _error, _ok


async def admin_birthday_activation_get_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async with get_session_factory(request)() as session:
        config = await load_birthday_activation_config(session, get_settings(request))
    return _ok({"campaign": config.model_dump(mode="json")})


async def admin_birthday_activation_put_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    config = await parse_body_or_400(request, BirthdayActivationConfig)
    try:
        config.validate_for(get_settings(request))
    except ValueError as exc:
        return _error(400, str(exc))
    value = config.model_dump(mode="json")
    async with get_session_factory(request)() as session:
        await app_settings_dal.upsert_override(
            session, key=BIRTHDAY_CAMPAIGN_KEY, value=value, updated_by=actor_id
        )
        await session.commit()
    return _ok({"campaign": value})


register_contract(
    "admin_birthday_activation_get_route",
    RouteContract(
        response_schema=ok_envelope_for(BirthdayActivationConfig, key="campaign"),
        models=(BirthdayActivationConfig,),
    ),
)
register_contract(
    "admin_birthday_activation_put_route",
    RouteContract(
        request_model=BirthdayActivationConfig,
        response_schema=ok_envelope_for(BirthdayActivationConfig, key="campaign"),
        models=(BirthdayActivationConfig,),
    ),
)
