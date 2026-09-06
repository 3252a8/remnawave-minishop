"""Recover recipient-bound gifts after panel timeouts or interrupted requests."""

import asyncio
import logging

from sqlalchemy.orm import sessionmaker

from bot.services.subscription_gifts import GiftError, claim_gift
from bot.services.subscription_service_impl.core import SubscriptionService
from db.dal import gift_dal

logger = logging.getLogger(__name__)


async def run_gift_activation_worker(
    session_factory: sessionmaker, service: SubscriptionService
) -> None:
    while True:
        try:
            async with session_factory() as session:
                pending = await gift_dal.pending_activation(session)
            for token, user_id in pending:
                try:
                    async with session_factory() as session:
                        await claim_gift(session, token=token, user_id=user_id, service=service)
                except GiftError as exc:
                    logger.warning(
                        "Gift activation recovery deferred: recipient=%s reason=%s",
                        user_id,
                        exc.code,
                    )
                except Exception:
                    logger.error("Gift activation recovery failed for recipient %s", user_id)
        except Exception:
            logger.exception("Gift activation recovery tick failed")
        await asyncio.sleep(60)
