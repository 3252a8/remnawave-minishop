from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise
from typing import Any

from config.tariff_checkout import serialize_checkout_addons
from config.tariffs_config import default_currency_key_for_settings

from .billing_sale_modes import _sale_mode_base, _sale_mode_tariff_key


class CheckoutBundleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CheckoutBundle:
    snapshot: str | None = None
    digest: str | None = None
    addon_amount: float = 0.0
    addon_stars: int = 0
    items: tuple[dict[str, Any], ...] = ()

    @property
    def has_addons(self) -> bool:
        return bool(self.items)


@dataclass(frozen=True)
class CheckoutPricingWindow:
    current_units: float
    month_fraction: float
    monthly_price: float = 0.0
    monthly_stars: int = 0


@dataclass(frozen=True)
class CheckoutPricingContext:
    active_subscription_id: int | None = None
    active_tariff_key: str | None = None
    active_end_at: datetime | None = None
    current_device_count: int = 0
    current_regular_limit_gb: float | None = None
    current_premium_limit_gb: float | None = None
    current_regular_monthly_price: float = 0.0
    current_premium_monthly_price: float = 0.0
    current_regular_monthly_stars: int = 0
    current_premium_monthly_stars: int = 0
    regular_windows: tuple[CheckoutPricingWindow, ...] = ()
    premium_windows: tuple[CheckoutPricingWindow, ...] = ()
    complimentary_remaining_period: bool = False

    @property
    def remaining_month_fraction(self) -> float:
        if self.active_end_at is None:
            return 0.0
        end_at = self.active_end_at
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=UTC)
        seconds = max(0.0, (end_at - datetime.now(UTC)).total_seconds())
        return seconds / (30 * 24 * 60 * 60)


def _same_units(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-9)


def _selected_units(payload: Any, kind: str) -> float | None:
    addons = getattr(payload, "checkout_addons", None)
    if addons is None:
        return None
    field = {
        "devices": "device_count",
        "traffic": "regular_limit_gb",
        "premium_traffic": "premium_limit_gb",
    }[kind]
    raw_value = getattr(addons, field, None)
    if raw_value is None:
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise CheckoutBundleError("invalid_checkout_addon", "Invalid checkout add-on") from exc
    if not math.isfinite(value) or value < 0:
        raise CheckoutBundleError("invalid_checkout_addon", "Invalid checkout add-on")
    if kind == "devices" and not value.is_integer():
        raise CheckoutBundleError("invalid_checkout_addon", "Invalid device add-on")
    return value


def normalize_checkout_device_selection(payment_payload: Any) -> Any:
    """Prefer the unified device add-on when a legacy renewal flag is also present."""

    if not bool(getattr(payment_payload, "renew_hwid_devices", False)):
        return payment_payload
    if (_selected_units(payment_payload, "devices") or 0) <= 0:
        return payment_payload
    return payment_payload.model_copy(update={"renew_hwid_devices": False})


def _option_for_units(options: list[dict[str, Any]], units: float) -> dict[str, Any] | None:
    return next(
        (option for option in options if _same_units(float(option.get("total_units") or 0), units)),
        None,
    )


def _money(value: float) -> float:
    return float(Decimal(str(max(0.0, value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def checkout_pricing_windows_from_records(
    records: list[Any],
    *,
    kind: str,
    start_at: datetime,
    end_at: datetime,
    fallback_units: float,
    fallback_monthly_price: float = 0.0,
    fallback_monthly_stars: int = 0,
) -> tuple[CheckoutPricingWindow, ...]:
    """Build max-entitlement pricing segments for repeated early renewals."""

    start = _aware_utc(start_at)
    end = _aware_utc(end_at)
    if end <= start:
        return ()
    matching = [record for record in records if str(getattr(record, "kind", "")) == kind]
    boundaries = {start, end}
    for record in matching:
        valid_from = _aware_utc(record.valid_from)
        valid_until = _aware_utc(record.valid_until)
        if valid_from < end and valid_until > start:
            boundaries.add(max(start, valid_from))
            boundaries.add(min(end, valid_until))
    points = sorted(boundaries)
    windows: list[CheckoutPricingWindow] = []
    for left, right in pairwise(points):
        if right <= left:
            continue
        active = [
            record
            for record in matching
            if _aware_utc(record.valid_from) <= left < _aware_utc(record.valid_until)
        ]
        selected = max(
            active,
            key=lambda record: (
                int(getattr(record, "limit_bytes", 0) or 0),
                _aware_utc(getattr(record, "created_at", left) or left),
            ),
            default=None,
        )
        current_units = fallback_units
        monthly_price = fallback_monthly_price
        monthly_stars = fallback_monthly_stars
        if selected is not None:
            current_units = float(selected.limit_bytes or 0) / (1024**3)
            monthly_price = float(selected.monthly_amount or 0)
            monthly_stars = int(selected.monthly_stars_amount or 0)
        fraction = (right - left).total_seconds() / (30 * 24 * 60 * 60)
        if fraction <= 0:
            continue
        window = CheckoutPricingWindow(
            current_units=max(0.0, current_units),
            month_fraction=fraction,
            monthly_price=max(0.0, monthly_price),
            monthly_stars=max(0, monthly_stars),
        )
        if windows and (
            _same_units(windows[-1].current_units, window.current_units)
            and _same_units(windows[-1].monthly_price, window.monthly_price)
            and windows[-1].monthly_stars == window.monthly_stars
        ):
            previous = windows.pop()
            window = replace(
                previous,
                month_fraction=previous.month_fraction + window.month_fraction,
            )
        windows.append(window)
    return tuple(windows)


def _current_total(context: CheckoutPricingContext | None, kind: str, base: float) -> float:
    if context is None:
        return base
    if kind == "devices":
        return base + max(0, int(context.current_device_count or 0))
    value = (
        context.current_regular_limit_gb if kind == "traffic" else context.current_premium_limit_gb
    )
    return max(base, float(value)) if value is not None else base


def _priced_option(
    addon: dict[str, Any],
    option: dict[str, Any],
    *,
    kind: str,
    context: CheckoutPricingContext | None,
) -> tuple[float, int, float, int, bool]:
    full_price = float(option.get("price") or 0)
    full_stars = int(option.get("stars_price") or 0)
    if context is None or context.remaining_month_fraction <= 0:
        return full_price, full_stars, 0.0, 0, False

    if context.complimentary_remaining_period:
        base = float(addon.get("base_units") or 0)
        selected_total = float(option.get("total_units") or 0)
        return (
            full_price,
            full_stars,
            0.0,
            0,
            selected_total > base + 1e-9,
        )

    options = list(addon.get("options") or [])
    base = float(addon.get("base_units") or 0)
    current_total = _current_total(context, kind, base)
    current = _option_for_units(options, current_total)
    context_monthly = 0.0
    context_monthly_stars = 0
    if kind == "traffic":
        context_monthly = context.current_regular_monthly_price
        context_monthly_stars = context.current_regular_monthly_stars
    elif kind == "premium_traffic":
        context_monthly = context.current_premium_monthly_price
        context_monthly_stars = context.current_premium_monthly_stars
    current_monthly = float((current or {}).get("monthly_price") or context_monthly or 0)
    selected_monthly = float(option.get("monthly_price") or 0)
    current_monthly_stars = int(
        (current or {}).get("monthly_stars_price") or context_monthly_stars or 0
    )
    selected_monthly_stars = int(option.get("monthly_stars_price") or 0)
    selected_total = float(option.get("total_units") or 0)
    windows = (
        context.regular_windows
        if kind == "traffic"
        else context.premium_windows
        if kind == "premium_traffic"
        else ()
    )
    if windows:
        applicable = [window for window in windows if selected_total > window.current_units + 1e-9]
        immediate_price = _money(
            sum(
                max(0.0, selected_monthly - window.monthly_price) * window.month_fraction
                for window in applicable
            )
        )
        immediate_stars = math.ceil(
            sum(
                max(0, selected_monthly_stars - window.monthly_stars) * window.month_fraction
                for window in applicable
            )
        )
        return (
            full_price + immediate_price,
            full_stars + immediate_stars,
            immediate_price,
            immediate_stars,
            bool(applicable),
        )
    immediate_price = _money(
        max(0.0, selected_monthly - current_monthly) * context.remaining_month_fraction
    )
    immediate_stars = math.ceil(
        max(0, selected_monthly_stars - current_monthly_stars) * context.remaining_month_fraction
    )
    return (
        full_price + immediate_price,
        full_stars + immediate_stars,
        immediate_price,
        immediate_stars,
        selected_total > current_total + 1e-9,
    )


def price_checkout_addon_definitions(
    definitions: dict[str, dict[str, Any]],
    context: CheckoutPricingContext,
) -> dict[str, dict[str, Any]]:
    """Attach the same active-subscription uplift used by the quote endpoint."""

    priced: dict[str, dict[str, Any]] = {}
    for kind, definition in definitions.items():
        next_definition = dict(definition)
        next_options: list[dict[str, Any]] = []
        for raw_option in list(definition.get("options") or []):
            option = dict(raw_option)
            (
                price,
                stars_price,
                immediate_price,
                immediate_stars,
                immediate_applies,
            ) = _priced_option(definition, option, kind=kind, context=context)
            option.update(
                {
                    "price": price,
                    "stars_price": stars_price,
                    "immediate_amount": immediate_price,
                    "immediate_stars_amount": immediate_stars,
                    "immediate_applies": immediate_applies,
                }
            )
            next_options.append(option)
        next_definition["options"] = next_options
        priced[kind] = next_definition
    return priced


def build_checkout_bundle(
    base_quote: Any,
    *,
    settings: Any,
    payment_payload: Any,
    method: str,
    pricing_context: CheckoutPricingContext | None = None,
) -> tuple[Any, CheckoutBundle]:
    if _sale_mode_base(base_quote.sale_mode) != "subscription":
        if any(
            (_selected_units(payment_payload, kind) or 0) > 0
            for kind in ("devices", "traffic", "premium_traffic")
        ):
            raise CheckoutBundleError(
                "checkout_addons_unavailable",
                "Checkout add-ons are available only for period subscriptions",
            )
        return base_quote, CheckoutBundle()
    tariff_key = _sale_mode_tariff_key(base_quote.sale_mode)
    tariffs_config = settings.tariffs_config
    if not tariff_key or tariffs_config is None:
        if any(
            (_selected_units(payment_payload, kind) or 0) > 0
            for kind in ("devices", "traffic", "premium_traffic")
        ):
            raise CheckoutBundleError(
                "checkout_addons_unavailable",
                "Checkout add-ons are not available for this subscription",
            )
        return base_quote, CheckoutBundle()
    tariff = tariffs_config.require(tariff_key)
    options = serialize_checkout_addons(
        tariff,
        default_currency=default_currency_key_for_settings(settings),
        months=int(base_quote.payment_units),
        fallback_hwid_limit=settings.USER_HWID_DEVICE_LIMIT,
        devices_feature_enabled=bool(settings.MY_DEVICES_SECTION_ENABLED),
    )
    items: list[dict[str, Any]] = []
    addon_amount = 0.0
    addon_stars = 0
    for kind in ("devices", "traffic", "premium_traffic"):
        units = _selected_units(payment_payload, kind)
        if units is None:
            continue
        addon = options.get(kind)
        # Web clients keep a stable checkout payload shape and may send zero
        # for an add-on that the selected tariff does not expose. Zero means
        # that no extra entitlement was selected; only a positive stale value
        # should fail availability validation.
        if addon is None and _same_units(units, 0):
            continue
        if kind == "devices" and addon is not None:
            units = float(addon.get("base_units") or 0) + units
        option = _option_for_units(list(addon.get("options") or []), units) if addon else None
        if option is None:
            raise CheckoutBundleError(
                "checkout_addon_unavailable",
                "The selected checkout add-on is no longer available",
            )
        base_units = float(addon.get("base_units") or 0)
        extra_units = float(option.get("extra_units") or 0)
        # A base selection on a new/base subscription is not an add-on. Keeping it
        # out of the snapshot lets payment methods without bundle support continue
        # to sell the plain tariff. A base traffic choice on an already upgraded
        # subscription is different: it is an intentional downgrade for the next
        # paid window and must be frozen in the payment snapshot.
        if extra_units <= 0:
            if kind == "devices":
                continue
            if _current_total(pricing_context, kind, base_units) <= base_units:
                continue
        price, stars_price, immediate_price, immediate_stars, immediate_applies = _priced_option(
            addon,
            option,
            kind=kind,
            context=pricing_context,
        )
        if (
            method == "stars"
            and stars_price <= 0
            and float(option.get("total_units") or 0) > float(addon.get("base_units") or 0)
        ):
            raise CheckoutBundleError(
                "checkout_addon_price_unavailable",
                "Stars price is not configured for the selected add-on",
            )
        item = {
            "kind": kind,
            "base_units": addon.get("base_units"),
            "extra_units": option.get("extra_units"),
            "total_units": option.get("total_units"),
            "amount": price,
            "stars_amount": stars_price,
            "future_amount": float(option.get("price") or 0),
            "future_stars_amount": int(option.get("stars_price") or 0),
            "immediate_amount": immediate_price,
            "immediate_stars_amount": immediate_stars,
            "immediate_applies": immediate_applies,
        }
        if kind == "devices":
            item["traffic_bonus_gb"] = float(option.get("traffic_bonus_gb") or 0)
        items.append(item)
        addon_amount += price
        addon_stars += stars_price

    if not items:
        return base_quote, CheckoutBundle()
    if bool(getattr(payment_payload, "renew_hwid_devices", False)) and any(
        item["kind"] == "devices" for item in items
    ):
        raise CheckoutBundleError(
            "duplicate_device_addon",
            "Device renewal and a device checkout add-on cannot be combined",
        )

    base_amount = float(base_quote.price or 0)
    base_stars = int(base_quote.stars_price or 0)
    snapshot_data = {
        "version": 3,
        "tariff_key": tariff.key,
        "months": int(base_quote.payment_units),
        "duration_days": tariff.period_duration_days(int(base_quote.payment_units)),
        "addon_period_factor": tariff.addon_period_factor(int(base_quote.payment_units)),
        "currency": "XTR" if method == "stars" else base_quote.default_currency_code,
        "base_subscription_amount": base_amount,
        "base_subscription_stars": base_stars,
        "addons_amount": round(addon_amount, 8),
        "addons_stars": addon_stars,
        "items": items,
        "active_context": {
            "subscription_id": pricing_context.active_subscription_id,
            "tariff_key": pricing_context.active_tariff_key,
            "end_at": (
                pricing_context.active_end_at.isoformat()
                if pricing_context and pricing_context.active_end_at
                else None
            ),
        }
        if pricing_context
        else None,
    }
    snapshot = json.dumps(snapshot_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    return (
        replace(
            base_quote,
            price=base_amount + addon_amount,
            stars_price=(base_stars + addon_stars if method == "stars" else base_quote.stars_price),
        ),
        CheckoutBundle(
            snapshot=snapshot,
            digest=digest,
            addon_amount=addon_amount,
            addon_stars=addon_stars,
            items=tuple(items),
        ),
    )
