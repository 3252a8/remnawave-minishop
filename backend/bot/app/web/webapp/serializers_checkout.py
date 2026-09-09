from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import tariff_dal

from .billing_checkout_bundle import (
    CheckoutPricingContext,
    checkout_pricing_windows_from_records,
    price_checkout_addon_definitions,
)
from .billing_common import _subscription_is_trial


async def attach_checkout_pricing_context_to_plans(
    session: AsyncSession,
    settings: Settings,
    *,
    local_sub: Any | None,
    plans: list[dict[str, Any]],
) -> None:
    if local_sub is None or not settings.tariffs_config:
        return
    if _subscription_is_trial(local_sub):
        for plan in plans:
            if str(plan.get("sale_mode") or "subscription") != "subscription":
                continue
            plan.pop("tariff_switch_required", None)
        return
    try:
        active_tariff = settings.tariffs_config.require_configured(local_sub.tariff_key)
    except Exception:
        active_tariff = None
    pricing_now = datetime.now(UTC)
    flexible_records = (
        await tariff_dal.get_active_flexible_traffic_limit_records(
            session,
            subscription_id=int(local_sub.subscription_id),
            at=pricing_now,
        )
        if active_tariff is not None
        else {}
    )
    flexible_window_records = (
        await tariff_dal.list_flexible_traffic_limit_records_in_window(
            session,
            subscription_id=int(local_sub.subscription_id),
            valid_from=pricing_now,
            valid_until=local_sub.end_date,
        )
        if active_tariff is not None
        else []
    )
    hwid_summary = (
        await tariff_dal.get_hwid_device_entitlement_summary(
            session,
            subscription_id=int(local_sub.subscription_id),
            at=pricing_now,
            include_future=True,
        )
        if active_tariff is not None
        else {}
    )
    next_hwid_window = hwid_summary.get("next_valid_from")
    if next_hwid_window is not None and next_hwid_window.tzinfo is None:
        next_hwid_window = next_hwid_window.replace(tzinfo=UTC)
    local_end_at = local_sub.end_date
    if local_end_at.tzinfo is None:
        local_end_at = local_end_at.replace(tzinfo=UTC)
    has_future_hwid_window = bool(next_hwid_window is not None and next_hwid_window < local_end_at)
    for plan in plans:
        if str(plan.get("sale_mode") or "subscription") != "subscription":
            continue
        target_key = str(plan.get("tariff_key") or "").strip()
        if active_tariff is None or target_key != active_tariff.key:
            plan["checkout_addons"] = {}
            plan["tariff_switch_required"] = True
            continue
        definitions = plan.get("checkout_addons")
        if not isinstance(definitions, dict) or not definitions:
            continue
        definitions = dict(definitions)
        if has_future_hwid_window:
            definitions.pop("devices", None)
        if not definitions:
            plan["checkout_addons"] = {}
            continue
        current_regular_limit_gb = float(
            local_sub.tier_baseline_bytes or active_tariff.monthly_bytes or 0
        ) / (1024**3)
        current_premium_limit_gb = float(
            local_sub.premium_baseline_bytes or active_tariff.premium_monthly_bytes or 0
        ) / (1024**3)
        current_regular_monthly_price = float(
            getattr(flexible_records.get("traffic"), "monthly_amount", 0) or 0
        )
        current_premium_monthly_price = float(
            getattr(flexible_records.get("premium_traffic"), "monthly_amount", 0) or 0
        )
        current_regular_monthly_stars = int(
            getattr(flexible_records.get("traffic"), "monthly_stars_amount", 0) or 0
        )
        current_premium_monthly_stars = int(
            getattr(
                flexible_records.get("premium_traffic"),
                "monthly_stars_amount",
                0,
            )
            or 0
        )
        context = CheckoutPricingContext(
            active_subscription_id=int(local_sub.subscription_id),
            active_tariff_key=active_tariff.key,
            active_end_at=local_sub.end_date,
            current_device_count=max(0, int(local_sub.extra_hwid_devices or 0)),
            current_regular_limit_gb=current_regular_limit_gb,
            current_premium_limit_gb=current_premium_limit_gb,
            current_regular_monthly_price=current_regular_monthly_price,
            current_premium_monthly_price=current_premium_monthly_price,
            current_regular_monthly_stars=current_regular_monthly_stars,
            current_premium_monthly_stars=current_premium_monthly_stars,
            regular_windows=checkout_pricing_windows_from_records(
                flexible_window_records,
                kind="traffic",
                start_at=pricing_now,
                end_at=local_sub.end_date,
                fallback_units=current_regular_limit_gb,
                fallback_monthly_price=current_regular_monthly_price,
                fallback_monthly_stars=current_regular_monthly_stars,
            ),
            premium_windows=checkout_pricing_windows_from_records(
                flexible_window_records,
                kind="premium_traffic",
                start_at=pricing_now,
                end_at=local_sub.end_date,
                fallback_units=current_premium_limit_gb,
                fallback_monthly_price=current_premium_monthly_price,
                fallback_monthly_stars=current_premium_monthly_stars,
            ),
        )
        priced = price_checkout_addon_definitions(definitions, context)
        requested_initials = {
            "devices": float(context.current_device_count),
            "traffic": float(context.current_regular_limit_gb or 0),
            "premium_traffic": float(context.current_premium_limit_gb or 0),
        }
        for kind, definition in priced.items():
            candidates = sorted(
                float(option.get("extra_units") if kind == "devices" else option.get("total_units"))
                for option in list(definition.get("options") or [])
            )
            requested = requested_initials.get(kind, 0.0)
            initial = next((value for value in candidates if value >= requested), None)
            if initial is None and candidates:
                initial = candidates[-1]
            if initial is not None:
                definition["initial_units"] = initial
        plan["checkout_addons"] = priced
