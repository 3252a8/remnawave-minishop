from bot.app.web.context import (
    get_session_factory,
    get_support_service,
)
from bot.services.support_service import TicketForbidden, TicketNotFound, TicketRateLimited
from db.dal import support_dal, user_dal
from db.models import SupportTicket, SupportTicketMessage

from ._runtime import (
    Any,
    Dict,
    json_response,
    sessionmaker,
    web,
)
from .common import (
    _json_error,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import (
    CreateTicketPayload,
    TicketReplyPayload,
)


def _support_ticket_payload(ticket: SupportTicket) -> Dict[str, Any]:
    return {
        "ticket_id": ticket.ticket_id,
        "user_id": ticket.user_id,
        "subject": ticket.subject,
        "category": ticket.category,
        "priority": ticket.priority,
        "status": ticket.status,
        "assigned_admin_id": ticket.assigned_admin_id,
        "last_message_at": ticket.last_message_at.isoformat() if ticket.last_message_at else None,
        "last_message_role": ticket.last_message_role,
        "unread_user_count": int(ticket.unread_user_count or 0),
        "unread_admin_count": int(ticket.unread_admin_count or 0),
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
    }


def _support_message_payload(message: SupportTicketMessage) -> Dict[str, Any]:
    return {
        "message_id": message.message_id,
        "ticket_id": message.ticket_id,
        "author_role": message.author_role,
        "author_user_id": message.author_user_id,
        "body": message.body,
        "is_internal_note": bool(message.is_internal_note),
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "read_by_user_at": message.read_by_user_at.isoformat() if message.read_by_user_at else None,
        "read_by_admin_at": message.read_by_admin_at.isoformat()
        if message.read_by_admin_at
        else None,
    }


def _support_limit_offset(request: web.Request) -> tuple[int, int]:
    limit = max(1, min(100, int(request.query.get("limit", 25) or 25)))
    offset = max(0, int(request.query.get("offset", 0) or 0))
    return limit, offset


async def support_tickets_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    limit, offset = _support_limit_offset(request)
    status_filter = request.query.get("status") or None
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        tickets = await support_dal.list_user_tickets(
            session,
            user_id,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
        )
        counts = await support_dal.user_ticket_counts(session, user_id)
    return json_response(
        {
            "ok": True,
            "tickets": [_support_ticket_payload(t) for t in tickets],
            "counts": counts,
        }
    )


async def support_create_ticket_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    payload = await _parse_model_payload(request, CreateTicketPayload)
    service = get_support_service(request)
    try:
        ticket = await service.create_ticket(
            user_id,
            payload.subject,
            payload.category,
            payload.priority,
            payload.body,
        )
    except TicketForbidden:
        return _json_error(403, "ticket_forbidden", "Support ticket action is forbidden")
    except TicketRateLimited:
        return _json_error(429, "ticket_rate_limited", "Too many support tickets")
    return json_response({"ok": True, "ticket": _support_ticket_payload(ticket)})


async def support_ticket_detail_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    ticket_id = int(request.match_info["id"])
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ticket, messages = await support_dal.get_ticket(session, ticket_id, include_internal=False)
        if not ticket or ticket.user_id != user_id:
            return _json_error(404, "not_found", "Ticket not found")
    return json_response(
        {
            "ok": True,
            "ticket": _support_ticket_payload(ticket),
            "messages": [_support_message_payload(m) for m in messages],
        }
    )


async def support_ticket_reply_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    ticket_id = int(request.match_info["id"])
    payload = await _parse_model_payload(request, TicketReplyPayload)
    service = get_support_service(request)
    try:
        ticket, message = await service.reply_as_user(user_id, ticket_id, payload.body)
    except TicketForbidden:
        return _json_error(403, "ticket_forbidden", "Support ticket action is forbidden")
    except TicketNotFound:
        return _json_error(404, "not_found", "Ticket not found")
    return json_response(
        {
            "ok": True,
            "ticket": _support_ticket_payload(ticket),
            "message": _support_message_payload(message),
        }
    )


async def support_ticket_read_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    ticket_id = int(request.match_info["id"])
    service = get_support_service(request)
    try:
        await service.mark_read_as_user(user_id, ticket_id)
    except TicketNotFound:
        return _json_error(404, "not_found", "Ticket not found")
    return json_response({"ok": True})


async def support_unread_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user and user.is_banned:
            return _json_error(403, "ticket_forbidden", "Support ticket action is forbidden")
        unread = await support_dal.count_user_unread(session, user_id)
    return json_response({"ok": True, "unread": unread})
