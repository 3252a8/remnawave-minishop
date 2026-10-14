"""Authenticated account payment history."""

from aiohttp import web

from bot.app.web.context import get_session_factory
from db.dal.payment_history_dal import list_user_payments

from .common import _json_error, _require_user_id
from .payment_history_schemas import PaymentHistoryItemOut
from .response_helpers import json_response


async def payment_history_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    try:
        limit = min(100, max(1, int(request.query.get("limit", "10"))))
        offset = max(0, int(request.query.get("offset", "0")))
    except (ValueError, TypeError):
        return _json_error(400, "invalid_pagination", "Invalid pagination")

    async with get_session_factory(request)() as session:
        payments, total = await list_user_payments(session, user_id, limit=limit, offset=offset)
        items = [
            PaymentHistoryItemOut.from_orm_payment(payment).model_dump(mode="json")
            for payment in payments
        ]
    return json_response(
        {"ok": True, "items": items, "total": total, "limit": limit, "offset": offset}
    )
