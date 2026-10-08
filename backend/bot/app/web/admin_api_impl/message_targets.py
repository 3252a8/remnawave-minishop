"""Customer plugin pages available to every administrator button editor."""

from aiohttp import web
from pydantic import Field

from bot.app.web.context import get_i18n, get_session_factory
from bot.app.web.http_contracts import HttpResponseModel
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.plugins.extensions.presentation import preferences
from bot.plugins.message_catalog import message_pages

from .auth import _require_admin_user_id
from .broadcast_shortcodes import _admin_language
from .common import _ok


class AdminMessageTargetOut(HttpResponseModel):
    id: str
    label: str
    owner: str


class AdminMessageTargetsOut(HttpResponseModel):
    sections: list[AdminMessageTargetOut] = Field(default_factory=list)


register_contract(
    "admin_message_targets_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminMessageTargetsOut),
        models=(AdminMessageTargetsOut, AdminMessageTargetOut),
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
    payload = AdminMessageTargetsOut(sections=sections)
    response = _ok(payload.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response
