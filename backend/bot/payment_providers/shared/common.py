from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable, Optional

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_dal
from db.models import Payment

from ..base import WebAppPaymentContext

Translator = Callable[..., str]


def make_translator(i18n: Any, language: str) -> Translator:
    """Return a ``_(key, **kw)`` callable that falls back to the key when i18n is absent."""

    def _(key: str, **kwargs: Any) -> str:
        if i18n is None:
            return key
        return i18n.gettext(language, key, **kwargs)

    return _


def format_decimal_amount(amount: Any, places: int = 2) -> Decimal:
    """Quantize ``amount`` to the given decimal places using bank rounding."""
    return Decimal(str(amount)).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def decimal_amounts_equal(left: Any, right: Any, places: int = 2) -> bool:
    """True when both values round to the same fixed-point representation."""
    return format_decimal_amount(left, places) == format_decimal_amount(right, places)


def parse_positive_int_units(value: Any) -> Optional[int]:
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
    human_value: Optional[str] = None,
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
    hwid_quote: Optional[dict] = None,
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
    purchased_gb: Optional[float]
    purchased_hwid_devices: Optional[int]
    tariff_key: Optional[str]
    traffic_sale: bool
    hwid_devices_sale: bool


def sale_mode_base(sale_mode: str) -> str:
    return str(sale_mode or "").split("@", 1)[0].split("|", 1)[0]


def sale_mode_is_traffic(sale_mode: str) -> bool:
    return sale_mode_base(sale_mode) in {"traffic", "traffic_package", "topup", "premium_topup"}


def sale_mode_is_hwid_devices(sale_mode: str) -> bool:
    return sale_mode_base(sale_mode) in {"hwid_device", "hwid_devices", "hwid_devices_renewal"}


def sale_mode_tariff_key(sale_mode: str) -> Optional[str]:
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
    traffic_gb: Optional[float] = None,
    hwid_device_count: Optional[int] = None,
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
    payment_id: Optional[int],
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
    sale_mode: Optional[str] = None,
    tariff_key: Optional[str] = None,
    purchased_gb: Optional[float] = None,
    purchased_hwid_devices: Optional[int] = None,
    hwid_valid_from: Optional[Any] = None,
    hwid_valid_until: Optional[Any] = None,
    hwid_pricing_period_months: Optional[int] = None,
    hwid_proration_ratio: Optional[float] = None,
    hwid_full_price: Optional[float] = None,
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
    )


async def reusable_webapp_payment_response(
    ctx: WebAppPaymentContext,
    provider_spec: Any,
    *,
    since_minutes: Optional[int] = None,
) -> Optional[web.Response]:
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
        since_minutes=since_minutes,
    )
    if payment is None:
        return None

    payment_url = await resolver(ctx, payment)
    if not payment_url:
        return None
    return payment_link_response(payment_url=payment_url, payment_id=payment.payment_id)


async def mark_payment_failed_creation(session: AsyncSession, payment_id: int) -> None:
    await payment_dal.update_payment_status_by_db_id(session, payment_id, "failed_creation")
    await session.commit()
