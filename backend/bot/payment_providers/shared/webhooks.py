from __future__ import annotations

import logging
from typing import Any, Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import payment_dal, user_dal
from db.models import Payment

from .common import make_translator


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
        payment = await payment_dal.get_payment_by_provider_payment_id(
            session, provider_payment_id
        )
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
    """Send the localized ``payment_failed`` text to the user; never raises."""
    db_user = payment.user or await user_dal.get_user_by_id(session, payment.user_id)
    language = (
        db_user.language_code
        if db_user and db_user.language_code
        else settings.DEFAULT_LANGUAGE
    )
    translator = make_translator(i18n, language)
    try:
        await bot.send_message(payment.user_id, translator(message_key))
    except Exception:
        logging.exception(
            "Webhook helper: failed to notify user %s about %s.",
            payment.user_id,
            message_key,
        )
