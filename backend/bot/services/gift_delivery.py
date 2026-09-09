"""Transactional gift email outbox, drained by the worker with bounded retries."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.email_auth_service import EmailAuthService
from bot.services.gift_email import render_gift_email
from bot.services.subscription_gifts import gift_url
from config.settings import Settings
from db.dal import gift_dal, message_log_dal, payment_dal, user_dal

logger = logging.getLogger(__name__)


async def deliver_gift_email(
    session: AsyncSession, *, payment_id: int, settings: Settings, i18n: JsonI18n
) -> bool:
    if not settings.smtp_delivery_configured or not settings.SUBSCRIPTION_MINI_APP_URL:
        return False
    payment = await payment_dal.get_payment_by_db_id_for_update(session, payment_id)
    gift = await gift_dal.by_payment(session, payment_id, lock=True)
    if payment is None or gift is None or payment.status != "succeeded" or gift.status != "ready":
        return False
    if not gift.recipient_email or gift.delivery_status == "sent" or gift.delivery_attempts >= 5:
        return False
    now = datetime.now(UTC)
    previous = gift.delivery_attempted_at
    if previous is not None:
        previous = previous.replace(tzinfo=UTC) if previous.tzinfo is None else previous
        if previous > now - timedelta(minutes=5):
            return False
    gift.delivery_attempts = int(gift.delivery_attempts or 0) + 1
    gift.delivery_attempted_at = now
    user = await user_dal.get_user_by_id(session, int(payment.user_id))
    language = user.language_code if user is not None else settings.DEFAULT_LANGUAGE
    link = gift_url(settings.SUBSCRIPTION_MINI_APP_URL, str(gift.token))
    content = render_gift_email(
        settings, i18n, language=language or settings.DEFAULT_LANGUAGE, link=link
    )
    try:
        await EmailAuthService(settings, i18n).send_rendered_email(
            email=str(gift.recipient_email), content=content
        )
    except Exception:
        # Do not log SMTP contents: this message contains a bearer link.
        logger.warning(
            "Gift email delivery failed: gift_id=%s attempt=%s",
            gift.gift_id,
            gift.delivery_attempts,
        )
        gift.delivery_status = "failed"
    else:
        gift.delivery_status = "sent"
        gift.delivered_at = now
    await message_log_dal.create_message_log_no_commit(
        session,
        {
            "user_id": gift.purchaser_id,
            "target_user_id": gift.purchaser_id,
            "is_admin_event": True,
            "event_type": "gift_email_delivery",
            "content": f"gift_id={gift.gift_id} status={gift.delivery_status} "
            f"attempt={gift.delivery_attempts}",
        },
    )
    sent = gift.delivery_status == "sent"
    await session.commit()
    return sent


async def run_gift_delivery_worker(
    settings: Settings, session_factory: sessionmaker, i18n: JsonI18n
) -> None:
    while True:
        try:
            async with session_factory() as session:
                ids = await gift_dal.pending_delivery(session)
            for payment_id in ids:
                async with session_factory() as session:
                    await deliver_gift_email(
                        session, payment_id=payment_id, settings=settings, i18n=i18n
                    )
        except Exception:
            logger.exception("Gift delivery worker tick failed")
        await asyncio.sleep(60)
