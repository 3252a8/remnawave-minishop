from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import PaymentCanceledPayload, SubscriptionAutoRenewFailedPayload
from db.dal import payment_dal
from db.models import Payment


def coerce_payment_db_id(order_id_raw: Any) -> int | None:
    """Pull a numeric DB id out of a webhook's ``orderId``/``order_id`` field."""
    if isinstance(order_id_raw, int):
        return order_id_raw
    if isinstance(order_id_raw, str) and order_id_raw.isdigit():
        return int(order_id_raw)
    return None


async def lookup_payment_by_order_or_provider_id(
    session: AsyncSession,
    *,
    providers: str | Collection[str],
    order_id_raw: Any = None,
    provider_payment_id: str | None = None,
) -> Payment | None:
    """Find a payment by DB id first, constrained to the expected providers.

    Returns ``None`` so callers stay in charge of the not-found response.
    """
    raw_providers = (providers,) if isinstance(providers, str) else providers
    provider_keys = tuple(
        dict.fromkeys(str(provider or "").strip().lower() for provider in raw_providers)
    )
    provider_keys = tuple(provider for provider in provider_keys if provider)
    if not provider_keys:
        return None

    payment_db_id = coerce_payment_db_id(order_id_raw)
    payment: Payment | None = None
    if payment_db_id is not None:
        payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        if payment and str(payment.provider or "").strip().lower() not in provider_keys:
            payment = None
    if not payment and provider_payment_id:
        matches = [
            candidate
            for provider in provider_keys
            if (
                candidate := await payment_dal.get_payment_by_provider_payment_id(
                    session,
                    provider,
                    provider_payment_id,
                )
            )
            is not None
        ]
        payment = matches[0] if len(matches) == 1 else None
    return payment


async def notify_user_payment_failed(
    *,
    bot: Bot,
    settings: Any,
    i18n: Any,
    session: AsyncSession,
    payment: Payment,
    message_key: str = "payment_failed",
) -> None:
    """Publish the standard payment-canceled event; reactions notify the user."""
    await events.emit_model(
        PaymentCanceledPayload(
            user_id=int(payment.user_id),
            payment_db_id=getattr(payment, "payment_id", None),
            provider=getattr(payment, "provider", None),
            provider_payment_id=getattr(payment, "provider_payment_id", None)
            or getattr(payment, "yookassa_payment_id", None),
            status=getattr(payment, "status", None),
            message_key=message_key,
        )
    )
    subscription_id = getattr(payment, "renewal_subscription_id", None)
    if bool(getattr(payment, "is_auto_renew", False)) and subscription_id is not None:
        # A generic cancellation remains available for ordinary payment UI
        # flows. Recurring marketing and recovery use a distinct typed event,
        # never provider text or a manual-cancellation proxy.
        await events.emit_model(
            SubscriptionAutoRenewFailedPayload(
                user_id=int(payment.user_id),
                subscription_id=int(subscription_id),
                provider=str(getattr(payment, "provider", "") or "unknown"),
                reason_code="provider_webhook_failed",
                payment_db_id=getattr(payment, "payment_id", None),
                provider_payment_id=getattr(payment, "provider_payment_id", None)
                or getattr(payment, "yookassa_payment_id", None),
                renewal_cycle_end=getattr(payment, "renewal_cycle_end", None),
                retryable=True,
                occurred_at=datetime.now(UTC),
            )
        )
