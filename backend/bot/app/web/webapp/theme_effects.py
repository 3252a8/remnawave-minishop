"""Authenticated theme runtime; privileged sessions never receive an executable theme."""

import asyncio
from pathlib import Path

from aiohttp import web

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.route_contracts import BINARY_RESPONSE_SCHEMA, ok_envelope_for, register_contract
from bot.services.account_roles import is_admin
from config.theme_packages.effects_runtime import active_effect, effect_asset
from config.theme_packages.models import PackageError, ThemeEffectsOut
from db.dal import user_dal

from .common import _require_user_id
from .contract_schemas import user_contract
from .response_helpers import json_response


async def eligible(request: web.Request) -> bool:
    user_id = _require_user_id(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        return bool(user and not user.is_banned and not await is_admin(session, user_id))


def theme_root(request: web.Request) -> Path:
    return Path(get_settings(request).WEBAPP_THEMES_DIR).expanduser()


async def theme_effects_route(request: web.Request) -> web.Response:
    settings = get_settings(request)
    effect = None
    if await eligible(request):
        try:
            effect = await asyncio.to_thread(
                active_effect,
                theme_root(request),
                settings.WEBAPP_DEFAULT_THEME,
                settings.WEBAPP_PRIMARY_COLOR or "#00fe7a",
            )
        except (PackageError, OSError, ValueError):
            effect = None
    return json_response(
        {"ok": True, **ThemeEffectsOut(effect=effect).model_dump(mode="json")},
        headers={"Cache-Control": "private, no-store"},
    )


async def theme_effect_asset_route(request: web.Request) -> web.Response:
    if not await eligible(request):
        raise web.HTTPForbidden()
    settings = get_settings(request)
    root = theme_root(request)
    try:
        effect = await asyncio.to_thread(
            active_effect,
            root,
            settings.WEBAPP_DEFAULT_THEME,
            settings.WEBAPP_PRIMARY_COLOR or "#00fe7a",
        )
        if effect is None:
            raise web.HTTPNotFound()
        body, content_type = await asyncio.to_thread(
            effect_asset,
            root,
            effect,
            request.match_info["key"],
            request.match_info["digest"],
            request.match_info["path"],
        )
    except (PackageError, OSError, ValueError):
        raise web.HTTPNotFound() from None
    return web.Response(
        body=body,
        content_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


register_contract(
    "theme_effects_route",
    user_contract(
        response_schema=ok_envelope_for(ThemeEffectsOut),
        models=(ThemeEffectsOut,),
    ),
)
register_contract(
    "theme_effect_asset_route",
    user_contract(
        response_schema=BINARY_RESPONSE_SCHEMA,
        response_content_type="application/octet-stream",
    ),
)
