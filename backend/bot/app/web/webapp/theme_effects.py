"""Authenticated theme runtime.

Storefront traffic runs the active theme's effect for ordinary users. Administrators
can opt into that runtime through appearance settings or explicitly preview an
installed theme (`?theme_preview=<key>`). Staged packages use the separate
opaque-origin mock preview in the theme library. All paths require current consent.
"""

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


async def viewer(request: web.Request) -> tuple[bool, bool]:
    """Return ``(allowed, is_admin)`` for the authenticated viewer.

    ``allowed`` is false for missing or banned accounts. The admin flag lets
    the descriptor route enforce the appearance setting or an explicit preview target.
    """
    user_id = _require_user_id(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if not user or user.is_banned:
            return False, False
        return True, await is_admin(session, user_id)


def theme_root(request: web.Request) -> Path:
    return Path(get_settings(request).WEBAPP_THEMES_DIR).expanduser()


def preview_key(request: web.Request) -> str:
    """Theme key requested through the ``theme_preview`` query parameter."""
    return str(request.query.get("theme_preview", "")).strip()


def _theme_defaults(request: web.Request) -> tuple[str | None, str]:
    settings = get_settings(request)
    return settings.WEBAPP_DEFAULT_THEME, settings.WEBAPP_PRIMARY_COLOR or "#00fe7a"


async def theme_effects_route(request: web.Request) -> web.Response:
    allowed, admin = await viewer(request)
    effect = None
    if allowed:
        requested = preview_key(request) if admin else ""
        if not admin or requested or get_settings(request).WEBAPP_ADMIN_THEME_EFFECTS_ENABLED:
            default_theme, accent = _theme_defaults(request)
            try:
                effect = await asyncio.to_thread(
                    active_effect,
                    theme_root(request),
                    default_theme,
                    accent,
                    requested or None,
                )
            except (PackageError, OSError, ValueError):
                effect = None
    return json_response(
        {"ok": True, **ThemeEffectsOut(effect=effect).model_dump(mode="json")},
        headers={"Cache-Control": "private, no-store"},
    )


async def theme_effect_asset_route(request: web.Request) -> web.Response:
    allowed, admin = await viewer(request)
    if not allowed:
        raise web.HTTPForbidden()
    settings = get_settings(request)
    root = theme_root(request)
    key = request.match_info["key"]
    try:
        effect = await asyncio.to_thread(
            active_effect,
            root,
            settings.WEBAPP_DEFAULT_THEME,
            settings.WEBAPP_PRIMARY_COLOR or "#00fe7a",
            # An administrator may load the adapter of any installed theme for
            # the preview; ordinary users are limited to the active theme.
            key if admin else None,
        )
        if effect is None:
            raise web.HTTPNotFound()
        body, content_type = await asyncio.to_thread(
            effect_asset,
            root,
            effect,
            key,
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
