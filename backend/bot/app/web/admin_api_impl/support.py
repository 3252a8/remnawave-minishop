from typing import Annotated, Any, Literal

from aiohttp import web
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_bot_username,
    get_i18n,
    get_session_factory,
    get_settings,
    get_support_service,
)
from bot.app.web.message_image_contracts import message_image_request_content
from bot.app.web.message_image_responses import message_image_response
from bot.app.web.request_parsing import (
    parse_body_or_400,
    parse_body_with_optional_image_or_400,
)
from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    BOOLEAN_SCHEMA,
    RouteContract,
    ok_envelope_with,
    register_contract,
    schema_ref,
)
from bot.app.web.support_schemas import (
    AdminSupportMessageOut,
    AdminSupportStatsOut,
    AdminSupportTicketOut,
    AdminSupportUserOut,
    AdminSupportUserSnapshotOut,
    EmptyObjectOut,
    SupportMessageButtonOut,
    SupportTicketOut,
    SupportTypingIn,
)
from bot.services.broadcast_personalization import (
    known_shortcodes,
    load_broadcast_contexts,
    render_broadcast_text,
    telegram_html_error,
    unknown_shortcodes,
)
from bot.services.message_image_service import (
    MessageImageError,
    load_message_image,
    prepare_message_image,
)
from bot.services.support_message_body import SupportBodyError
from bot.services.support_message_buttons import (
    MAX_SUPPORT_MESSAGE_BUTTONS,
    encode_support_buttons,
)
from bot.services.support_presence import is_support_typing, set_support_typing
from bot.services.support_service import TicketNotFound
from db.dal import support_dal, user_dal
from db.models import SupportTicket, SupportTicketMessage, User

from .auth import (
    _require_admin_user_id,
)
from .broadcast import _resolve_panel_service
from .broadcast_content import (
    BroadcastValidationError,
    resolve_broadcast_buttons,
)
from .common import (
    _error,
    _ok,
)
from .schemas import AdminBroadcastButtonBody

# The transport cap only: the message cap counts visible characters and is
# applied after sanitizing, so markup does not eat into what an admin may say.
TicketBodyString = Annotated[str, StringConstraints(max_length=32000)]


class AdminTicketReplyPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    body: TicketBodyString
    body_format: Literal["text", "html"] = "text"
    is_internal_note: bool = False
    # Buttons reach the customer, so an internal note never carries any; the
    # service drops them rather than the admin having to remember.
    buttons: list[AdminBroadcastButtonBody] = Field(
        default_factory=list, max_length=MAX_SUPPORT_MESSAGE_BUTTONS
    )

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        return value.strip()


class AdminTicketPatchPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["open", "awaiting_user", "awaiting_admin", "resolved", "closed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    category: Literal["billing", "technical", "account", "other"] | None = None
    assigned_admin_id: int | None = None


register_contract(
    "admin_support_tickets_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "tickets": {
                    "type": "array",
                    "items": schema_ref(AdminSupportTicketOut),
                }
            }
        ),
        models=(AdminSupportTicketOut, AdminSupportUserOut, EmptyObjectOut),
    ),
)
register_contract(
    "admin_support_ticket_detail_route",
    RouteContract(
        response_schema=ok_envelope_with(
            {
                "ticket": schema_ref(AdminSupportTicketOut),
                "messages": {
                    "type": "array",
                    "items": schema_ref(AdminSupportMessageOut),
                },
                "user_snapshot": {
                    "oneOf": [
                        schema_ref(AdminSupportUserSnapshotOut),
                        schema_ref(EmptyObjectOut),
                    ]
                },
                "peer_typing": BOOLEAN_SCHEMA,
            }
        ),
        models=(
            AdminSupportMessageOut,
            AdminSupportTicketOut,
            AdminSupportUserOut,
            AdminSupportUserSnapshotOut,
            EmptyObjectOut,
            SupportMessageButtonOut,
        ),
    ),
)
register_contract(
    "admin_support_ticket_reply_route",
    RouteContract(
        request_content=message_image_request_content(AdminTicketReplyPayload),
        response_schema=ok_envelope_with(
            {
                "ticket": schema_ref(SupportTicketOut),
                "message": schema_ref(AdminSupportMessageOut),
            }
        ),
        models=(
            AdminBroadcastButtonBody,
            AdminTicketReplyPayload,
            AdminSupportMessageOut,
            SupportMessageButtonOut,
            SupportTicketOut,
        ),
    ),
)
register_contract(
    "admin_message_image_route",
    RouteContract(
        response_schema=BINARY_RESPONSE_SCHEMA,
        response_content_type="image/webp",
    ),
)
register_contract(
    "admin_support_ticket_patch_route",
    RouteContract(
        request_model=AdminTicketPatchPayload,
        response_schema=ok_envelope_with({"ticket": schema_ref(SupportTicketOut)}),
        models=(AdminTicketPatchPayload, SupportTicketOut),
    ),
)
register_contract(
    "admin_support_ticket_read_route",
    RouteContract(response_schema=ok_envelope_with()),
)
register_contract(
    "admin_support_ticket_typing_route",
    RouteContract(
        request_model=SupportTypingIn,
        response_schema=ok_envelope_with(),
        models=(SupportTypingIn,),
    ),
)
register_contract(
    "admin_support_stats_route",
    RouteContract(
        response_schema=ok_envelope_with({"stats": schema_ref(AdminSupportStatsOut)}),
        models=(AdminSupportStatsOut,),
    ),
)


def _invalid_request_payload_response(_exc: Exception) -> web.Response:
    return _error(400, "invalid_request", "Invalid request")


def _support_ticket_payload(ticket: SupportTicket) -> dict[str, Any]:
    return SupportTicketOut.from_orm_ticket(ticket).model_dump(mode="json")


def _user_display_name(user: User | None) -> str | None:
    if not user:
        return None
    name = " ".join(
        part.strip() for part in [user.first_name, user.last_name] if part and part.strip()
    ).strip()
    return name or user.username or user.email or str(user.user_id)


def _support_message_payload(
    message: SupportTicketMessage,
    *,
    authors: dict[int, Any] | None = None,
) -> dict[str, Any]:
    author = authors.get(message.author_user_id) if authors and message.author_user_id else None
    return AdminSupportMessageOut.from_orm_message(
        message,
        author_name=_user_display_name(author),
    ).model_dump(mode="json")


def _admin_support_user_payload(user: User | None) -> dict[str, Any]:
    if not user:
        return {}
    return AdminSupportUserOut.from_orm_user(user).model_dump(mode="json")


def _support_limit_offset(request: web.Request) -> tuple[int, int]:
    limit = max(1, min(100, int(request.query.get("limit", 25) or 25)))
    offset = max(0, int(request.query.get("offset", 0) or 0))
    return limit, offset


async def admin_support_tickets_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    limit, offset = _support_limit_offset(request)
    assigned_raw = request.query.get("assigned")
    assigned_admin_id = None
    if assigned_raw and assigned_raw not in {"all", "any"}:
        assigned_admin_id = int(assigned_raw)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        tickets = await support_dal.list_admin_tickets(
            session,
            status=request.query.get("status") or None,
            priority=request.query.get("priority") or None,
            category=request.query.get("category") or None,
            assigned_admin_id=assigned_admin_id,
            search=request.query.get("search") or None,
            sort=request.query.get("sort") or "updated_desc",
            limit=limit,
            offset=offset,
        )
    return _ok(
        {
            "tickets": [
                {
                    **_support_ticket_payload(ticket),
                    "user": _admin_support_user_payload(getattr(ticket, "user", None)),
                }
                for ticket in tickets
            ],
        }
    )


async def admin_support_ticket_detail_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    ticket_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    service = get_support_service(request)
    async with async_session_factory() as session:
        ticket, messages = await support_dal.get_ticket(session, ticket_id, include_internal=True)
        if not ticket:
            return _error(404, "not_found", "Ticket not found")
        user = await user_dal.get_user_by_id(session, ticket.user_id)
        snapshot = await service.build_user_snapshot(user, session=session) if user else {}
        author_ids = {m.author_user_id for m in messages if m.author_user_id is not None}
        authors = {}
        for author_id in author_ids:
            author = await user_dal.get_user_by_id(session, author_id)
            if author:
                authors[author_id] = author
    peer_typing = await is_support_typing(get_settings(request), ticket_id, "user")
    return _ok(
        {
            "ticket": {
                **_support_ticket_payload(ticket),
                "user": _admin_support_user_payload(user),
            },
            "messages": [_support_message_payload(m, authors=authors) for m in messages],
            "user_snapshot": snapshot,
            "peer_typing": peer_typing,
        }
    )


async def _personalize_reply_body(
    request: web.Request,
    *,
    text: str,
    recipient_id: int,
) -> tuple[str, str]:
    """Substitute shortcodes for the ticket owner, and report their language.

    A ticket has exactly one recipient, so unlike a broadcast the reply is
    rendered once and *stored* rendered: the admin and the customer must be
    looking at the same message, and a link resolved months later would point
    somewhere else.
    """

    settings = get_settings(request)
    needed = known_shortcodes(text)
    contexts = {}
    if needed:
        async_session_factory: sessionmaker = get_session_factory(request)
        async with async_session_factory() as session:
            contexts = await load_broadcast_contexts(
                session,
                settings,
                [recipient_id],
                needed,
                _resolve_panel_service(request),
            )
            await session.commit()
    ctx = contexts.get(recipient_id)
    language = str(
        (ctx.language_code if ctx else None) or settings.DEFAULT_LANGUAGE or "en"
    ).strip()
    if not needed:
        return text, language
    return (
        render_broadcast_text(
            text,
            ctx,
            lang=language,
            i18n=get_i18n(request),
            settings=settings,
            bot_username=get_bot_username(request),
            escape=True,
        ),
        language,
    )


async def admin_support_ticket_reply_route(request: web.Request) -> web.Response:
    admin_id = _require_admin_user_id(request)
    ticket_id = int(request.match_info["id"])
    payload, upload = await parse_body_with_optional_image_or_400(
        request,
        AdminTicketReplyPayload,
        validation_error_response_factory=_invalid_request_payload_response,
    )
    try:
        image = await prepare_message_image(upload)
    except MessageImageError as exc:
        return _error(400, exc.code, exc.detail)
    if not payload.body and image is None:
        return _error(400, "empty_text", "Message is empty")
    unknown = sorted(unknown_shortcodes(payload.body))
    if unknown:
        return _error(400, "unknown_shortcode", ", ".join(unknown))
    if payload.body_format == "html":
        html_error = telegram_html_error(payload.body)
        if html_error:
            return _error(400, "invalid_telegram_html", html_error)

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ticket_row = await session.get(SupportTicket, ticket_id)
        if ticket_row is None:
            return _error(404, "not_found", "Ticket not found")
        recipient_id = int(ticket_row.user_id)

    body, language = await _personalize_reply_body(
        request,
        text=payload.body,
        recipient_id=recipient_id,
    )
    encoded_buttons: str | None = None
    if payload.buttons and not payload.is_internal_note:
        try:
            encoded_buttons = encode_support_buttons(
                resolve_broadcast_buttons(
                    payload.buttons,
                    settings=get_settings(request),
                    bot_username=get_bot_username(request),
                    language=language,
                    i18n=get_i18n(request),
                )
            )
        except BroadcastValidationError as exc:
            return _error(400, exc.code, exc.detail)

    try:
        ticket, message = await get_support_service(request).reply_as_admin(
            admin_id,
            ticket_id,
            body,
            is_internal_note=payload.is_internal_note,
            body_format=payload.body_format,
            buttons=encoded_buttons,
            image=image,
        )
    except SupportBodyError:
        return _error(400, "empty_text", "Message is empty")
    except TicketNotFound:
        return _error(404, "not_found", "Ticket not found")
    async with async_session_factory() as session:
        admin = await user_dal.get_user_by_id(session, admin_id)
    await set_support_typing(get_settings(request), ticket_id, "admin", typing=False)
    return _ok(
        {
            "ticket": _support_ticket_payload(ticket),
            "message": _support_message_payload(
                message, authors={admin_id: admin} if admin else {}
            ),
        }
    )


async def admin_message_image_route(request: web.Request) -> web.StreamResponse:
    _require_admin_user_id(request)
    image_id = str(request.match_info["image_id"]).lower()
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        image = await load_message_image(session, image_id)
    if image is None:
        raise web.HTTPNotFound()
    return await message_image_response(image)


async def admin_support_ticket_patch_route(request: web.Request) -> web.Response:
    admin_id = _require_admin_user_id(request)
    ticket_id = int(request.match_info["id"])
    payload = await parse_body_or_400(
        request,
        AdminTicketPatchPayload,
        validation_error_response_factory=_invalid_request_payload_response,
    )
    updates = payload.model_dump(exclude_unset=True)
    try:
        if updates.get("status") == "closed":
            ticket = await get_support_service(request).close_ticket(admin_id, ticket_id)
            updates.pop("status", None)
            if updates:
                ticket = await get_support_service(request)._update_and_audit(
                    admin_id,
                    ticket_id,
                    **updates,
                )
        else:
            ticket = await get_support_service(request)._update_and_audit(
                admin_id,
                ticket_id,
                **updates,
            )
    except TicketNotFound:
        return _error(404, "not_found", "Ticket not found")
    return _ok({"ticket": _support_ticket_payload(ticket)})


async def admin_support_ticket_read_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    ticket_id = int(request.match_info["id"])
    await get_support_service(request).mark_read_as_admin(ticket_id)
    return _ok({})


async def admin_support_ticket_typing_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    ticket_id = int(request.match_info["id"])
    payload = await parse_body_or_400(
        request,
        SupportTypingIn,
        validation_error_response_factory=_invalid_request_payload_response,
    )
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        if await session.get(SupportTicket, ticket_id) is None:
            return _error(404, "not_found", "Ticket not found")
    await set_support_typing(get_settings(request), ticket_id, "admin", typing=payload.typing)
    return _ok({})


async def admin_support_stats_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        stats = await support_dal.admin_stats(session)
    return _ok({"stats": stats})
