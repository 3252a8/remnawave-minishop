"""Transactional fulfillment of add-ons funded by existing subscription time."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.payment_fulfillment import (
    capture_payment_entitlement_snapshot,
    persist_payment_fulfillment,
)
from bot.services.subscription_days_quotes import (
    METHOD,
    AddonSelection,
    SubscriptionDaysError,
    aware,
    enabled,
    package_quote,
    paid_basis,
    read_quote,
)
from bot.services.subscription_service_impl.core import SubscriptionService
from config.tariffs_config import default_currency_key_for_settings, payment_currency_code
from db.dal import subscription_dal
from db.models import Payment, TrafficTopup, User


async def purchase_with_days(
    session: AsyncSession,
    service: SubscriptionService,
    *,
    user_id: int,
    selection: AddonSelection,
    token: str,
    description: str,
) -> Payment:
    """Caller owns commit; the user lock serializes confirmations and fulfillment."""
    settings = service.settings
    quote = read_quote(settings, token, user_id)
    if any(quote.get(key) != value for key, value in selection.identity().items()):
        raise SubscriptionDaysError("subscription_days_quote_stale")
    identifier = hashlib.sha256(token.encode()).hexdigest()
    lookup = select(Payment).where(
        Payment.provider == METHOD,
        Payment.provider_payment_id == identifier,
        Payment.user_id == user_id,
    )
    existing = await session.scalar(lookup.with_for_update())
    if existing is not None:
        if existing.status != "succeeded":
            raise SubscriptionDaysError("subscription_days_quote_stale")
        return existing
    user = await session.scalar(
        select(User)
        .where(User.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or user.is_banned or not user.panel_user_uuid:
        raise SubscriptionDaysError("subscription_days_unavailable", reason="subscription_required")
    # A simultaneous request may have completed while this request waited for the user lock.
    existing = await session.scalar(lookup)
    if existing is not None:
        if existing.status != "succeeded":
            raise SubscriptionDaysError("subscription_days_quote_stale")
        return existing
    now = datetime.now(UTC)
    if quote["exp"] <= int(now.timestamp()):
        raise SubscriptionDaysError("subscription_days_quote_stale")
    if not enabled(settings, selection.mode):
        raise SubscriptionDaysError("subscription_days_unavailable")
    sub = await subscription_dal.get_active_subscription_by_user_id_for_update(session, user_id)
    if (
        sub is None
        or sub.subscription_id != quote["sub"]
        or sub.panel_user_uuid != user.panel_user_uuid
    ):
        raise SubscriptionDaysError("subscription_days_quote_stale")
    daily, source, reason = await paid_basis(session, sub, service, now)
    if reason or daily is None:
        raise SubscriptionDaysError("subscription_days_unavailable", reason=reason)
    if (
        aware(sub.end_date).isoformat() != quote["before"]
        or source != quote["source"]
        or daily != Decimal(quote["rate"])
        or quote["min"] != settings.SUBSCRIPTION_DAYS_MIN_REMAINING
        or payment_currency_code(default_currency_key_for_settings(settings)) != quote["currency"]
    ):
        raise SubscriptionDaysError("subscription_days_quote_stale")
    # Reprice at the server's original quote time: elapsed seconds must not cause
    # spurious repricing, while an administrator's package edits invalidate the quote.
    price, hwid = await package_quote(
        session, service, sub, selection, aware(datetime.fromisoformat(quote["at"]))
    )
    if price is None or price != Decimal(quote["price"]) or hwid != quote["hwid"]:
        raise SubscriptionDaysError("subscription_days_quote_stale")
    days = int((price / daily).to_integral_value(rounding=ROUND_CEILING))
    new_end = aware(sub.end_date) - timedelta(days=days)
    if days != quote["days"] or new_end.isoformat() != quote["after"]:
        raise SubscriptionDaysError("subscription_days_quote_stale")
    if new_end < now + timedelta(days=settings.SUBSCRIPTION_DAYS_MIN_REMAINING):
        raise SubscriptionDaysError("subscription_days_unavailable", reason="insufficient_days")
    payment = Payment(
        user_id=user_id,
        provider=METHOD,
        funding_source=METHOD,
        provider_payment_id=identifier,
        idempotence_key=f"days:{identifier}",
        amount=0,
        currency=quote["currency"],
        status="pending",
        description=description,
        tariff_key=selection.tariff_key,
        sale_mode=f"{selection.mode}@{selection.tariff_key}",
        subscription_days_spent=days,
        subscription_days_snapshot=json.dumps(quote, sort_keys=True),
        fulfillment_source="internal",
    )
    session.add(payment)
    await session.flush()
    before = await capture_payment_entitlement_snapshot(session, payment, include_referrer=False)
    sub.end_date = new_end
    await session.flush()
    if selection.mode == "hwid_devices":
        payment.hwid_valid_from = now
        payment.hwid_valid_until = new_end
        payment.hwid_full_price = hwid["full_price"]
        payment.hwid_pricing_period_months = hwid["pricing_period_months"]
        payment.hwid_pricing_period_days = hwid["pricing_period_days"]
        payment.hwid_proration_ratio = hwid["proration_ratio"]
        payment.hwid_traffic_bonus_bytes = hwid["traffic_bonus_bytes"]
        await session.flush()
        result = await service.activate_hwid_device_topup(
            session,
            user_id=user_id,
            device_count=int(selection.units),
            payment_amount=0,
            payment_db_id=int(payment.payment_id),
            provider=METHOD,
            tariff_key=selection.tariff_key,
            notify=False,
        )
    else:
        activate = (
            service.activate_premium_topup
            if selection.mode == "premium_topup"
            else service.activate_topup
        )
        result = await activate(
            session,
            user_id=user_id,
            traffic_gb=float(selection.units),
            payment_amount=0,
            payment_db_id=int(payment.payment_id),
            provider=METHOD,
            tariff_key=selection.tariff_key,
            notify=False,
        )
        if result is not None:
            linked = await session.scalar(
                select(TrafficTopup.topup_id).where(TrafficTopup.payment_id == payment.payment_id)
            )
            if linked is None:
                raise SubscriptionDaysError("subscription_days_panel_failed", status=502)
    if result is None or not await service.sync_main_traffic_limit_to_panel(session, user_id):
        raise SubscriptionDaysError("subscription_days_panel_failed", status=502)
    payment.status = "succeeded"
    await session.flush()
    after = await capture_payment_entitlement_snapshot(session, payment, include_referrer=False)
    persist_payment_fulfillment(payment, before=before, after=after)
    await session.flush()
    return payment
