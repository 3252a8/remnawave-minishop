"""Payment purchase display data shared by account and administration APIs."""

from __future__ import annotations

from typing import Any

from bot.app.web.http_contracts import HttpResponseModel
from bot.infra.payment_events import resolve_payment_purchases
from bot.services.checkout_addons import checkout_addon_grants


class PaymentPurchaseOut(HttpResponseModel):
    kind: str
    amount: float
    unit: str
    scope: str | None = None
    mode: str = "topup"


def payment_purchases(payment: Any) -> list[PaymentPurchaseOut]:
    purchases: list[PaymentPurchaseOut] = []
    seen: set[tuple[str, str | None]] = set()

    def append(
        *,
        kind: str,
        amount: float,
        unit: str,
        scope: str | None = None,
        mode: str = "topup",
    ) -> None:
        key = (kind, scope)
        if key in seen:
            return
        seen.add(key)
        purchases.append(
            PaymentPurchaseOut(
                kind=kind,
                amount=float(amount),
                unit=unit,
                scope=scope,
                mode=mode,
            )
        )

    checkout_grants = checkout_addon_grants(getattr(payment, "checkout_bundle_snapshot", None))
    if checkout_grants.regular_limit_gb is not None:
        append(
            kind="traffic",
            amount=checkout_grants.regular_limit_gb,
            unit="gb",
            scope="regular",
            mode="limit",
        )
    if checkout_grants.premium_limit_gb is not None:
        append(
            kind="traffic",
            amount=checkout_grants.premium_limit_gb,
            unit="gb",
            scope="premium",
            mode="limit",
        )
    if checkout_grants.legacy_regular_topup_gb > 0:
        append(
            kind="traffic",
            amount=checkout_grants.legacy_regular_topup_gb,
            unit="gb",
            scope="regular",
        )
    if checkout_grants.legacy_premium_topup_gb > 0:
        append(
            kind="traffic",
            amount=checkout_grants.legacy_premium_topup_gb,
            unit="gb",
            scope="premium",
        )
    if checkout_grants.device_count > 0:
        sale_mode = str(getattr(payment, "sale_mode", "") or "").split("@", 1)[0].lower()
        append(
            kind="hwid_devices",
            amount=float(checkout_grants.device_count),
            unit="device",
            mode="limit" if sale_mode == "subscription" else "topup",
        )

    for purchase in resolve_payment_purchases({}, payment):
        if purchase.amount <= 0:
            continue
        append(
            kind=purchase.kind,
            amount=purchase.amount,
            unit=purchase.unit,
            scope=purchase.scope,
        )
    return purchases


def traffic_gb_split(payment: Any) -> tuple[float | None, float | None]:
    if payment.purchased_gb is None:
        return None, None
    try:
        gb = float(payment.purchased_gb)
    except (TypeError, ValueError):
        return None, None
    sale_mode = (payment.sale_mode or "").strip()
    if not sale_mode:
        return None, None
    base = sale_mode.split("@", 1)[0].split("|", 1)[0].lower()
    if base == "premium_topup":
        return None, gb
    if base in {"traffic", "traffic_package", "topup"}:
        return gb, None
    return None, None
