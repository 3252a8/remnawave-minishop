"""Server-priced, short-lived quotes for paying for add-ons with subscription days."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.payment_events import sale_mode_base
from bot.services.balance_recurring import active_balance_recurrence
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from config.tariffs_config import default_currency_key_for_settings, payment_currency_code
from db.gift_models import SubscriptionGift
from db.models import Payment, Subscription

METHOD = "subscription_days"
QUOTE_TTL_SECONDS = 300
MODES = frozenset({"hwid_devices", "topup", "premium_topup"})


class SubscriptionDaysError(RuntimeError):
    def __init__(self, code: str, *, status: int = 409, reason: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.reason = reason


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def positive_decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    return result if result.is_finite() and result > 0 else None


@dataclass(frozen=True)
class AddonSelection:
    mode: str
    tariff_key: str
    units: Decimal

    @classmethod
    def parse(cls, mode: object, tariff_key: object, units: object) -> AddonSelection:
        base = sale_mode_base(str(mode or ""))
        quantity = positive_decimal(units)
        key = str(tariff_key or "").strip()
        if (
            base not in MODES
            or not key
            or quantity is None
            or quantity > 2**31 - 1
            or quantity < Decimal(1) / 1024**3
            or (base == "hwid_devices" and quantity != quantity.to_integral_value())
        ):
            raise SubscriptionDaysError("invalid_subscription_days_purchase", status=400)
        return cls(base, key, quantity)

    def identity(self) -> dict[str, str]:
        return {"mode": self.mode, "tariff": self.tariff_key, "units": str(self.units.normalize())}


def enabled(settings: Settings, mode: str) -> bool:
    return bool(
        settings.SUBSCRIPTION_DAYS_DEVICES_ENABLED
        if mode == "hwid_devices"
        else settings.SUBSCRIPTION_DAYS_TRAFFIC_ENABLED
        if mode in {"topup", "premium_topup"}
        else False
    )


def _has_paid_value(payment: Payment) -> bool:
    return positive_decimal(payment.amount) is not None or (
        payment.funding_source in {"internal_user_balance", "internal_partner_balance"}
        and positive_decimal(payment.checkout_total_amount) is not None
    )


async def paid_basis(
    session: AsyncSession, sub: Subscription, service: SubscriptionService, now: datetime
) -> tuple[Decimal | None, int | None, str | None]:
    """A tariff price alone must never make a complimentary subscription spendable."""
    if not sub.is_active or not sub.end_date or aware(sub.end_date) <= now:
        return None, None, "subscription_required"
    if not (int(sub.duration_days or 0) > 0 or int(sub.duration_months or 0) > 0):
        return None, None, "duration_required"
    provider = str(sub.provider or "").lower()
    if active_balance_recurrence(sub) or (provider == "tribute" and sub.auto_renew_enabled):
        return None, None, "recurring_conflict"
    if (
        provider in {"trial", "admin", "manual", "registration", "referral", "bonus"}
        or str(sub.status_from_panel or "").upper() == "TRIAL"
    ):
        return None, None, "paid_subscription_required"
    currency = payment_currency_code(default_currency_key_for_settings(service.settings))
    paid = await session.scalar(
        select(Payment)
        .where(
            Payment.user_id == sub.user_id,
            Payment.status == "succeeded",
            or_(
                Payment.sale_mode == "subscription",
                Payment.sale_mode.like("subscription@%"),
                Payment.sale_mode.like("tariff_change@%"),
            ),
        )
        .order_by(Payment.payment_id.desc())
        .limit(1)
    )
    if sub.gift_terms_snapshot:
        paid = await session.scalar(
            select(Payment)
            .join(SubscriptionGift, SubscriptionGift.payment_id == Payment.payment_id)
            .where(
                SubscriptionGift.recipient_id == sub.user_id,
                SubscriptionGift.status == "activated",
                SubscriptionGift.activation_end_at > now,
                Payment.tariff_key == sub.tariff_key,
                Payment.status == "succeeded",
            )
            .order_by(SubscriptionGift.activated_at.desc())
            .limit(1)
        )
    if paid is None or not _has_paid_value(paid):
        return None, None, "paid_subscription_required"
    if paid.tariff_key and paid.tariff_key != sub.tariff_key:
        return None, None, "paid_subscription_required"
    if paid.currency != currency:
        return None, None, "price_unavailable"
    # Newer payments retain the funded period boundary. A later complimentary
    # extension must not turn an already expired paid period into spendable days.
    if paid.fulfillment_after_snapshot and not sub.gift_terms_snapshot:
        try:
            snapshot = json.loads(paid.fulfillment_after_snapshot)
            paid_ends = [
                aware(datetime.fromisoformat(item["end_date"]))
                for user in snapshot.get("users", [])
                for item in user.get("subscriptions", [])
                if item.get("subscription_id") == sub.subscription_id and item.get("end_date")
            ]
        except (TypeError, ValueError, AttributeError):
            return None, None, "paid_subscription_required"
        if not paid_ends or max(paid_ends) <= now or aware(sub.end_date) > max(paid_ends):
            return None, None, "paid_subscription_required"
    monthly = positive_decimal(sub.effective_monthly_price_rub)
    if monthly is None:
        duration = (
            int(paid.subscription_duration_days or 0)
            or int(paid.subscription_duration_months or 0) * 30
        )
        amount = positive_decimal(paid.checkout_total_amount) or positive_decimal(paid.amount)
        if amount is not None and duration > 0:
            return amount / duration, int(paid.payment_id), None
        tariff = service.settings.tariffs_config.require_configured(str(sub.tariff_key))
        monthly = positive_decimal(
            service._tariff_effective_monthly_price(
                tariff, default_currency_key_for_settings(service.settings)
            )
        )
    if monthly is None:
        return None, None, "price_unavailable"
    return monthly / 30, int(paid.payment_id), None


def sign_quote(settings: Settings, payload: dict[str, Any]) -> str:
    body = (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        )
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(
        settings.WEBAPP_SESSION_SECRET.encode(), f"addon-days:{body}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{body}.{signature}"


def read_quote(settings: Settings, token: str, user_id: int) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            settings.WEBAPP_SESSION_SECRET.encode(), f"addon-days:{body}".encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if not isinstance(payload, dict) or payload.get("v") != 1 or payload.get("user") != user_id:
            raise ValueError("owner")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise SubscriptionDaysError("subscription_days_quote_stale") from exc
    return payload


async def package_quote(
    session: AsyncSession,
    service: SubscriptionService,
    sub: Subscription,
    selection: AddonSelection,
    now: datetime,
) -> tuple[Decimal | None, dict[str, Any]]:
    config = service.settings.tariffs_config
    if config is None or sub.tariff_key != selection.tariff_key:
        return None, {}
    tariff = config.require_configured(selection.tariff_key)
    if tariff.billing_model != "period":
        return None, {}
    currency = default_currency_key_for_settings(service.settings)
    if selection.mode == "hwid_devices":
        quote = await service.quote_hwid_device_topup(
            session,
            user_id=int(sub.user_id),
            device_count=int(selection.units),
            tariff_key=selection.tariff_key,
            currency=currency,
            now=now,
        )
        return (
            (
                positive_decimal(quote.get("price")),
                {
                    key: quote.get(key)
                    for key in (
                        "full_price",
                        "pricing_period_months",
                        "pricing_period_days",
                        "proration_ratio",
                        "traffic_bonus_bytes",
                    )
                },
            )
            if quote
            else (None, {})
        )
    if selection.mode == "premium_topup" and not tariff.premium_squad_uuids:
        return None, {}
    packages = (
        tariff.premium_topup_packages
        if selection.mode == "premium_topup"
        else tariff.topup_packages
    )
    for package in packages.for_currency(currency) if packages else []:
        if Decimal(str(package.gb)) == selection.units:
            return positive_decimal(package.price), {}
    return None, {}


async def attach_days_quotes(
    session: AsyncSession,
    service: SubscriptionService,
    sub: Subscription,
    plans: list[dict[str, Any]],
) -> None:
    settings = service.settings
    if not any(enabled(settings, str(p.get("sale_mode"))) for p in plans):
        return
    now = datetime.now(UTC)
    daily, source, reason = await paid_basis(session, sub, service, now)
    for plan in plans:
        mode = str(plan.get("sale_mode") or "")
        if not enabled(settings, mode):
            continue
        selection = AddonSelection.parse(
            mode,
            plan.get("tariff_key"),
            plan.get("device_count") if mode == "hwid_devices" else plan.get("traffic_gb"),
        )
        price, hwid = await package_quote(session, service, sub, selection, now)
        failure = reason or ("price_unavailable" if price is None else None)
        days = (
            int((price / daily).to_integral_value(rounding=ROUND_CEILING))
            if price and daily
            else None
        )
        old_end = aware(sub.end_date) if sub.end_date else None
        try:
            new_end = old_end - timedelta(days=days) if old_end and days else None
        except OverflowError:
            days = None
            new_end = None
            failure = failure or "insufficient_days"
        minimum = settings.SUBSCRIPTION_DAYS_MIN_REMAINING
        if not failure and new_end is not None and new_end < now + timedelta(days=minimum):
            failure = "insufficient_days"
        payload = {
            "v": 1,
            "user": int(sub.user_id),
            "sub": int(sub.subscription_id),
            **selection.identity(),
            "days": days,
            "before": old_end.isoformat() if old_end else None,
            "after": new_end.isoformat() if new_end else None,
            "source": source,
            "price": str(price),
            "rate": str(daily),
            "min": minimum,
            "currency": str(plan.get("currency")),
            "hwid": hwid,
            "at": now.isoformat(),
            "exp": int(now.timestamp()) + QUOTE_TTL_SECONDS,
            "nonce": secrets.token_hex(16),
        }
        plan["subscription_days"] = {
            "eligible": failure is None,
            "disabled_reason": failure,
            "days_to_charge": days,
            "current_expires_at": old_end.isoformat() if old_end else None,
            "next_expires_at": new_end.isoformat() if new_end else None,
            "minimum_remaining_days": minimum,
            "quote_token": sign_quote(settings, payload) if failure is None else None,
            "price_amount": float(price) if price else None,
            "currency": str(plan.get("currency")),
        }
