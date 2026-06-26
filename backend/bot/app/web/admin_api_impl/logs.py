from aiohttp import web
from schemas import AdminLogsListOut, LogOut
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_session_factory,
)
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from db.dal import message_log_dal

from .auth import _require_admin_user_id
from .common import _error, _ok, _serialize_log

register_contract(
    "admin_logs_route",
    RouteContract(
        response_schema=ok_envelope_for(AdminLogsListOut),
        models=(AdminLogsListOut, LogOut),
    ),
)


async def admin_logs_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async_session_factory: sessionmaker = get_session_factory(request)

    page = max(0, int(request.query.get("page", 0) or 0))
    page_size = min(200, max(1, int(request.query.get("page_size", 50) or 50)))
    user_filter = request.query.get("user_id")

    async with async_session_factory() as session:
        if user_filter:
            try:
                user_id = int(user_filter)
            except (TypeError, ValueError):
                return _error(400, "invalid_user_id")
            entries = await message_log_dal.get_user_message_logs(
                session, user_id, page_size, page * page_size
            )
            total = await message_log_dal.count_user_message_logs(session, user_id)
        else:
            entries = await message_log_dal.get_all_message_logs(
                session, page_size, page * page_size
            )
            total = await message_log_dal.count_all_message_logs(session)

    return _ok(
        {
            "logs": [_serialize_log(entry) for entry in entries],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }
    )
