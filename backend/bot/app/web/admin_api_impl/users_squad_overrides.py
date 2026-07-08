from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.web.context import (
    get_optional_subscription_service,
    get_panel_service,
    get_session_factory,
    get_settings,
)
from bot.app.web.request_parsing import parse_body_or_400
from db.dal import message_log_dal, subscription_dal, user_dal
from db.dal import user_panel_squad_override_dal as override_dal
from db.models import Subscription, User

from .auth import _require_admin_user_id
from .common import _error, _ok
from .squad_override_schemas import (
    AdminPanelSquadOverridesOut,
    AdminUserSquadOverridesPatchBody,
)
from .users_listing import _invalidate_after_admin_user_mutation

logger = logging.getLogger(__name__)


def _panel_uuid_for_user(user: User, active_sub: Subscription | None) -> str | None:
    return (
        str(
            getattr(user, "panel_user_uuid", None)
            or getattr(active_sub, "panel_user_uuid", None)
            or ""
        ).strip()
        or None
    )


async def _build_overrides_payload(
    subscription_service: Any,
    session: Any,
    *,
    user_id: int,
    panel_user_uuid: str,
    active_sub: Subscription | None,
    panel_user_snapshot: dict[str, Any] | None = None,
    panel_snapshot_available: bool = False,
    discover_panel_overrides: bool = False,
) -> dict[str, Any]:
    summary = await subscription_service.panel_squad_overrides_summary(
        session,
        user_id=user_id,
        panel_user_uuid=panel_user_uuid,
        subscription=active_sub,
        panel_user_snapshot=panel_user_snapshot,
        panel_snapshot_available=panel_snapshot_available,
        discover_panel_overrides=discover_panel_overrides,
    )
    return AdminPanelSquadOverridesOut.model_validate(summary).model_dump(mode="json")


async def admin_user_squad_overrides_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings = get_settings(request)
    subscription_service = get_optional_subscription_service(request)
    if subscription_service is None:
        return _error(503, "subscription_service_unavailable")
    body = await parse_body_or_400(request, AdminUserSquadOverridesPatchBody)
    async_session_factory: sessionmaker = get_session_factory(request)

    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")
        active_sub = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        panel_user_uuid = _panel_uuid_for_user(user, active_sub)
        if not panel_user_uuid:
            return _error(404, "no_panel_user")

        for squad_uuid in body.remove_internal_squad_uuids:
            await override_dal.deactivate_internal_override(
                session,
                user_id=target_id,
                panel_user_uuid=panel_user_uuid,
                squad_uuid=squad_uuid,
            )
        for squad_uuid in body.add_internal_squad_uuids:
            await override_dal.upsert_internal_override(
                session,
                user_id=target_id,
                panel_user_uuid=panel_user_uuid,
                squad_uuid=squad_uuid,
                source=override_dal.OVERRIDE_SOURCE_ADMIN,
                created_by_admin_id=actor_id,
            )
        if body.external_mode is not None:
            await override_dal.set_external_override(
                session,
                user_id=target_id,
                panel_user_uuid=panel_user_uuid,
                mode=body.external_mode,
                squad_uuid=body.external_squad_uuid,
                source=override_dal.OVERRIDE_SOURCE_ADMIN,
                created_by_admin_id=actor_id,
            )

        panel_response: dict[str, Any] | None = None
        if body.sync_panel:
            managed_squads, _managed_source = (
                subscription_service._managed_panel_squad_uuids_for_subscription(active_sub)
            )
            effective_fields = await subscription_service.build_effective_panel_squad_fields(
                session,
                user_id=target_id,
                panel_user_uuid=panel_user_uuid,
                managed_internal_squads=managed_squads,
                discover_panel_overrides=False,
                include_internal_squads=True,
                source="admin_squad_overrides",
            )
            panel_response = await subscription_service.panel_service.update_user_details_on_panel(
                panel_user_uuid,
                {"uuid": panel_user_uuid, **effective_fields},
            )
            if not panel_response or panel_response.get("error"):
                await session.rollback()
                logger.warning(
                    "Admin squad override panel sync failed for user %s uuid=%s: %s",
                    target_id,
                    panel_user_uuid,
                    panel_response,
                )
                return _error(502, "panel_update_failed")

        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_squad_overrides_webapp",
                "content": (
                    f"add={','.join(body.add_internal_squad_uuids) or '-'} "
                    f"remove={','.join(body.remove_internal_squad_uuids) or '-'} "
                    f"external={body.external_mode or '-'} "
                    f"sync={'yes' if body.sync_panel else 'no'}"
                ),
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        payload = await _build_overrides_payload(
            subscription_service,
            session,
            user_id=target_id,
            panel_user_uuid=panel_user_uuid,
            active_sub=active_sub,
            panel_user_snapshot=panel_response,
            panel_snapshot_available=bool(panel_response),
            discover_panel_overrides=False,
        )
        await session.commit()

    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({"panel_squad_overrides": payload})


async def admin_user_squad_overrides_refresh_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    target_id = int(request.match_info["user_id"])
    settings = get_settings(request)
    subscription_service = get_optional_subscription_service(request)
    if subscription_service is None:
        return _error(503, "subscription_service_unavailable")
    panel_service = get_panel_service(request) or getattr(
        subscription_service,
        "panel_service",
        None,
    )
    if panel_service is None:
        return _error(503, "panel_unavailable")

    async_session_factory: sessionmaker = get_session_factory(request)
    async with async_session_factory() as session:
        user = await user_dal.get_user_by_id(session, target_id)
        if not user:
            return _error(404, "not_found")
        active_sub = await subscription_dal.get_active_subscription_by_user_id(session, target_id)
        panel_user_uuid = _panel_uuid_for_user(user, active_sub)
        if not panel_user_uuid:
            return _error(404, "no_panel_user")

        try:
            panel_user_snapshot = await panel_service.get_user_by_uuid(panel_user_uuid)
        except Exception as exc:
            logger.warning(
                "Admin squad override refresh failed for user %s uuid=%s: %s",
                target_id,
                panel_user_uuid,
                exc,
            )
            return _error(502, "panel_request_failed", str(exc))
        if not isinstance(panel_user_snapshot, dict):
            return _error(502, "panel_request_failed")

        payload = await _build_overrides_payload(
            subscription_service,
            session,
            user_id=target_id,
            panel_user_uuid=panel_user_uuid,
            active_sub=active_sub,
            panel_user_snapshot=panel_user_snapshot,
            panel_snapshot_available=True,
            discover_panel_overrides=True,
        )
        await message_log_dal.create_message_log(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_squad_overrides_refresh_webapp",
                "content": "refresh_from_panel",
                "is_admin_event": True,
                "target_user_id": target_id,
            },
        )
        await session.commit()

    await _invalidate_after_admin_user_mutation(settings, target_id)
    return _ok({"panel_squad_overrides": payload})
