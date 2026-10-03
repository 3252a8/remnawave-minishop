"""Start the paid traffic counter independently of the preceding trial."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from bot.utils.traffic_reset import panel_last_traffic_reset_at

from ._typing import SubscriptionServiceMixinContract

logger = logging.getLogger(__name__)


async def reset_trial_traffic_for_paid_activation(
    service: SubscriptionServiceMixinContract,
    panel_user_uuid: str,
) -> dict[str, Any] | None:
    before: dict[str, Any] | None = await service._get_panel_user_for_entitlement_verification(
        panel_user_uuid
    )
    before_used, _, _ = service._extract_panel_traffic_details(before or {})
    before_reset_at = panel_last_traffic_reset_at(before)
    requested_at = datetime.now(UTC)
    try:
        reset_ok = await service.panel_service.reset_user_traffic(panel_user_uuid)
    except Exception:
        logger.exception("Trial traffic reset failed before paid activation: %s", panel_user_uuid)
        return None
    if not reset_ok:
        logger.warning(
            "Panel rejected trial traffic reset before paid activation: %s", panel_user_uuid
        )
        return None

    # A 2xx action response can arrive before the reset is visible. Read independently
    # without repeating the reset: another reset could erase traffic served meanwhile.
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(0.2 * attempt)
        after: dict[str, Any] | None = await service._get_panel_user_for_entitlement_verification(
            panel_user_uuid
        )
        used, _, _ = service._extract_panel_traffic_details(after or {})
        reset_at = panel_last_traffic_reset_at(after)
        fresh_reset_marker = (
            reset_at is not None
            and reset_at != before_reset_at
            and reset_at >= requested_at - timedelta(seconds=1)
        )
        counter_was_reset = (
            used is not None
            and used >= 0
            and (
                used == 0 or (before_used is not None and used < before_used) or fresh_reset_marker
            )
        )
        if not counter_was_reset:
            continue
        lifetime = service._extract_lifetime_used_traffic(after or {})
        lifetime_start = lifetime - used if lifetime is not None and lifetime >= used else None
        # Upsert reuses the trial row. Discard its old accounting snapshot so the
        # worker cannot charge trial usage against the newly purchased allowance.
        return {
            "traffic_used_bytes": used,
            "traffic_period_lifetime_start_bytes": lifetime_start,
            "traffic_topup_accounting_state": None,
            "period_start_at": reset_at or requested_at,
        }

    logger.warning(
        "Trial traffic reset was not persisted before paid activation: %s", panel_user_uuid
    )
    return None
