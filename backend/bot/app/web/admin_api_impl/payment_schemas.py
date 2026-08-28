"""Typed admin API contracts for payments."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from pydantic import ConfigDict, Field, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.infra.payment_events import resolve_payment_purchases
from bot.services.checkout_addons import checkout_addon_grants

from .schema_helpers import float_or_none as _float_or_none
from .schema_helpers import payment_user_display_label as _payment_user_display_label
from .schema_helpers import traffic_gb_split as _traffic_gb_split


class AdminPaymentFinalizeBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
    confirm_promo_conflict: bool = False

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("reason must contain at least 3 non-whitespace characters")
        return normalized


class AdminPaymentReverseBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
    restore_promo_usage: bool = True

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("reason must contain at least 3 non-whitespace characters")
        return normalized


class PaymentPurchaseOut(HttpResponseModel):
    kind: str
    amount: float
    unit: str
    scope: str | None = None
    mode: str = "topup"


def _payment_purchases(payment: Any) -> list[PaymentPurchaseOut]:
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


class PaymentOut(HttpResponseModel):
    payment_id: int
    user_id: int
    user_label: str
    telegram_id: int | None = None
    traffic_regular_gb: float | None = None
    traffic_premium_gb: float | None = None
    provider: str | None = None
    funding_source: str = "external"
    provider_payment_id: str | None = None
    provider_payment_url: str | None = None
    amount: float
    currency: str | None = None
    status: str | None = None
    description: str | None = None
    subscription_duration_months: int | None = None
    sale_mode: str | None = None
    tariff_key: str | None = None
    purchased_gb: Any = None
    purchased_hwid_devices: int | None = None
    purchases: list[PaymentPurchaseOut] = Field(default_factory=list)
    promo_code_id: int | None = None
    promo_discount_percent: float | None = None
    checkout_discount_amount: float | None = None
    fulfillment_source: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_orm_payment(cls, payment: Any) -> PaymentOut:
        telegram_id = None
        loaded_user = payment.__dict__.get("user")
        user_label = _payment_user_display_label(loaded_user, int(payment.user_id))
        if loaded_user is not None:
            raw_telegram_id = getattr(loaded_user, "telegram_id", None)
            if raw_telegram_id is not None:
                try:
                    telegram_id = int(raw_telegram_id)
                except (TypeError, ValueError):
                    telegram_id = None
        regular_gb, premium_gb = _traffic_gb_split(payment)
        return cls(
            payment_id=int(payment.payment_id),
            user_id=int(payment.user_id),
            user_label=user_label,
            telegram_id=telegram_id,
            traffic_regular_gb=regular_gb,
            traffic_premium_gb=premium_gb,
            provider=payment.provider,
            funding_source=str(getattr(payment, "funding_source", "external") or "external"),
            provider_payment_id=payment.provider_payment_id,
            provider_payment_url=getattr(payment, "provider_payment_url", None),
            amount=float(payment.amount),
            currency=payment.currency,
            status=payment.status,
            description=payment.description,
            subscription_duration_months=payment.subscription_duration_months,
            sale_mode=payment.sale_mode,
            tariff_key=payment.tariff_key,
            purchased_gb=payment.purchased_gb,
            purchased_hwid_devices=payment.purchased_hwid_devices,
            purchases=_payment_purchases(payment),
            promo_code_id=(
                int(payment.promo_code_id) if getattr(payment, "promo_code_id", None) else None
            ),
            promo_discount_percent=_float_or_none(getattr(payment, "promo_discount_percent", None)),
            checkout_discount_amount=_float_or_none(
                getattr(payment, "checkout_discount_amount", None)
            ),
            fulfillment_source=(str(getattr(payment, "fulfillment_source", "") or "") or None),
            created_at=payment.created_at,
        )


class PaymentDetailOut(PaymentOut):
    yookassa_payment_id: str | None = None
    idempotence_key: str | None = None
    promo_code: str | None = None
    checkout_base_amount: float | None = None
    fulfilled_at: datetime | None = None
    fulfilled_by_admin_id: int | None = None
    fulfillment_note: str | None = None
    promo_conflict_override: bool = False
    reversed_at: datetime | None = None
    reversed_by_admin_id: int | None = None
    reversal_note: str | None = None
    promo_usage_restored: bool = False
    can_manual_finalize: bool = False
    manual_finalize_requires_promo_confirmation: bool = False
    manual_finalize_warnings: list[str] = Field(default_factory=list)
    can_reverse: bool = False
    reversal_block_reason: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_orm_payment_detail(cls, payment: Any) -> PaymentDetailOut:
        payload = PaymentOut.from_orm_payment(payment).model_dump(mode="json")
        promo_code_used = payment.promo_code_used
        promo_code = None
        if promo_code_used is not None:
            promo_code = getattr(promo_code_used, "archived_code", None) or getattr(
                promo_code_used, "code", None
            )
        payload.update(
            {
                "yookassa_payment_id": payment.yookassa_payment_id,
                "idempotence_key": payment.idempotence_key,
                "promo_code": promo_code,
                "checkout_base_amount": _float_or_none(
                    getattr(payment, "checkout_base_amount", None)
                ),
                "fulfilled_at": getattr(payment, "fulfilled_at", None),
                "fulfilled_by_admin_id": getattr(payment, "fulfilled_by_admin_id", None),
                "fulfillment_note": getattr(payment, "fulfillment_note", None),
                "promo_conflict_override": bool(getattr(payment, "promo_conflict_override", False)),
                "reversed_at": getattr(payment, "reversed_at", None),
                "reversed_by_admin_id": getattr(payment, "reversed_by_admin_id", None),
                "reversal_note": getattr(payment, "reversal_note", None),
                "promo_usage_restored": bool(getattr(payment, "promo_usage_restored", False)),
                "updated_at": payment.updated_at,
            }
        )
        return cast("PaymentDetailOut", cls.model_validate(payload))
