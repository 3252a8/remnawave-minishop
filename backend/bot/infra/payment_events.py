"""Helpers for payment-related domain event payloads.

The event bus intentionally carries plain dictionaries so plugins can subscribe
without importing ORM models. This module is the typed edge around those dicts:
publishers use it to build stable payloads, subscribers use it to resolve a
payment snapshot, and plugins may register extra purchase resolvers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, cast

from bot.infra.event_payloads import PaymentSucceededPayload

logger = logging.getLogger(__name__)

TRAFFIC_SALE_BASES = {"traffic", "traffic_package", "topup", "premium_topup"}
HWID_DEVICE_SALE_BASES = {"hwid_device", "hwid_devices", "hwid_devices_renewal"}


@dataclass(frozen=True)
class PaymentPurchase:
    """One purchased unit attached to a successful payment event."""

    kind: str
    amount: float
    unit: str
    scope: Optional[str] = None
    label_key: Optional[str] = None
    label_kwargs: Mapping[str, Any] = field(default_factory=dict)
    sort_order: int = 100


@dataclass(frozen=True)
class PaymentPurchaseContext:
    """Inputs available to purchase resolvers."""

    payload: Mapping[str, Any]
    payment: Any
    sale_mode: str
    sale_mode_base: str
    tariff_key: Optional[str]


@dataclass(frozen=True)
class PaymentSuccessSnapshot:
    """Normalized view of a ``PAYMENT_SUCCEEDED`` payload."""

    user_id: Optional[int]
    payment_db_id: Optional[int]
    amount: float
    currency: str
    provider: str
    notification_provider: str
    sale_mode: str
    sale_mode_base: str
    tariff_key: Optional[str]
    months: int
    traffic_gb: Optional[float]
    traffic_is_premium: bool
    purchased_hwid_devices: Optional[int]
    promo_code_id: Optional[int]
    base_amount: Optional[float]
    discount_amount: Optional[float]
    purchases: tuple[PaymentPurchase, ...]


PaymentPurchaseResolver = Callable[[PaymentPurchaseContext], Iterable[PaymentPurchase]]

_extra_purchase_resolvers: list[PaymentPurchaseResolver] = []


def sale_mode_base(sale_mode: Any) -> str:
    return str(sale_mode or "").split("@", 1)[0].split("|", 1)[0]


def sale_mode_tariff_key(sale_mode: Any) -> Optional[str]:
    if "@" not in str(sale_mode or ""):
        return None
    return str(sale_mode).split("@", 1)[1].split("|", 1)[0] or None


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _first_optional_float(*values: Any) -> Optional[float]:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    return None


def _optional_positive_int(value: Any) -> Optional[int]:
    number = _optional_float(value)
    if number is None or not number.is_integer():
        return None
    parsed = int(number)
    return parsed if parsed > 0 else None


def _optional_int(value: Any) -> Optional[int]:
    number = _optional_float(value)
    if number is None:
        return None
    return int(number)


def _getattr_or_none(source: Any, name: str) -> Any:
    return getattr(source, name, None) if source is not None else None


def _resolve_traffic_purchase(ctx: PaymentPurchaseContext) -> Iterable[PaymentPurchase]:
    amount = _optional_float(ctx.payload.get("traffic_gb"))
    payload_has_traffic = amount is not None
    if amount is None:
        amount = _optional_float(_getattr_or_none(ctx.payment, "purchased_gb"))
    if amount is None:
        return ()
    if not payload_has_traffic and ctx.sale_mode_base not in TRAFFIC_SALE_BASES:
        return ()
    scope = "premium" if ctx.sale_mode_base == "premium_topup" else "regular"
    return (
        PaymentPurchase(
            kind="traffic",
            amount=amount,
            unit="gb",
            scope=scope,
            sort_order=20,
        ),
    )


def _resolve_hwid_purchase(ctx: PaymentPurchaseContext) -> Iterable[PaymentPurchase]:
    amount = _optional_positive_int(ctx.payload.get("purchased_hwid_devices"))
    if amount is None:
        amount = _optional_positive_int(ctx.payload.get("hwid_devices"))
    if amount is None:
        amount = _optional_positive_int(_getattr_or_none(ctx.payment, "purchased_hwid_devices"))
    if amount is None:
        return ()
    return (
        PaymentPurchase(
            kind="hwid_devices",
            amount=float(amount),
            unit="device",
            sort_order=40,
        ),
    )


_CORE_PURCHASE_RESOLVERS: tuple[PaymentPurchaseResolver, ...] = (
    _resolve_traffic_purchase,
    _resolve_hwid_purchase,
)


def register_payment_purchase_resolver(resolver: PaymentPurchaseResolver) -> None:
    """Register a plugin purchase resolver for future payment event snapshots."""

    if not callable(resolver):
        raise TypeError("resolver must be callable")
    if resolver not in _extra_purchase_resolvers:
        _extra_purchase_resolvers.append(resolver)


def reset_payment_purchase_resolvers() -> None:
    """Remove plugin purchase resolvers while preserving core resolvers."""

    _extra_purchase_resolvers.clear()


def iter_payment_purchase_resolvers() -> tuple[PaymentPurchaseResolver, ...]:
    return (*_CORE_PURCHASE_RESOLVERS, *_extra_purchase_resolvers)


def resolve_payment_purchases(
    payload: Mapping[str, Any],
    payment: Any = None,
) -> tuple[PaymentPurchase, ...]:
    sale_mode = str(payload.get("sale_mode") or _getattr_or_none(payment, "sale_mode") or "")
    base = sale_mode_base(sale_mode)
    tariff_key = (
        payload.get("tariff_key")
        or _getattr_or_none(payment, "tariff_key")
        or sale_mode_tariff_key(sale_mode)
    )
    ctx = PaymentPurchaseContext(
        payload=payload,
        payment=payment,
        sale_mode=sale_mode,
        sale_mode_base=base,
        tariff_key=str(tariff_key) if tariff_key else None,
    )
    purchases: list[PaymentPurchase] = []
    for resolver in iter_payment_purchase_resolvers():
        try:
            purchases.extend(resolver(ctx) or ())
        except Exception:
            logger.exception(
                "Payment purchase resolver %r failed; skipping it",
                getattr(resolver, "__qualname__", resolver),
            )
    return tuple(sorted(purchases, key=lambda item: (item.sort_order, item.kind, item.unit)))


def payment_purchases_from_legacy_fields(
    *,
    traffic_gb: Optional[float] = None,
    traffic_is_premium: bool = False,
    purchased_hwid_devices: Optional[int] = None,
) -> tuple[PaymentPurchase, ...]:
    sale_mode = "premium_topup" if traffic_is_premium else "topup"
    payload = {
        "sale_mode": sale_mode,
        "traffic_gb": traffic_gb,
        "purchased_hwid_devices": purchased_hwid_devices,
    }
    return resolve_payment_purchases(payload)


def resolve_payment_success_snapshot(
    payload: Mapping[str, Any],
    payment: Any = None,
    *,
    default_currency: str = "RUB",
) -> PaymentSuccessSnapshot:
    sale_mode = str(payload.get("sale_mode") or _getattr_or_none(payment, "sale_mode") or "")
    base = sale_mode_base(sale_mode)
    tariff_key = (
        payload.get("tariff_key")
        or _getattr_or_none(payment, "tariff_key")
        or sale_mode_tariff_key(sale_mode)
    )
    purchases = resolve_payment_purchases(
        {**dict(payload), "sale_mode": sale_mode, "tariff_key": tariff_key},
        payment,
    )
    traffic_purchase = next((item for item in purchases if item.kind == "traffic"), None)
    hwid_purchase = next((item for item in purchases if item.kind == "hwid_devices"), None)
    months = 0
    if base == "subscription":
        months = int(
            _optional_int(payload.get("months"))
            or _optional_int(_getattr_or_none(payment, "subscription_duration_months"))
            or 0
        )
    amount = _optional_float(payload.get("amount"))
    if amount is None:
        amount = _optional_float(_getattr_or_none(payment, "amount")) or 0.0
    currency = str(
        payload.get("currency") or _getattr_or_none(payment, "currency") or default_currency
    )
    provider = str(payload.get("provider") or _getattr_or_none(payment, "provider") or "")
    notification_provider = str(payload.get("notification_provider") or provider)
    return PaymentSuccessSnapshot(
        user_id=_optional_int(payload.get("user_id")),
        payment_db_id=_optional_int(payload.get("payment_db_id")),
        amount=float(amount),
        currency=currency,
        provider=provider,
        notification_provider=notification_provider,
        sale_mode=sale_mode,
        sale_mode_base=base,
        tariff_key=str(tariff_key) if tariff_key else None,
        months=months,
        traffic_gb=traffic_purchase.amount if traffic_purchase else None,
        traffic_is_premium=bool(
            base == "premium_topup"
            or (traffic_purchase is not None and traffic_purchase.scope == "premium")
        ),
        purchased_hwid_devices=int(hwid_purchase.amount) if hwid_purchase else None,
        promo_code_id=_optional_int(
            payload.get("promo_code_id") or _getattr_or_none(payment, "promo_code_id")
        ),
        base_amount=_first_optional_float(
            payload.get("base_amount"),
            _getattr_or_none(payment, "checkout_base_amount"),
        ),
        discount_amount=_first_optional_float(
            payload.get("discount_amount"),
            _getattr_or_none(payment, "checkout_discount_amount"),
        ),
        purchases=purchases,
    )


def build_payment_succeeded_payload(
    *,
    user_id: int,
    payment_db_id: int,
    provider: str,
    notification_provider: str,
    amount: float,
    currency: str,
    sale_mode: str,
    tariff_key: Optional[str],
    months: Optional[int],
    traffic_gb: Optional[float],
    end_date: Optional[str],
    is_auto_renew: bool,
    payment: Any = None,
    activation: Optional[Mapping[str, Any]] = None,
    purchased_hwid_devices: Optional[int] = None,
    promo_code_id: Optional[int] = None,
    base_amount: Optional[float] = None,
    discount_amount: Optional[float] = None,
) -> dict[str, Any]:
    activation = activation or {}
    payload: dict[str, Any] = {
        "user_id": user_id,
        "payment_db_id": payment_db_id,
        "provider": provider,
        "notification_provider": notification_provider,
        "amount": amount,
        "currency": currency,
        "sale_mode": sale_mode,
        "tariff_key": tariff_key,
        "months": months,
        "traffic_gb": traffic_gb,
        "purchased_hwid_devices": (
            purchased_hwid_devices
            or activation.get("purchased_hwid_devices")
            or activation.get("hwid_devices_renewed_count")
        ),
        "promo_code_id": promo_code_id or _getattr_or_none(payment, "promo_code_id"),
        "base_amount": base_amount,
        "discount_amount": discount_amount,
        "end_date": end_date,
        "is_auto_renew": is_auto_renew,
    }
    snapshot = resolve_payment_success_snapshot(payload, payment)
    payload["traffic_gb"] = snapshot.traffic_gb
    payload["purchased_hwid_devices"] = snapshot.purchased_hwid_devices
    payload["promo_code_id"] = snapshot.promo_code_id
    payload["base_amount"] = snapshot.base_amount
    payload["discount_amount"] = snapshot.discount_amount
    return cast(dict[str, Any], PaymentSucceededPayload(**payload).to_payload())
