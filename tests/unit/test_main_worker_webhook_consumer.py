import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main_worker

from bot.infra.webhook_queue import ClaimedWebhookEvent


class WebhookConsumerTests(unittest.IsolatedAsyncioTestCase):
    async def test_acknowledges_only_after_handler_completes(self) -> None:
        claimed = ClaimedWebhookEvent(
            event={"provider": "test", "event_id": "evt-1", "payload": {"value": 42}},
            raw='{"provider":"test"}',
        )
        handler = AsyncMock()
        acknowledge = AsyncMock(return_value=True)
        pop_calls = 0

        async def pop_once(_settings):
            nonlocal pop_calls
            pop_calls += 1
            if pop_calls == 1:
                return claimed
            raise asyncio.CancelledError

        settings = SimpleNamespace(
            WEBHOOK_QUEUE_MAX_ATTEMPTS=5,
            WEBHOOK_QUEUE_RETRY_BASE_SECONDS=0,
            WEBHOOK_QUEUE_RETRY_MAX_SECONDS=0,
        )
        ctx = SimpleNamespace(settings=settings, error_reporter=None)
        with (
            patch.object(main_worker, "pop_webhook_event", pop_once),
            patch.object(main_worker, "acknowledge_webhook_event", acknowledge),
            patch.object(main_worker, "webhook_queue_depth", AsyncMock(return_value=0)),
            self.assertRaises(asyncio.CancelledError),
        ):
            await main_worker._webhook_consumer(ctx, {"test": handler})

        handler.assert_awaited_once_with(ctx, {"value": 42})
        acknowledge.assert_awaited_once_with(ctx.settings, claimed)

    async def test_requeues_failed_event_without_acknowledging(self) -> None:
        claimed = ClaimedWebhookEvent(
            event={"provider": "test", "event_id": "evt-2", "payload": {}},
            raw='{"provider":"test"}',
        )
        handler = AsyncMock(side_effect=RuntimeError("temporary"))
        retry = AsyncMock(return_value=True)
        acknowledge = AsyncMock(return_value=True)
        pop_calls = 0

        async def pop_once(_settings):
            nonlocal pop_calls
            pop_calls += 1
            if pop_calls == 1:
                return claimed
            raise asyncio.CancelledError

        settings = SimpleNamespace(
            WEBHOOK_QUEUE_MAX_ATTEMPTS=5,
            WEBHOOK_QUEUE_RETRY_BASE_SECONDS=0,
            WEBHOOK_QUEUE_RETRY_MAX_SECONDS=0,
        )
        ctx = SimpleNamespace(settings=settings, error_reporter=AsyncMock())
        with (
            patch.object(main_worker, "pop_webhook_event", pop_once),
            patch.object(main_worker, "retry_webhook_event", retry),
            patch.object(main_worker, "acknowledge_webhook_event", acknowledge),
            patch.object(main_worker, "webhook_queue_depth", AsyncMock(return_value=0)),
            self.assertRaises(asyncio.CancelledError),
        ):
            await main_worker._webhook_consumer(ctx, {"test": handler})

        acknowledge.assert_not_awaited()
        retry.assert_awaited_once_with(settings, claimed, delivery_attempts=1)

    async def test_dead_letters_event_after_last_attempt(self) -> None:
        claimed = ClaimedWebhookEvent(
            event={
                "provider": "test",
                "event_id": "evt-3",
                "payload": {},
                "delivery_attempts": 4,
            },
            raw='{"provider":"test"}',
        )
        error = RuntimeError("permanent")
        handler = AsyncMock(side_effect=error)
        dead_letter = AsyncMock(return_value=True)
        pop_calls = 0

        async def pop_once(_settings):
            nonlocal pop_calls
            pop_calls += 1
            if pop_calls == 1:
                return claimed
            raise asyncio.CancelledError

        settings = SimpleNamespace(
            WEBHOOK_QUEUE_MAX_ATTEMPTS=5,
            WEBHOOK_QUEUE_RETRY_BASE_SECONDS=0,
            WEBHOOK_QUEUE_RETRY_MAX_SECONDS=0,
        )
        ctx = SimpleNamespace(settings=settings, error_reporter=AsyncMock())
        with (
            patch.object(main_worker, "pop_webhook_event", pop_once),
            patch.object(main_worker, "dead_letter_webhook_event", dead_letter),
            patch.object(main_worker, "webhook_queue_depth", AsyncMock(return_value=0)),
            self.assertRaises(asyncio.CancelledError),
        ):
            await main_worker._webhook_consumer(ctx, {"test": handler})

        dead_letter.assert_awaited_once_with(
            settings,
            claimed,
            delivery_attempts=5,
            error=error,
        )
