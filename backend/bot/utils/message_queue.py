import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot.utils.telegram_markup import (
    is_profile_link_error,
    remove_profile_link_buttons,
)


@dataclass
class QueuedMessage:
    """Represents a queued message with all necessary parameters"""

    chat_id: int
    method_name: str  # 'send_message', 'edit_message_text', etc.
    kwargs: dict[str, Any]
    callback: Callable[[Any], Awaitable[None]] | None = None  # Optional callback for result


class MessageQueue:
    """Message queue with rate limiting for Telegram API"""

    # Telegram allows ~1 message/sec to the same chat before returning 429.
    PER_CHAT_MIN_INTERVAL_SECONDS = 1.0
    # Drop per-chat timestamps older than this to keep the dict bounded.
    PER_CHAT_TTL_SECONDS = 5.0

    def __init__(self, messages_per_second: float, burst_size: int = 5):
        self.messages_per_second = messages_per_second
        self.burst_size = burst_size
        self.queue: deque[QueuedMessage] = deque()
        self.last_send_times: deque[datetime] = deque()
        self.is_processing = False
        self.delay_between_messages = 1.0 / messages_per_second
        self.total_sent = 0
        self.total_failed = 0
        self._chat_last_sent: dict[int, datetime] = {}
        self._processing_task: asyncio.Task[None] | None = None

    async def add_message(self, message: QueuedMessage) -> None:
        """Add message to queue"""
        self.queue.append(message)
        if not self.is_processing and (
            self._processing_task is None or self._processing_task.done()
        ):
            task = asyncio.create_task(self._process_queue())
            self._processing_task = task
            task.add_done_callback(self._forget_processing_task)

    def _forget_processing_task(self, task: asyncio.Task[None]) -> None:
        if self._processing_task is task:
            self._processing_task = None

    async def _process_queue(self) -> None:
        """Process messages from queue with rate limiting"""
        if self.is_processing:
            return

        self.is_processing = True

        try:
            while self.queue:
                # Peek at the head to honor per-chat throttling before popping.
                message = self.queue[0]
                await self._wait_if_needed(message.chat_id)
                self.queue.popleft()

                try:
                    await self._send_message(message)
                    self._record_send_time(message.chat_id)

                except TelegramBadRequest as exc:
                    fallback_message = self._build_profile_link_fallback(message, exc)
                    if fallback_message:
                        logging.warning(
                            "Telegram rejected profile buttons for chat %s: %s. "
                            "Retrying without tg:// links.",
                            message.chat_id,
                            getattr(exc, "message", "") or str(exc),
                        )
                        try:
                            await self._send_message(fallback_message)
                            self._record_send_time(message.chat_id)
                            continue
                        except Exception as retry_exc:
                            self.total_failed += 1
                            logging.error(
                                f"Failed to send fallback message to {message.chat_id}: {retry_exc}"
                            )
                            continue

                    self.total_failed += 1
                    logging.error(f"Failed to send queued message to {message.chat_id}: {exc}")

                except Exception:
                    self.total_failed += 1
                    logging.exception("Failed to send queued message to %s.", message.chat_id)

        finally:
            self.is_processing = False

    async def _wait_if_needed(self, chat_id: int | None = None) -> None:
        """Wait if we need to respect global and per-chat rate limits."""
        now = datetime.now(UTC)
        waits: list[float] = []

        if self.last_send_times:
            time_since_last = (now - self.last_send_times[-1]).total_seconds()
            if time_since_last < self.delay_between_messages:
                waits.append(self.delay_between_messages - time_since_last)

        if chat_id is not None:
            last_chat = self._chat_last_sent.get(chat_id)
            if last_chat is not None:
                time_since_chat = (now - last_chat).total_seconds()
                if time_since_chat < self.PER_CHAT_MIN_INTERVAL_SECONDS:
                    waits.append(self.PER_CHAT_MIN_INTERVAL_SECONDS - time_since_chat)

        if waits:
            await asyncio.sleep(max(waits))

    def _record_send_time(self, chat_id: int | None = None) -> None:
        """Track sent message timestamps and purge old entries for rate limiting."""
        now = datetime.now(UTC)
        self.last_send_times.append(now)
        self.total_sent += 1

        cutoff_time = now - timedelta(seconds=60)
        while self.last_send_times and self.last_send_times[0] < cutoff_time:
            self.last_send_times.popleft()

        if chat_id is not None:
            self._chat_last_sent[chat_id] = now
            chat_cutoff = now - timedelta(seconds=self.PER_CHAT_TTL_SECONDS)
            stale = [cid for cid, ts in self._chat_last_sent.items() if ts < chat_cutoff]
            for cid in stale:
                self._chat_last_sent.pop(cid, None)

    def _build_profile_link_fallback(
        self, message: QueuedMessage, exc: Exception
    ) -> QueuedMessage | None:
        """Create a fallback message without tg://user buttons when Telegram rejects them."""
        if not is_profile_link_error(exc):
            return None

        markup = message.kwargs.get("reply_markup")
        if markup is None:
            return None

        safe_markup = remove_profile_link_buttons(markup)
        fallback_kwargs = dict(message.kwargs)
        fallback_kwargs["reply_markup"] = safe_markup

        return QueuedMessage(
            chat_id=message.chat_id,
            method_name=message.method_name,
            kwargs=fallback_kwargs,
            callback=message.callback,
        )

    async def _send_message(self, message: QueuedMessage) -> Any:
        """Send a single message - to be implemented by subclass"""
        raise NotImplementedError("Subclass must implement _send_message")


class TelegramMessageQueue(MessageQueue):
    """Telegram-specific message queue"""

    def __init__(self, bot: Bot, messages_per_second: float, burst_size: int = 5):
        super().__init__(messages_per_second, burst_size)
        self.bot = bot

    async def _send_message(self, message: QueuedMessage) -> Any:
        """Send message using bot method"""
        method = getattr(self.bot, message.method_name)
        result = await method(chat_id=message.chat_id, **message.kwargs)

        # Call callback if provided
        if message.callback:
            await message.callback(result)

        return result


class MessageQueueManager:
    """Manager for different types of message queues"""

    def __init__(self, bot: Bot):
        self.bot = bot

        # Different queues for different types of chats
        self.group_queue = TelegramMessageQueue(
            bot=bot,
            messages_per_second=15 / 60,  # 15 messages per minute for groups
            burst_size=3,
        )

        self.user_queue = TelegramMessageQueue(
            bot=bot,
            messages_per_second=25,  # 25 messages per second for users
            burst_size=10,
        )

    def _is_group_chat(self, chat_id: int) -> bool:
        """Check if chat_id belongs to a group or channel"""
        return str(chat_id).startswith("-100")

    async def send_message(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_message call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_message", kwargs=kwargs)
        await queue.add_message(message)

    async def edit_message_text(self, chat_id: int, **kwargs: Any) -> None:
        """Queue an edit_message_text call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="edit_message_text", kwargs=kwargs)
        await queue.add_message(message)

    async def send_document(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_document call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_document", kwargs=kwargs)
        await queue.add_message(message)

    async def send_photo(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_photo call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_photo", kwargs=kwargs)
        await queue.add_message(message)

    async def send_video(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_video call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_video", kwargs=kwargs)
        await queue.add_message(message)

    async def send_animation(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_animation (GIF) call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_animation", kwargs=kwargs)
        await queue.add_message(message)

    async def send_audio(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_audio call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_audio", kwargs=kwargs)
        await queue.add_message(message)

    async def send_voice(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_voice call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_voice", kwargs=kwargs)
        await queue.add_message(message)

    async def send_sticker(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_sticker call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_sticker", kwargs=kwargs)
        await queue.add_message(message)

    async def send_video_note(self, chat_id: int, **kwargs: Any) -> None:
        """Queue a send_video_note call"""
        queue = self.group_queue if self._is_group_chat(chat_id) else self.user_queue
        message = QueuedMessage(chat_id=chat_id, method_name="send_video_note", kwargs=kwargs)
        await queue.add_message(message)

    async def answer_callback_query(self, callback_query_id: str, **kwargs: Any) -> None:
        """Send callback query answer immediately (not rate limited)"""
        await self.bot.answer_callback_query(callback_query_id, **kwargs)

    def get_queue_stats(self) -> dict[str, Any]:
        """Get statistics about queues"""
        return {
            "group_queue_size": len(self.group_queue.queue),
            "user_queue_size": len(self.user_queue.queue),
            "group_queue_processing": self.group_queue.is_processing,
            "user_queue_processing": self.user_queue.is_processing,
            "group_recent_sends": len(self.group_queue.last_send_times),
            "user_recent_sends": len(self.user_queue.last_send_times),
            "group_failed_messages": self.group_queue.total_failed,
            "user_failed_messages": self.user_queue.total_failed,
            "group_sent_messages": self.group_queue.total_sent,
            "user_sent_messages": self.user_queue.total_sent,
        }


# Global queue manager instance
_queue_manager: MessageQueueManager | None = None


def init_queue_manager(bot: Bot) -> MessageQueueManager:
    """Initialize global queue manager"""
    global _queue_manager
    _queue_manager = MessageQueueManager(bot)
    return _queue_manager


def get_queue_manager() -> MessageQueueManager | None:
    """Get global queue manager instance"""
    return _queue_manager
