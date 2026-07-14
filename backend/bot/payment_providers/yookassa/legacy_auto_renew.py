from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from bot.payment_providers.shared import (
    parse_positive_int_units,
    sale_mode_base,
    sale_mode_tariff_key,
)
from db.dal import payment_dal
from db.models import Payment, Subscription


class _RenewalQuote(Protocol):
    amount: float
    currency: str
    months: int
    sale_mode: str
    tariff_key: str | None
    hwid_quote: dict[str, Any] | None


class _RenewalQuoteService(Protocol):
    async def quote_subscription_renewal(
        self,
        session: AsyncSession,
        sub: Subscription,
    ) -> _RenewalQuote | None: ...


def _decimal_value(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _validated_hwid_quote(
    metadata: Mapping[str, Any],
    quote: _RenewalQuote,
) -> dict[str, Any] | None:
    metadata_keys = {
        "hwid_devices",
        "hwid_valid_from",
        "hwid_valid_until",
        "hwid_pricing_period_months",
        "hwid_proration_ratio",
        "hwid_full_price",
    }
    has_hwid_metadata = any(
        key in metadata and str(metadata.get(key) or "").strip() for key in metadata_keys
    )
    authoritative = quote.hwid_quote
    if authoritative is None:
        if has_hwid_metadata:
            raise ValueError("Legacy auto-renew HWID metadata has no authoritative quote.")
        return None

    expected_devices = parse_positive_int_units(authoritative.get("device_count"))
    expected_valid_from = _datetime_value(authoritative.get("valid_from"))
    expected_valid_until = _datetime_value(authoritative.get("valid_until"))
    expected_period = parse_positive_int_units(authoritative.get("pricing_period_months"))
    expected_ratio = _decimal_value(authoritative.get("proration_ratio"))
    expected_full_price = _decimal_value(authoritative.get("full_price"))
    if (
        expected_devices is None
        or expected_valid_from is None
        or expected_valid_until is None
        or expected_valid_from >= expected_valid_until
        or expected_period is None
        or expected_ratio is None
        or expected_full_price is None
    ):
        raise ValueError("Authoritative legacy auto-renew HWID quote is incomplete.")

    comparisons = {
        "hwid_devices": (
            parse_positive_int_units(metadata.get("hwid_devices")),
            expected_devices,
        ),
        "hwid_valid_from": (
            _datetime_value(metadata.get("hwid_valid_from")),
            expected_valid_from,
        ),
        "hwid_valid_until": (
            _datetime_value(metadata.get("hwid_valid_until")),
            expected_valid_until,
        ),
        "hwid_pricing_period_months": (
            parse_positive_int_units(metadata.get("hwid_pricing_period_months")),
            expected_period,
        ),
        "hwid_proration_ratio": (
            _decimal_value(metadata.get("hwid_proration_ratio")),
            expected_ratio,
        ),
        "hwid_full_price": (
            _decimal_value(metadata.get("hwid_full_price")),
            expected_full_price,
        ),
    }
    mismatched = [
        field for field, (received, expected) in comparisons.items() if received != expected
    ]
    if mismatched:
        raise ValueError(
            "Legacy auto-renew HWID metadata does not match the authoritative quote: "
            + ", ".join(mismatched)
        )
    return authoritative


async def ensure_legacy_auto_renew_payment(
    session: AsyncSession,
    *,
    provider_payment_id: str,
    user_id: int,
    subscription_id: int,
    metadata: Mapping[str, Any],
    description: str,
    subscription_service: _RenewalQuoteService,
) -> Payment:
    """Recreate only a verifiable order emitted by the old recurring flow.

    Old workers charged YooKassa before persisting a local order id. During a
    rolling upgrade their successful callbacks must be recoverable, but the
    callback amount can never define the entitlement or expected price.
    """
    remote_id = str(provider_payment_id or "").strip()
    if not remote_id:
        raise ValueError("Legacy auto-renew payment has no provider id.")
    if subscription_id <= 0:
        raise ValueError("Legacy auto-renew subscription id is invalid.")

    sub = await session.get(Subscription, subscription_id)
    if sub is None:
        raise ValueError("Legacy auto-renew subscription does not exist.")
    if int(sub.user_id) != int(user_id):
        raise ValueError("Legacy auto-renew subscription belongs to another user.")
    if str(sub.provider or "").strip().lower() != "yookassa":
        raise ValueError("Legacy auto-renew subscription uses another provider.")

    metadata_months = parse_positive_int_units(metadata.get("subscription_months"))
    expected_months = int(sub.duration_months or 1)
    if metadata_months != expected_months:
        raise ValueError("Legacy auto-renew duration does not match the subscription.")

    metadata_sale_mode = str(metadata.get("sale_mode") or "").strip()
    if sale_mode_base(metadata_sale_mode) != "subscription":
        raise ValueError("Legacy auto-renew sale mode is not a subscription.")
    subscription_tariff_key = str(sub.tariff_key or "").strip() or None
    if sale_mode_tariff_key(metadata_sale_mode) != subscription_tariff_key:
        raise ValueError("Legacy auto-renew tariff does not match the subscription.")

    quote = await subscription_service.quote_subscription_renewal(session, sub)
    if quote is None:
        raise ValueError("Legacy auto-renew has no authoritative renewal quote.")
    if (
        quote.months != expected_months
        or quote.tariff_key != subscription_tariff_key
        or quote.sale_mode != metadata_sale_mode
    ):
        raise ValueError("Legacy auto-renew metadata does not match the renewal quote.")

    hwid_quote = _validated_hwid_quote(metadata, quote)
    return await payment_dal.ensure_payment_with_provider_id(
        session,
        user_id=user_id,
        amount=quote.amount,
        currency=quote.currency,
        months=quote.months,
        description=description,
        provider="yookassa",
        provider_payment_id=remote_id,
        sale_mode=quote.sale_mode,
        tariff_key=quote.tariff_key,
        purchased_hwid_devices=(
            parse_positive_int_units(hwid_quote.get("device_count")) if hwid_quote else None
        ),
        hwid_valid_from=hwid_quote.get("valid_from") if hwid_quote else None,
        hwid_valid_until=hwid_quote.get("valid_until") if hwid_quote else None,
        hwid_pricing_period_months=(
            parse_positive_int_units(hwid_quote.get("pricing_period_months"))
            if hwid_quote
            else None
        ),
        hwid_proration_ratio=(
            float(hwid_quote["proration_ratio"])
            if hwid_quote and hwid_quote.get("proration_ratio") is not None
            else None
        ),
        hwid_full_price=(
            float(hwid_quote["full_price"])
            if hwid_quote and hwid_quote.get("full_price") is not None
            else None
        ),
    )
