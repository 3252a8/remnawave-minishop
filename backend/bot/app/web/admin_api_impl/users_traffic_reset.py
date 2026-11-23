import asyncio
import logging
from datetime import UTC, datetime

from aiohttp import web

from bot.app.web.context import (
    get_optional_subscription_service,
    get_session_factory,
    get_settings,
)
from bot.services.regular_topup_settlement import regular_topup_period, settle_regular_topup
from bot.services.subscription_order_terms import gift_tariff
from bot.utils.traffic_reset import (
    panel_last_traffic_reset_at,
    panel_traffic_limit_strategy,
    traffic_accounting_period_start,
)
from db.advisory_locks import acquire_subscription_background_sync_lock
from db.dal import message_log_dal, subscription_dal

from .auth import _require_admin_user_id
from .common import _error, _is_trial_subscription, _ok
from .users_listing import _invalidate_after_admin_user_mutation

logger = logging.getLogger(__name__)


async def admin_user_traffic_reset_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    user_id = int(request.match_info["user_id"])
    service = get_optional_subscription_service(request)
    if service is None:
        return _error(503, "subscription_service_unavailable")
    panel = service.panel_service
    async with get_session_factory(request)() as session:
        await acquire_subscription_background_sync_lock(session)
        sub = await subscription_dal.get_active_subscription_by_user_id_for_update(session, user_id)
        if sub is None:
            return _error(404, "no_active_subscription")
        try:
            tariff = gift_tariff(sub) or (
                service._resolve_tariff(sub.tariff_key) if sub.tariff_key else None
            )
        except ValueError:
            tariff = None
        if tariff is None or tariff.billing_model != "period" or _is_trial_subscription(sub):
            return _error(400, "traffic_reset_period_required")
        panel_id = str(sub.panel_user_uuid or "")
        if not panel_id:
            return _error(404, "no_panel_user")
        before = await service._get_panel_user_for_entitlement_verification(panel_id)
        used, _, _ = service._extract_panel_traffic_details(before or {})
        lifetime = service._extract_lifetime_used_traffic(before or {})
        if before is None or used is None or lifetime is None or not 0 <= used <= lifetime:
            return _error(502, "traffic_reset_snapshot_unavailable")
        if used == 0:
            return _ok({})
        now = datetime.now(UTC)
        previous_start = sub.period_start_at
        strategy = panel_traffic_limit_strategy(
            before, service._period_tariff_traffic_strategy(tariff)
        )
        current_start = traffic_accounting_period_start(
            strategy,
            now,
            subscription_start_at=sub.start_date,
            previous_period_start_at=previous_start,
            panel_user_data=before,
        )
        await settle_regular_topup(
            session,
            sub,
            tariff,
            subscription_service=service,
            used_bytes=used,
            panel_user_data=before,
            previous_period_start=previous_start,
            period_start=current_start,
            traffic_strategy=strategy,
            now=now,
            usage_source=panel,
        )
        sub.period_start_at = current_start
        acknowledged = False
        try:
            acknowledged = await panel.reset_user_traffic(panel_id)
        except Exception:
            logger.exception("Admin regular traffic reset request failed for user %s", user_id)
        after = None
        reset_used = None
        reset_at = None
        if acknowledged:
            for attempt in range(3):
                if attempt:
                    await asyncio.sleep(0.2 * attempt)
                after = await service._get_panel_user_for_entitlement_verification(panel_id)
                reset_used, _, _ = service._extract_panel_traffic_details(after or {})
                reset_at = panel_last_traffic_reset_at(after)
                reset_lifetime = service._extract_lifetime_used_traffic(after or {})
                if (
                    reset_used is not None
                    and reset_lifetime is not None
                    and 0 <= reset_used <= reset_lifetime
                    and reset_lifetime - reset_used >= lifetime
                    and (used > reset_used or reset_at != panel_last_traffic_reset_at(before))
                ):
                    break
            else:
                after = None
        if after is None or reset_used is None:
            # Keep the last known allowance and observed overflow so a delayed
            # reset can still be settled by the worker, without repeating it.
            await session.commit()
            return _error(502, "traffic_reset_unconfirmed")
        new_start = reset_at or now
        await settle_regular_topup(
            session,
            sub,
            tariff,
            subscription_service=service,
            used_bytes=reset_used,
            panel_user_data=after,
            previous_period_start=current_start,
            period_start=new_start,
            traffic_strategy=strategy,
            now=datetime.now(UTC),
            usage_source=panel,
            manual_reset=True,
        )
        sub.period_start_at = new_start
        sub.traffic_used_bytes = reset_used
        state = regular_topup_period(sub)
        limit_synchronized = True
        if state is not None:
            desired = (
                state.allowance_bytes + int(sub.topup_balance_bytes or 0)
                if state.allowance_bytes
                else 0
            )
            _, observed, _ = service._extract_panel_traffic_details(after)
            if observed != desired:
                payload = {"trafficLimitBytes": desired}
                try:
                    updated = await panel.update_user_details_on_panel(panel_id, payload)
                    confirmed = await service._confirmed_panel_entitlement(
                        panel_id, updated, payload, source="admin_traffic_reset"
                    )
                    limit_synchronized = confirmed is not None
                except Exception:
                    logger.exception(
                        "Could not sync traffic limit after reset for user %s", user_id
                    )
                    limit_synchronized = False
            if limit_synchronized:
                sub.traffic_limit_bytes = desired
        await message_log_dal.create_message_log_no_commit(
            session,
            {
                "user_id": actor_id,
                "event_type": "admin_traffic_reset_webapp",
                "content": f"used_bytes={used}; panel_limit_synced={limit_synchronized}",
                "is_admin_event": True,
                "target_user_id": user_id,
            },
        )
        await session.commit()
    await _invalidate_after_admin_user_mutation(get_settings(request), user_id)
    if not limit_synchronized:
        return _error(502, "traffic_reset_limit_unconfirmed")
    return _ok({})
