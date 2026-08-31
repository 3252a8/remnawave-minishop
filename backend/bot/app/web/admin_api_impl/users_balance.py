from __future__ import annotations

from uuid import uuid4

from aiohttp import web

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.request_parsing import parse_body_or_400
from bot.services.user_balance_service import UserBalanceError, UserBalanceService

from .auth import _require_admin_user_id
from .common import _error, _ok
from .schemas import AdminUserBalanceAdjustmentBody, AdminUserBalanceConversionBody
from .users_listing import _invalidate_after_admin_user_mutation


def _balance_error(exc: UserBalanceError) -> web.Response:
    return _error(exc.status, exc.code, exc.message or str(exc))


async def admin_user_balance_adjustment_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserBalanceAdjustmentBody)
    key = body.idempotency_key.strip() or f"admin-balance:{target_id}:{actor_id}:{uuid4().hex}"
    service = UserBalanceService(get_settings(request))
    try:
        async with get_session_factory(request)() as session, session.begin():
            await service.admin_adjust(
                session,
                user_id=target_id,
                actor_admin_id=actor_id,
                mode=body.mode,
                amount=body.amount,
                reason=body.reason,
                idempotency_key=key,
            )
            snapshot = await service.snapshot(
                session,
                user_id=target_id,
                include_history=True,
            )
    except UserBalanceError as exc:
        return _balance_error(exc)
    await _invalidate_after_admin_user_mutation(service.settings, target_id, include_devices=False)
    return _ok({"balance": {"ok": True, **snapshot}})


async def admin_user_balance_conversion_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserBalanceConversionBody)
    key = body.idempotency_key.strip() or f"balance-conversion:{target_id}:{uuid4().hex}"
    service = UserBalanceService(get_settings(request))
    try:
        async with get_session_factory(request)() as session, session.begin():
            await service.convert(
                session,
                user_id=target_id,
                actor_admin_id=actor_id,
                direction=body.direction,
                amount=body.amount,
                reason=body.reason,
                idempotency_key=key,
            )
            snapshot = await service.snapshot(
                session,
                user_id=target_id,
                include_history=True,
            )
    except UserBalanceError as exc:
        return _balance_error(exc)
    await _invalidate_after_admin_user_mutation(service.settings, target_id, include_devices=False)
    return _ok({"balance": {"ok": True, **snapshot}})
