from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
    get_settings,
    get_support_service,
)
from bot.app.web.support_schemas import SupportMessageOut, SupportTicketOut, SupportTypingIn
from bot.services.support_presence import is_support_typing, set_support_typing
from bot.services.support_service import TicketForbidden, TicketNotFound, TicketRateLimited
from db.dal import support_dal, user_dal
from db.models import SupportTicket, SupportTicketMessage

from .common import (
    _json_error,
    _parse_model_payload,
    _require_user_id,
)
from .payloads import (
    CreateTicketPayload,
    TicketReplyPayload,
)
from .response_helpers import json_response


def _support_ticket_payload(ticket: SupportTicket) -> dict[str, Any]:
    return SupportTicketOut.from_orm_ticket(ticket).model_dump(mode="json")


def _support_message_payload(message: SupportTicketMessage) -> dict[str, Any]:
    return SupportMessageOut.from_orm_message(message).model_dump(mode="json")


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
    peer_typing = await is_support_typing(get_settings(request), ticket_id, "admin")
    return json_response(
        {
            "ok": True,
            "ticket": _support_ticket_payload(ticket),
            "messages": [_support_message_payload(m) for m in messages],
            "peer_typing": peer_typing,
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
    await set_support_typing(get_settings(request), ticket_id, "user", typing=False)
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


async def support_ticket_typing_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    ticket_id = int(request.match_info["id"])
    payload = await _parse_model_payload(request, SupportTypingIn)
    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        ticket = await session.get(SupportTicket, ticket_id)
        if not ticket or ticket.user_id != user_id:
            return _json_error(404, "not_found", "Ticket not found")
    await set_support_typing(get_settings(request), ticket_id, "user", typing=payload.typing)
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
