"""Admin broadcast shortcode registry + personalization preview endpoints.

- ``GET  /api/admin/broadcast/shortcodes`` — the localized registry plus the
  editor∩email allowed-tag list; single source of truth for the UI picker.
- ``POST /api/admin/broadcast/preview`` — render a draft for a sample user
  (``render`` mode) or send the personalized draft to the acting admin's own
  Telegram (``send_telegram`` mode), which is the authoritative HTML validation.
"""

from __future__ import annotations

import logging

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_bot_username,
    get_i18n,
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.services.broadcast_personalization import (
    SHORTCODES,
    TELEGRAM_BROADCAST_ALLOWED_TAGS,
    BroadcastUserContext,
    known_shortcodes,
    load_broadcast_contexts,
    render_broadcast_text,
    unknown_shortcodes,
)
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from config.settings import Settings
from db.dal import message_log_dal, user_dal

from .auth import _require_admin_user_id
from .broadcast import _resolve_panel_service
from .common import _error, _ok
from .response_schemas import (
    AdminBroadcastPreviewOut,
    AdminBroadcastShortcodeOut,
    AdminBroadcastShortcodesOut,
)
from .schemas import AdminBroadcastPreviewBody

logger = logging.getLogger(__name__)

register_contract(
    "admin_broadcast_shortcodes_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminBroadcastShortcodesOut),
        models=(AdminBroadcastShortcodesOut, AdminBroadcastShortcodeOut),
    ),
)
register_contract(
    "admin_broadcast_preview_route",
    RouteContract(
        request_model=AdminBroadcastPreviewBody,
        response_schema=ok_envelope_for(AdminBroadcastPreviewOut),
        models=(AdminBroadcastPreviewOut,),
    ),
)


async def _admin_language(request: web.Request, actor_id: int) -> str:
    settings: Settings = get_settings(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        admin_user = await user_dal.get_user_by_id(session, actor_id)
    return getattr(admin_user, "language_code", None) or settings.DEFAULT_LANGUAGE or "ru"


async def admin_broadcast_shortcodes_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    i18n = get_i18n(request)
    lang = await _admin_language(request, actor_id)

    def describe(key: str) -> str:
        return i18n.gettext(lang, key) if i18n is not None else key

    payload = AdminBroadcastShortcodesOut(
        shortcodes=[
            AdminBroadcastShortcodeOut(
                name=spec.name,
                cost=spec.cost,
                description=describe(spec.description_key),
            )
            for spec in SHORTCODES.values()
        ],
        allowed_tags=list(TELEGRAM_BROADCAST_ALLOWED_TAGS),
    )
    return _ok(payload.model_dump(mode="json"))


async def admin_broadcast_preview_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, AdminBroadcastPreviewBody)
    settings: Settings = get_settings(request)
    text = str(body.text or "").strip()
    email_subject = str(body.email_subject or "")
    if not text:
        return _error(400, "empty_text")

    i18n = get_i18n(request)
    bot_username = get_bot_username(request)
    sample_user_id = int(body.user_id) if body.user_id is not None else actor_id
    unknown = sorted(unknown_shortcodes(text) | unknown_shortcodes(email_subject))
    needed = known_shortcodes(text) | known_shortcodes(email_subject)

    async_session_factory: sessionmaker = get_session_factory(request)
    contexts: dict[int, BroadcastUserContext] = {}
    async with async_session_factory() as session:
        if needed:
            contexts = await load_broadcast_contexts(
                session,
                settings,
                [sample_user_id],
                needed,
                _resolve_panel_service(request),
            )
        await session.commit()

    ctx = contexts.get(sample_user_id)
    lang = (ctx.language_code if ctx else None) or await _admin_language(request, actor_id)

    def render(template: str, *, escape: bool) -> str:
        return render_broadcast_text(
            template,
            ctx,
            lang=lang,
            i18n=i18n,
            settings=settings,
            bot_username=bot_username,
            escape=escape,
        )

    rendered_text = render(text, escape=True)
    rendered_subject = render(email_subject, escape=False) if email_subject else None

    if body.mode == "send_telegram":
        admin_telegram_id = request.get("admin_telegram_id")
        if not admin_telegram_id:
            return _error(403, "admin_telegram_unavailable")
        queue_manager = get_queue_manager()
        if not queue_manager:
            return _error(503, "queue_unavailable")
        try:
            await send_message_via_queue(
                queue_manager,
                int(admin_telegram_id),
                MessageContent(content_type="text", text=rendered_text),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.warning("Broadcast preview send failed: %s", exc)
            return _error(502, "preview_failed", str(exc))

        async with async_session_factory() as session:
            await message_log_dal.create_message_log(
                session,
                {
                    "user_id": actor_id,
                    "event_type": "admin_broadcast_preview_webapp",
                    "content": rendered_text[:4000],
                    "is_admin_event": True,
                },
            )
        payload = AdminBroadcastPreviewOut(
            rendered_text=rendered_text,
            rendered_subject=rendered_subject,
            unknown_shortcodes=unknown,
            length=len(rendered_text),
            sent=True,
        )
        return _ok(payload.model_dump(mode="json"))

    payload = AdminBroadcastPreviewOut(
        rendered_text=rendered_text,
        rendered_subject=rendered_subject,
        unknown_shortcodes=unknown,
        length=len(rendered_text),
        sent=False,
    )
    return _ok(payload.model_dump(mode="json"))
