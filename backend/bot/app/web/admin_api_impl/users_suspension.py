"""Temporarily stop a single entitlement while keeping the shop account accessible."""

from datetime import UTC, datetime, timedelta

from aiohttp import web
from pydantic import Field, StrictBool

from bot.app.web.context import get_session_factory, get_settings
from bot.app.web.http_contracts import HttpBodyModel
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    RouteContract,
    ok_envelope_with,
    register_contract,
    schema_ref,
)
from bot.services.account_roles import can_ban_account
from bot.utils.traffic_reset import parse_panel_datetime
from db.advisory_locks import acquire_subscription_background_sync_lock
from db.dal import account_cleanup_dal, subscription_dal, user_dal

from .auth import _require_admin_user_id
from .common import _error, _ok, _serialize_subscription
from .user_panel_account import user_panel_service
from .user_schemas import AdminSubscriptionOut
from .users_listing import _invalidate_after_admin_user_mutation


class SubscriptionSuspensionBody(HttpBodyModel):
    subscription_id: int = Field(strict=True, gt=0)
    suspended: StrictBool


register_contract(
    "admin_user_subscription_suspension_route",
    RouteContract(
        request_model=SubscriptionSuspensionBody,
        models=(AdminSubscriptionOut,),
        response_schema=ok_envelope_with({"subscription": schema_ref(AdminSubscriptionOut)}),
    ),
)


async def admin_user_subscription_suspension_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    target = int(request.match_info["user_id"])
    body = await parse_body_or_400(request, SubscriptionSuspensionBody)
    panel = user_panel_service(request)
    if panel is None:
        return _error(503, "panel_service_unavailable")

    async with get_session_factory(request)() as session:
        # A durable intent precedes the panel write. Reacquire the locks after
        # committing it so a lost response or a restart can be retried safely.
        reserved = False
        while True:
            await acquire_subscription_background_sync_lock(session)
            if body.suspended and not await can_ban_account(session, actor, target):
                return _error(403, "forbidden")
            user = await user_dal.lock_user_by_id(session, target, with_suspension=True)
            sub = await subscription_dal.get_subscription_by_id_for_update(
                session, body.subscription_id
            )
            if user is None or sub is None or sub.user_id != target:
                return _error(404, "not_found")
            if user.is_banned:
                return _error(409, "account_banned")
            reference = sub.panel_user_uuid
            if (
                not reference
                or (user.panel_user_uuid and user.panel_user_uuid != reference)
                or await account_cleanup_dal.panel_identity_is_shared(session, target, reference)
            ):
                return _error(409, "subscription_not_current")

            if sub.suspended_at is None:
                current = await subscription_dal.get_active_subscription_by_user_id(
                    session, target, user.panel_user_uuid
                )
                if (
                    reserved
                    or user.suspended_subscription_id
                    or current is None
                    or current.subscription_id != sub.subscription_id
                ):
                    return _error(409, "subscription_not_current")
                if not body.suspended:
                    return _ok({"subscription": _serialize_subscription(sub)})
                before = await panel.get_user_by_uuid(reference, use_cache=False)
                if not before:
                    return _error(502, "panel_status_update_failed")
                expiry = parse_panel_datetime(before.get("expireAt"))
                now = datetime.now(UTC)
                if before.get("status") != "ACTIVE" or expiry is None or expiry <= now:
                    return _error(409, "subscription_not_current")
                sub.suspended_at = now
                sub.suspension_end_date = expiry
                await session.commit()
                reserved = True
                continue
            break

        if body.suspended:
            if sub.is_active:
                # A previous attempt may already have disabled the panel user.
                snapshot = await panel.get_user_by_uuid(reference, use_cache=False)
                if not snapshot:
                    return _error(502, "panel_status_update_failed")
                if snapshot.get("status") != "DISABLED":
                    if not reserved:
                        sub.suspended_at = datetime.now(UTC)
                    if not await panel.update_user_status_on_panel(reference, False):
                        checked = await panel.get_user_by_uuid(reference, use_cache=False)
                        if not checked or checked.get("status") != "DISABLED":
                            if checked and checked.get("status") in {
                                "ACTIVE",
                                "LIMITED",
                                "EXPIRED",
                            }:
                                # Known failure: there was no pause to compensate. An
                                # unknown result keeps the intent for a later retry.
                                sub.suspended_at = None
                                sub.suspension_end_date = None
                                await session.commit()
                                await _invalidate_after_admin_user_mutation(
                                    get_settings(request), target
                                )
                            return _error(502, "panel_status_update_failed")
                sub.is_active = False
                sub.status_from_panel = "DISABLED"
        else:
            if sub.is_active or sub.suspension_end_date is None:
                return _error(409, "subscription_not_current")
            snapshot = await panel.get_user_by_uuid(reference, use_cache=False)
            if not snapshot:
                return _error(502, "panel_status_update_failed")
            # If enable succeeded but the local commit failed, adopt the exact
            # confirmed expiry. Never add a second pause to an extended date.
            expiry = parse_panel_datetime(snapshot.get("expireAt"))
            if (
                snapshot.get("status") != "ACTIVE"
                or expiry is None
                or expiry <= sub.suspension_end_date
            ):
                now = datetime.now(UTC)
                expected = sub.suspension_end_date + max(now - sub.suspended_at, timedelta())
                updated = await panel.update_user_details_on_panel(
                    reference, {"expireAt": expected.isoformat()}
                )
                expiry = parse_panel_datetime((updated or {}).get("expireAt"))
                if expiry is None or abs(expiry - expected) >= timedelta(seconds=1):
                    return _error(502, "panel_status_update_failed")
                if not await panel.update_user_status_on_panel(reference, True):
                    return _error(502, "panel_status_update_failed")
            sub.end_date = expiry
            sub.is_active = True
            sub.status_from_panel = "ACTIVE"
            sub.suspended_at = None
            sub.suspension_end_date = None
        payload = _serialize_subscription(sub)
        await session.commit()
    await _invalidate_after_admin_user_mutation(get_settings(request), target)
    return _ok({"subscription": payload})
