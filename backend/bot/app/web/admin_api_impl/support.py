from typing import Annotated, Any, Literal

from aiohttp import web
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
    get_support_service,
)
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
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
    SupportTicketOut,
)
from bot.services.support_service import TicketNotFound
from db.dal import support_dal, user_dal
from db.models import SupportTicket, SupportTicketMessage, User

from .auth import (
    _require_admin_user_id,
)
from .common import (
    _error,
    _ok,
)

TicketBodyString = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class AdminTicketReplyPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    body: TicketBodyString
    is_internal_note: bool = False

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("empty_text")
        return stripped


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
            }
        ),
        models=(
            AdminSupportMessageOut,
            AdminSupportTicketOut,
            AdminSupportUserOut,
            AdminSupportUserSnapshotOut,
            EmptyObjectOut,
        ),
    ),
)
register_contract(
    "admin_support_ticket_reply_route",
    RouteContract(
        request_model=AdminTicketReplyPayload,
        response_schema=ok_envelope_with(
            {
                "ticket": schema_ref(SupportTicketOut),
                "message": schema_ref(AdminSupportMessageOut),
            }
        ),
        models=(AdminTicketReplyPayload, AdminSupportMessageOut, SupportTicketOut),
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
    return _ok(
        {
            "ticket": {
                **_support_ticket_payload(ticket),
                "user": _admin_support_user_payload(user),
            },
            "messages": [_support_message_payload(m, authors=authors) for m in messages],
            "user_snapshot": snapshot,
        }
    )


async def admin_support_ticket_reply_route(request: web.Request) -> web.Response:
    admin_id = _require_admin_user_id(request)
    ticket_id = int(request.match_info["id"])
    payload = await parse_body_or_400(
        request,
        AdminTicketReplyPayload,
        validation_error_response_factory=_invalid_request_payload_response,
    )
    try:
        ticket, message = await get_support_service(request).reply_as_admin(
            admin_id,
            ticket_id,
            payload.body,
            is_internal_note=payload.is_internal_note,
        )
    except TicketNotFound:
        return _error(404, "not_found", "Ticket not found")
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        admin = await user_dal.get_user_by_id(session, admin_id)
    return _ok(
        {
            "ticket": _support_ticket_payload(ticket),
            "message": _support_message_payload(
                message, authors={admin_id: admin} if admin else {}
            ),
        }
    )


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


async def admin_support_stats_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        stats = await support_dal.admin_stats(session)
    return _ok({"stats": stats})
