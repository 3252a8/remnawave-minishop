from __future__ import annotations

import logging
from datetime import UTC, datetime

from aiogram import Bot

from bot.services.message_audit import log_user_message_delivery
from bot.services.telegram_notifications import (
    mark_telegram_notifications_status,
    telegram_notification_status_from_error,
)
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager

logger = logging.getLogger(__name__)


class OutboundMessagingService:
    def __init__(self, bot: Bot | None = None) -> None:
        self.bot = bot

    async def send_text(
        self,
        session,
        *,
        user_id: int,
        text: str,
        parse_mode: str | None = "HTML",
        disable_web_page_preview: bool = True,
        event_type: str = "outbound_message_sent",
    ) -> bool:
        queue_manager = get_queue_manager()
        if queue_manager is not None:
            await send_message_via_queue(
                queue_manager,
                int(user_id),
                MessageContent(content_type="text", text=text),
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
            await log_user_message_delivery(
                session,
                target_user_id=int(user_id),
                event_type=event_type,
                channel="telegram_queue",
                recipient=str(user_id),
                content=text[:4096],
                timestamp=datetime.now(UTC),
            )
            return True

        if self.bot is None:
            return False
        try:
            await self.bot.send_message(
                int(user_id),
                text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
        except Exception as exc:
            status = telegram_notification_status_from_error(exc)
            if status:
                await mark_telegram_notifications_status(session, int(user_id), status)
                return False
            logger.exception("Failed to send outbound message to user %s.", user_id)
            return False
        await log_user_message_delivery(
            session,
            target_user_id=int(user_id),
            event_type=event_type,
            channel="telegram",
            recipient=str(user_id),
            content=text[:4096],
            timestamp=datetime.now(UTC),
        )
        return True
