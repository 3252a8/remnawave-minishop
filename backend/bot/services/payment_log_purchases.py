"""Render payment log contents from the immutable checkout, without changing events."""

import math
from collections.abc import Callable
from html import escape
from typing import Any

from bot.infra.payment_events import PaymentPurchase
from bot.services.checkout_addons import parse_checkout_bundle_snapshot


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def format_payment_purchase_line(
    translate: Callable[..., str],
    purchase: PaymentPurchase,
    format_amount: Callable[[float], str],
) -> str:
    if purchase.kind == "traffic":
        traffic_kind = translate(
            "log_payment_traffic_kind_premium"
            if purchase.scope == "premium"
            else "log_payment_traffic_kind_regular"
        )
        return translate(
            "log_payment_traffic_purchase_line",
            gb=format_amount(float(purchase.amount)),
            kind=traffic_kind,
        )
    if purchase.kind == "hwid_devices":
        return translate("log_payment_hwid_devices_purchase_line", count=int(purchase.amount))
    label_kwargs = {
        "amount": format_amount(float(purchase.amount)),
        "unit": purchase.unit,
        "kind": purchase.kind,
        "scope": purchase.scope or "",
        **dict(purchase.label_kwargs),
    }
    return translate(purchase.label_key or "log_payment_generic_purchase_line", **label_kwargs)


def format_payment_purchase_summary(
    translate: Callable[..., str],
    purchases: tuple[PaymentPurchase, ...],
    *,
    checkout_bundle_snapshot: str | None,
    currency: str,
    format_amount: Callable[[float], str],
) -> str:
    snapshot = parse_checkout_bundle_snapshot(checkout_bundle_snapshot) or {}
    lines: list[str] = []
    covered: set[tuple[str, str | None]] = set()
    checkout_currency = str(snapshot.get("currency") or currency)
    price_field = "stars_amount" if checkout_currency == "XTR" else "amount"
    for item in snapshot.get("items", []):
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if not isinstance(kind, str):
            continue
        scope = "premium" if kind == "premium_traffic" else "regular"
        key = ("hwid_devices", None) if kind == "devices" else ("traffic", scope)
        if key in covered:
            continue
        if kind == "devices":
            units = _number(item.get("extra_units"))
            if units is None or units <= 0 or not units.is_integer():
                continue
            line = translate("log_payment_hwid_devices_purchase_line", count=int(units))
            total = _number(item.get("total_units"))
            if total is not None and total.is_integer():
                line += translate("log_payment_devices_total", count=int(total))
        elif kind in {"traffic", "premium_traffic"}:
            is_limit = snapshot.get("version", 1) >= 2
            units = _number(item.get("total_units" if is_limit else "extra_units"))
            if units is None or (not is_limit and units <= 0):
                continue
            line = translate(
                (
                    "log_payment_traffic_limit_unlimited_line"
                    if units == 0
                    else "log_payment_traffic_limit_purchase_line"
                )
                if is_limit
                else "log_payment_traffic_purchase_line",
                gb=format_amount(units),
                kind=translate(f"log_payment_traffic_kind_{scope}"),
            )
        else:
            continue
        covered.add(key)
        price = _number(item.get(price_field))
        if price is not None:
            line += translate(
                "log_payment_item_price",
                amount=format_amount(price),
                currency=escape(checkout_currency),
            )
        lines.append(line)
        included_traffic = _number(item.get("traffic_bonus_gb"))
        if kind == "devices" and included_traffic is not None and included_traffic > 0:
            lines.append(
                translate("log_payment_devices_traffic_line", gb=format_amount(included_traffic))
            )
    base_price = _number(
        snapshot.get(
            "base_subscription_stars" if checkout_currency == "XTR" else "base_subscription_amount"
        )
    )
    if lines and base_price is not None:
        lines.insert(
            0,
            translate(
                "log_payment_base_subscription_line",
                amount=format_amount(base_price),
                currency=escape(checkout_currency),
            ),
        )
    lines.extend(
        format_payment_purchase_line(translate, purchase, format_amount)
        for purchase in purchases
        if (purchase.kind, purchase.scope) not in covered
    )
    return "\n".join(line for line in lines if line)
