"""Explicit administrator-assisted account merge using the customer merge rules."""

import logging

from aiohttp import web
from pydantic import Field
from sqlalchemy import text

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import RouteContract, ok_envelope_for, register_contract
from bot.app.web.webapp.auth_panel import (
    _build_account_merge_notice,
    _merge_users_for_web,
    _sync_merged_panel_identity_for_user,
)
from bot.services.account_roles import is_admin
from db.dal import message_log_dal, user_dal
from db.dal.user_merge_dal import UserMergeConflictError

from .auth import _require_admin_user_id
from .common import _error, _ok
from .users_listing import _invalidate_after_admin_user_mutation
from .users_merge_context import has_admin_merge_privileges

logger = logging.getLogger(__name__)


class AdminUserMergeBody(HttpBodyModel):
    source_user_id: int = Field(strict=True)
    confirmation_user_id: int = Field(strict=True)


class AdminUserMergeOut(HttpResponseModel):
    user_id: int
    source_user_id: int
    panel_reconciliation_pending: bool = False
    final_end_date: str | None = None


register_contract(
    "admin_user_merge_route",
    RouteContract(
        request_model=AdminUserMergeBody,
        response_schema=ok_envelope_for(AdminUserMergeOut),
        models=(AdminUserMergeBody, AdminUserMergeOut),
    ),
)


async def admin_user_merge_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, AdminUserMergeBody)
    source_id = body.source_user_id
    if source_id == target_id or not source_id or not target_id:
        return _error(400, "account_merge_not_required")
    if body.confirmation_user_id != target_id:
        return _error(400, "account_merge_confirmation_required")
    if actor_id in {source_id, target_id}:
        return _error(403, "account_merge_privileged_source")

    settings = get_settings(request)
    pending = False
    async with get_session_factory(request)() as session:
        try:
            # Serialize with role grants/revocations, then recheck authority.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": 68533712981372}
            )
            if not await is_admin(session, actor_id):
                return _error(403, "forbidden")
            for participant_id in sorted({source_id, target_id}):
                await user_dal.lock_user_by_id(session, participant_id)
            source = await user_dal.get_user_by_id(session, source_id)
            target = await user_dal.get_user_by_id(session, target_id)
            if source is None or target is None:
                return _error(404, "not_found")
            if await has_admin_merge_privileges(session, (source_id, target_id)):
                return _error(409, "account_merge_privileged_source")
            source_panel_uuid = source.panel_user_uuid
            merged = await _merge_users_for_web(
                request,
                session,
                source_user_id=source_id,
                target_user_id=target_id,
                reason=f"admin_manual_merge:{actor_id}",
                send_user_email=True,
            )
            notice = await _build_account_merge_notice(
                session,
                merged_user=merged,
                source_user_id=source_id,
                source_panel_uuid=source_panel_uuid,
                settings=settings,
            )
            await message_log_dal.create_message_log_no_commit(
                session,
                {
                    "user_id": actor_id,
                    "event_type": "admin_merge_users_webapp",
                    "content": f"actor={actor_id}; source={source_id}; target={target_id}",
                    "is_admin_event": True,
                },
            )
            await session.commit()
        except UserMergeConflictError as exc:
            await session.rollback()
            return _error(409, exc.code, str(exc))
        except Exception:
            await session.rollback()
            logger.exception("Administrator account merge failed")
            return _error(500, "account_merge_failed")

        if source_panel_uuid or merged.panel_user_uuid:
            try:
                pending = not await _sync_merged_panel_identity_for_user(
                    request,
                    merged,
                    source_panel_uuid=source_panel_uuid,
                    final_panel_uuid=merged.panel_user_uuid,
                    session=session,
                )
            except Exception:
                pending = True
                logger.exception("Panel reconciliation pending after administrator account merge")

    for participant_id in (source_id, target_id):
        try:
            await _invalidate_after_admin_user_mutation(settings, participant_id)
        except Exception:
            logger.warning("Account merge committed; cache invalidation failed", exc_info=True)
    payload = AdminUserMergeOut(
        user_id=target_id,
        source_user_id=source_id,
        panel_reconciliation_pending=pending,
        final_end_date=notice.get("final_end_date"),
    )
    return _ok(payload.model_dump(mode="json"))
