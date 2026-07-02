"""Gate that decides when traffic top-up offers are available to a user.

Mirrors the web app rules (``frontend/src/lib/webapp/billingView.ts``): the
offer unlocks once usage crosses ``TRAFFIC_TOPUP_UNLOCK_PERCENT`` of the
limit, except for traffic-billed tariffs (buying packages *is* the product)
and tariffs with the ``topup_always_available`` admin toggle enabled.
"""

import logging
from dataclasses import dataclass
from typing import Any

from config.settings import Settings

logger = logging.getLogger(__name__)

# Used-traffic percent from which top-up offers unlock.
# Keep in sync with TRAFFIC_TOPUP_UNLOCK_PERCENT in frontend/src/App.svelte.
TRAFFIC_TOPUP_UNLOCK_PERCENT = 80


@dataclass(frozen=True)
class TrafficTopupAvailability:
    regular_offer_exists: bool = False
    premium_offer_exists: bool = False
    regular_unlocked: bool = False
    premium_unlocked: bool = False
    always_available: bool = False

    @property
    def has_offers(self) -> bool:
        return self.regular_offer_exists or self.premium_offer_exists

    @property
    def unlocked(self) -> bool:
        return self.regular_unlocked or self.premium_unlocked


def _coerce_bytes(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _usage_percent(used: Any, limit: Any) -> int:
    limit_bytes = _coerce_bytes(limit)
    if limit_bytes <= 0:
        return 0
    percent = round(_coerce_bytes(used) / limit_bytes * 100)
    return max(0, min(100, percent))


def resolve_traffic_topup_availability(
    settings: Settings,
    active: dict[str, Any] | None,
) -> TrafficTopupAvailability:
    """Compute top-up availability from active-subscription details.

    ``active`` is the dict returned by
    ``SubscriptionService.get_active_subscription_details``.
    """
    config = settings.tariffs_config
    if not config or not active or not active.get("tariff_key"):
        return TrafficTopupAvailability()
    try:
        tariff = config.require(str(active["tariff_key"]))
        packages = config.topup_packages_for(tariff)
    except Exception:
        logger.debug(
            "Top-up availability: tariff %r is unknown or disabled",
            active.get("tariff_key"),
        )
        return TrafficTopupAvailability()

    regular_offer_exists = bool(packages and packages.has_any())
    premium_offer_exists = bool(
        tariff.premium_squad_uuids
        and tariff.premium_topup_packages
        and tariff.premium_topup_packages.has_any()
    )
    always_available = bool(tariff.topup_always_available)
    threshold_bypassed = always_available or tariff.billing_model == "traffic"

    regular_visible = not bool(active.get("regular_unlimited_override")) and (
        _coerce_bytes(active.get("traffic_limit_bytes")) > 0
    )
    regular_unlocked = bool(
        regular_offer_exists
        and regular_visible
        and (
            threshold_bypassed
            or _usage_percent(active.get("traffic_used_bytes"), active.get("traffic_limit_bytes"))
            >= TRAFFIC_TOPUP_UNLOCK_PERCENT
        )
    )

    premium_visible = not bool(active.get("premium_unlimited_override")) and (
        _coerce_bytes(active.get("premium_limit_bytes")) > 0
    )
    premium_unlocked = bool(
        premium_offer_exists
        and premium_visible
        and (
            threshold_bypassed
            or _usage_percent(active.get("premium_used_bytes"), active.get("premium_limit_bytes"))
            >= TRAFFIC_TOPUP_UNLOCK_PERCENT
        )
    )

    return TrafficTopupAvailability(
        regular_offer_exists=regular_offer_exists,
        premium_offer_exists=premium_offer_exists,
        regular_unlocked=regular_unlocked,
        premium_unlocked=premium_unlocked,
        always_available=always_available,
    )
