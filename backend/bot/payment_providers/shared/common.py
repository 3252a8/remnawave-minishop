from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_dal
from db.models import Payment

from ..base import WebAppPaymentContext, normalize_payment_currency_code

Translator = Callable[..., str]


def make_translator(i18n: Any, language: str) -> Translator:
    """Return a ``_(key, **kw)`` callable that falls back to the key when i18n is absent."""

    def _(key: str, **kwargs: Any) -> str:
        if i18n is None:
            return key
        return str(i18n.gettext(language, key, **kwargs))

    return _


def format_decimal_amount(amount: Any, places: int = 2) -> Decimal:
    """Quantize ``amount`` to the given decimal places using half-up rounding."""
    return Decimal(str(amount)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def decimal_amounts_equal(left: Any, right: Any, places: int = 2) -> bool:
    """True when both values round to the same fixed-point representation."""
    return format_decimal_amount(left, places) == format_decimal_amount(right, places)


def payment_amount_matches(
    *,
    expected_amount: Any,
    received_amount: Any,
    places: int | None = 2,
) -> bool:
    """Return whether a provider's settled amount matches its issued invoice.

    The locally stored amount is normalized to the precision used when the
    invoice is created.  A callback must already be expressed at that
    precision: rounding it would make a distinct, signed settlement look like
    the expected amount.
    """
    if received_amount is None:
        return False
    try:
        expected_decimal = Decimal(str(expected_amount).strip())
        received_decimal = Decimal(str(received_amount).strip())
        if not expected_decimal.is_finite() or not received_decimal.is_finite():
            return False
        if places is None:
            return expected_decimal == received_decimal
        quantum = Decimal(10) ** -places
        expected_fixed = expected_decimal.quantize(quantum, rounding=ROUND_HALF_UP)
        received_fixed = received_decimal.quantize(quantum, rounding=ROUND_HALF_UP)
        return received_decimal == received_fixed and expected_fixed == received_fixed
    except (InvalidOperation, TypeError, ValueError):
        return False


def payment_amount_and_currency_match(
    *,
    expected_amount: Any,
    expected_currency: Any,
    received_amount: Any,
    received_currency: Any,
    places: int | None = 2,
) -> bool:
    """Return whether a provider confirmation matches the stored payment exactly.

    Payment providers must not finalize a payment when their successful callback
    omits either monetary field: treating a missing currency as the default
    currency would turn an unverified callback into a paid order.

    ``places=None`` selects an exact finite ``Decimal`` comparison for payment
    rails that use crypto-asset precision rather than a fixed fiat scale.
    """
    if received_amount is None or received_currency is None:
        return False
    received_currency_code = normalize_payment_currency_code(received_currency, default="")
    expected_currency_code = normalize_payment_currency_code(expected_currency, default="")
    if not received_currency_code or received_currency_code != expected_currency_code:
        return False
    return payment_amount_matches(
        expected_amount=expected_amount,
        received_amount=received_amount,
        places=places,
    )


def parse_positive_int_units(value: Any) -> int | None:
    """Return a positive integer only when the input represents whole units exactly."""
    if isinstance(value, bool):
        return None
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
        return None
    integer_value = int(decimal_value)
    return integer_value if integer_value > 0 else None


def format_human_units(value: Any) -> str:
    """Render numeric units the way the UI expects: integers w/o decimals, floats with %g."""
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:g}"


def build_payment_description(
    translator: Translator,
    *,
    months: Any,
    sale_mode: str,
    human_value: str | None = None,
) -> str:
    """Render the standard user-visible payment description.

    Mirrors the branching every callback handler used to repeat
    (traffic / hwid_devices / subscription).
    """
    base = sale_mode_base(sale_mode)
    if base in {"traffic", "traffic_package", "topup", "premium_topup"}:
        return translator(
            "payment_description_traffic",
            traffic_gb=human_value if human_value is not None else format_human_units(months),
        )
    if base in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}:
        return translator("payment_description_hwid_devices", count=int(float(months)))
    return translator("payment_description_subscription", months=int(float(months)))


def build_payment_record_payload(
    *,
    user_id: int,
    amount: float,
    currency: str,
    status: str,
    description: str,
    months: Any,
    provider: str,
    sale_mode: str,
    hwid_quote: dict | None = None,
) -> dict:
    """Assemble the payment-record dict that every callback handler used to inline.

    For the ``traffic`` sale modes, ``purchased_gb`` is taken from ``months``
    (callbacks encode the GB amount in the ``months`` slot); webapp creators
    use the ``payment_record_amounts`` helper directly to split the two.
    """
    base = sale_mode_base(sale_mode)
    is_traffic = sale_mode_is_traffic(sale_mode)
    is_hwid = sale_mode_is_hwid_devices(sale_mode)
    hwid_devices = int(float(months)) if is_hwid else None
    if hwid_quote:
        quote_devices = parse_positive_int_units(hwid_quote.get("device_count"))
        if quote_devices is not None:
            hwid_devices = quote_devices
    payload = {
        "user_id": user_id,
        "amount": amount,
        "currency": currency,
        "status": status,
        "description": description,
        "subscription_duration_months": int(float(months)) if base == "subscription" else None,
        "provider": provider,
        "sale_mode": sale_mode,
        "tariff_key": sale_mode_tariff_key(sale_mode),
        "purchased_gb": float(months) if is_traffic else None,
        "purchased_hwid_devices": hwid_devices,
    }
    if hwid_quote and hwid_devices is not None:
        payload.update(
            {
                "hwid_valid_from": hwid_quote.get("valid_from"),
                "hwid_valid_until": hwid_quote.get("valid_until"),
                "hwid_pricing_period_months": hwid_quote.get("pricing_period_months"),
                "hwid_proration_ratio": hwid_quote.get("proration_ratio"),
                "hwid_full_price": hwid_quote.get("full_price"),
            }
        )
    return payload


@dataclass(frozen=True)
class PaymentRecordAmounts:
    months: int
    purchased_gb: float | None
    purchased_hwid_devices: int | None
    tariff_key: str | None
    traffic_sale: bool
    hwid_devices_sale: bool


def sale_mode_base(sale_mode: str) -> str:
    return str(sale_mode or "").split("@", 1)[0].split("|", 1)[0]


def sale_mode_is_traffic(sale_mode: str) -> bool:
    return sale_mode_base(sale_mode) in {"traffic", "traffic_package", "topup", "premium_topup"}


def sale_mode_is_hwid_devices(sale_mode: str) -> bool:
    return sale_mode_base(sale_mode) in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}


def sale_mode_tariff_key(sale_mode: str) -> str | None:
    if "@" not in str(sale_mode or ""):
        return None
    return str(sale_mode).split("@", 1)[1].split("|", 1)[0] or None


def format_number_for_payload(value: Any) -> str:
    value_float = float(value)
    return str(int(value_float)) if value_float.is_integer() else f"{value_float:g}"


def payment_record_amounts(
    *,
    months: Any,
    sale_mode: str,
    traffic_gb: float | None = None,
    hwid_device_count: int | None = None,
) -> PaymentRecordAmounts:
    traffic_sale = sale_mode_is_traffic(sale_mode)
    hwid_devices_sale = sale_mode_is_hwid_devices(sale_mode)
    units = traffic_gb if traffic_sale and traffic_gb is not None else months
    purchased_hwid_devices = int(float(months)) if hwid_devices_sale else None
    if not hwid_devices_sale and hwid_device_count is not None:
        parsed_hwid_devices = parse_positive_int_units(hwid_device_count)
        if parsed_hwid_devices is not None:
            purchased_hwid_devices = parsed_hwid_devices
    return PaymentRecordAmounts(
        months=int(float(units)) if traffic_sale else int(float(months)),
        purchased_gb=float(units) if traffic_sale else None,
        purchased_hwid_devices=purchased_hwid_devices,
        tariff_key=sale_mode_tariff_key(sale_mode),
        traffic_sale=traffic_sale,
        hwid_devices_sale=hwid_devices_sale,
    )


def payment_units_for_activation(payment: Any, sale_mode: str) -> Any:
    """Resolve purchased units from a payment record for webhook activation."""
    base = sale_mode_base(sale_mode)
    if sale_mode_is_traffic(base):
        return (
            getattr(payment, "purchased_gb", None)
            or getattr(payment, "subscription_duration_months", None)
            or 1
        )
    if sale_mode_is_hwid_devices(base):
        return (
            getattr(payment, "purchased_hwid_devices", None)
            or getattr(payment, "subscription_duration_months", None)
            or 1
        )
    return getattr(payment, "subscription_duration_months", None) or 1


def json_error(status: int, code: str, message: str) -> web.Response:
    return web.json_response({"ok": False, "error": code, "message": message}, status=status)


def payment_unavailable() -> web.Response:
    return json_error(400, "payment_unavailable", "Payment method unavailable")


def payment_failed(message: str = "Failed to create payment") -> web.Response:
    return json_error(502, "payment_failed", message)


def payment_link_response(
    *,
    payment_url: str,
    payment_id: int | None,
    action: str = "open_link",
) -> web.Response:
    return web.json_response(
        {
            "ok": True,
            "action": action,
            "payment_url": payment_url,
            "payment_id": payment_id,
        }
    )


def detached_payment_snapshot(payment: Any) -> SimpleNamespace:
    """Copy scalar payment columns so external calls do not keep a DB transaction open."""
    return SimpleNamespace(
        **{column.name: getattr(payment, column.name, None) for column in Payment.__table__.columns}
    )


async def create_base_payment_record(
    session: AsyncSession,
    *,
    user_id: int,
    amount: float,
    currency: str,
    status: str,
    description: str,
    months: int,
    provider: str,
    sale_mode: str | None = None,
    tariff_key: str | None = None,
    purchased_gb: float | None = None,
    purchased_hwid_devices: int | None = None,
    hwid_valid_from: Any | None = None,
    hwid_valid_until: Any | None = None,
    hwid_pricing_period_months: int | None = None,
    hwid_proration_ratio: float | None = None,
    hwid_full_price: float | None = None,
    promo_code_id: int | None = None,
    promo_effect_summary: str | None = None,
    promo_bonus_days: int | None = None,
    promo_discount_percent: float | None = None,
    promo_duration_multiplier: float | None = None,
    promo_traffic_multiplier: float | None = None,
    promo_applies_to: str | None = None,
    promo_min_subscription_months: int | None = None,
    promo_min_traffic_gb: float | None = None,
    checkout_base_amount: float | None = None,
    checkout_discount_amount: float | None = None,
    checkout_charged_months: int | None = None,
    checkout_charged_gb: float | None = None,
    checkout_quoted_at: Any | None = None,
) -> Payment:
    payment = await payment_dal.create_payment_record(
        session,
        {
            "user_id": user_id,
            "amount": amount,
            "currency": currency,
            "status": status,
            "description": description,
            "subscription_duration_months": months,
            "provider": provider,
            "sale_mode": sale_mode,
            "tariff_key": tariff_key,
            "purchased_gb": purchased_gb,
            "purchased_hwid_devices": purchased_hwid_devices,
            "hwid_valid_from": hwid_valid_from,
            "hwid_valid_until": hwid_valid_until,
            "hwid_pricing_period_months": hwid_pricing_period_months,
            "hwid_proration_ratio": hwid_proration_ratio,
            "hwid_full_price": hwid_full_price,
            "promo_code_id": promo_code_id,
            "promo_effect_summary": promo_effect_summary,
            "promo_bonus_days": promo_bonus_days,
            "promo_discount_percent": promo_discount_percent,
            "promo_duration_multiplier": promo_duration_multiplier,
            "promo_traffic_multiplier": promo_traffic_multiplier,
            "promo_applies_to": promo_applies_to,
            "promo_min_subscription_months": promo_min_subscription_months,
            "promo_min_traffic_gb": promo_min_traffic_gb,
            "checkout_base_amount": checkout_base_amount,
            "checkout_discount_amount": checkout_discount_amount,
            "checkout_charged_months": checkout_charged_months,
            "checkout_charged_gb": checkout_charged_gb,
            "checkout_quoted_at": checkout_quoted_at,
        },
    )
    await session.commit()
    return payment


async def create_webapp_payment_record(
    ctx: WebAppPaymentContext,
    *,
    amount: float,
    currency: str,
    status: str,
    provider: str,
) -> Payment:
    amounts = payment_record_amounts(
        months=ctx.months,
        sale_mode=ctx.sale_mode,
        traffic_gb=ctx.traffic_gb,
        hwid_device_count=ctx.hwid_device_count,
    )
    return await create_base_payment_record(
        ctx.session,
        user_id=ctx.user_id,
        amount=amount,
        currency=currency,
        status=status,
        description=ctx.description,
        months=amounts.months,
        provider=provider,
        sale_mode=ctx.sale_mode,
        tariff_key=amounts.tariff_key,
        purchased_gb=amounts.purchased_gb,
        purchased_hwid_devices=amounts.purchased_hwid_devices,
        hwid_valid_from=ctx.hwid_valid_from,
        hwid_valid_until=ctx.hwid_valid_until,
        hwid_pricing_period_months=ctx.hwid_pricing_period_months,
        hwid_proration_ratio=ctx.hwid_proration_ratio,
        hwid_full_price=ctx.hwid_full_price,
        promo_code_id=ctx.promo_code_id,
        promo_effect_summary=ctx.promo_effect_summary,
        promo_bonus_days=ctx.promo_bonus_days,
        promo_discount_percent=ctx.promo_discount_percent,
        promo_duration_multiplier=ctx.promo_duration_multiplier,
        promo_traffic_multiplier=ctx.promo_traffic_multiplier,
        promo_applies_to=ctx.promo_applies_to,
        promo_min_subscription_months=ctx.promo_min_subscription_months,
        promo_min_traffic_gb=ctx.promo_min_traffic_gb,
        checkout_base_amount=ctx.checkout_base_amount,
        checkout_discount_amount=ctx.checkout_discount_amount,
        checkout_charged_months=ctx.checkout_charged_months,
        checkout_charged_gb=ctx.checkout_charged_gb,
        checkout_quoted_at=ctx.checkout_quoted_at,
    )


async def reusable_webapp_payment_response(
    ctx: WebAppPaymentContext,
    provider_spec: Any,
    *,
    since_minutes: int | None = None,
) -> web.Response | None:
    resolver = getattr(provider_spec, "reuse_webapp_payment", None)
    if resolver is None:
        return None

    amounts = payment_record_amounts(
        months=ctx.months,
        sale_mode=ctx.sale_mode,
        traffic_gb=ctx.traffic_gb,
        hwid_device_count=ctx.hwid_device_count,
    )
    payment = await payment_dal.find_recent_pending_provider_payment(
        ctx.session,
        user_id=ctx.user_id,
        provider=provider_spec.provider_key,
        pending_status=provider_spec.pending_status,
        amount=ctx.price,
        currency=ctx.currency,
        sale_mode=ctx.sale_mode,
        months=amounts.months,
        purchased_gb=amounts.purchased_gb,
        purchased_hwid_devices=amounts.purchased_hwid_devices,
        tariff_key=amounts.tariff_key,
        promo_code_id=ctx.promo_code_id,
        promo_effect_summary=ctx.promo_effect_summary,
        since_minutes=since_minutes,
    )
    if payment is None:
        return None

    payment_snapshot = detached_payment_snapshot(payment)
    await ctx.session.rollback()
    payment_url = await resolver(ctx, payment_snapshot)
    if not payment_url:
        return None
    return payment_link_response(payment_url=payment_url, payment_id=payment_snapshot.payment_id)


async def mark_payment_failed_creation(session: AsyncSession, payment_id: int) -> None:
    await payment_dal.update_payment_status_by_db_id(session, payment_id, "failed_creation")
    await session.commit()
