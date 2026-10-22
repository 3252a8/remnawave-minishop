"""Customer plugin pages available to every administrator button editor."""

from aiohttp import web
from pydantic import Field

from bot.app.web.context import get_i18n, get_session_factory
from bot.app.web.http_contracts import HttpResponseModel
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.app.web.webapp.guide_document import load_guide_content
from bot.plugins.extensions.presentation import preferences
from bot.plugins.message_catalog import message_pages
from bot.services.message_composition import resolve_localized_text

from .auth import _require_admin_user_id
from .broadcast_shortcodes import _admin_language
from .common import _ok


class AdminMessageTargetOut(HttpResponseModel):
    id: str
    label: str
    owner: str


class AdminInstallAppOut(HttpResponseModel):
    id: str
    name: str


class AdminInstallPlatformOut(HttpResponseModel):
    id: str
    label: str
    apps: list[AdminInstallAppOut] = Field(default_factory=list)


class AdminMessageTargetsOut(HttpResponseModel):
    sections: list[AdminMessageTargetOut] = Field(default_factory=list)
    install_platforms: list[AdminInstallPlatformOut] = Field(default_factory=list)


register_contract(
    "admin_message_targets_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminMessageTargetsOut),
        models=(
            AdminMessageTargetsOut,
            AdminMessageTargetOut,
            AdminInstallPlatformOut,
            AdminInstallAppOut,
        ),
    ),
)


async def admin_message_targets_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    language = await _admin_language(request, actor_id)
    i18n = get_i18n(request)
    sections: list[AdminMessageTargetOut] = []
    owner_choices: dict[str, dict[str, tuple[bool, int]]] = {}
    async with get_session_factory(request)() as session:
        for path, label, owner, i18n_key, page_id in await message_pages():
            if owner not in owner_choices:
                owner_choices[owner] = await preferences(session, owner)
            choice = owner_choices[owner].get(f"view:{page_id}")
            if choice is not None and not choice[0]:
                continue
            if i18n_key and i18n is not None:
                translated = i18n.gettext(language, i18n_key)
                if translated != i18n_key:
                    label = translated
            sections.append(AdminMessageTargetOut(id=path, label=label, owner=owner))
    _status, document = await load_guide_content(request, user_id=actor_id)
    install_platforms: list[AdminInstallPlatformOut] = []
    for platform in (document or {}).get("platforms", []):
        title = platform.get("displayName")
        label = (
            resolve_localized_text(title, language=language, default_language="en")
            if isinstance(title, dict)
            else str(title or platform["id"])
        )
        install_platforms.append(
            AdminInstallPlatformOut(
                id=platform["id"],
                label=label,
                apps=[
                    AdminInstallAppOut(id=app["id"], name=app["name"])
                    for app in platform.get("apps", [])
                ],
            )
        )
    payload = AdminMessageTargetsOut(sections=sections, install_platforms=install_platforms)
    response = _ok(payload.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response
