from __future__ import annotations

from typing import Any, Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import PaymentCanceledPayload
from db.dal import payment_dal
from db.models import Payment


def coerce_payment_db_id(order_id_raw: Any) -> Optional[int]:
    """Pull a numeric DB id out of a webhook's ``orderId``/``order_id`` field."""
    if isinstance(order_id_raw, int):
        return order_id_raw
    if isinstance(order_id_raw, str) and order_id_raw.isdigit():
        return int(order_id_raw)
    return None


async def lookup_payment_by_order_or_provider_id(
    session: AsyncSession,
    *,
    order_id_raw: Any = None,
    provider_payment_id: Optional[str] = None,
) -> Optional[Payment]:
    """Find a payment by DB id first, fall back to provider id.

    Returns ``None`` so callers stay in charge of the not-found response.
    """
    payment_db_id = coerce_payment_db_id(order_id_raw)
    payment: Optional[Payment] = None
    if payment_db_id is not None:
        payment = await payment_dal.get_payment_by_db_id(session, payment_db_id)
    if not payment and provider_payment_id:
        payment = await payment_dal.get_payment_by_provider_payment_id(session, provider_payment_id)
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
