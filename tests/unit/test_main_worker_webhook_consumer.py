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

        ctx = SimpleNamespace(settings=SimpleNamespace(), error_reporter=None)
        with (
            patch.object(main_worker, "pop_webhook_event", pop_once),
            patch.object(main_worker, "acknowledge_webhook_event", acknowledge),
            patch.object(main_worker, "webhook_queue_depth", AsyncMock(return_value=0)),
            self.assertRaises(asyncio.CancelledError),
        ):
            await main_worker._webhook_consumer(ctx, {"test": handler})

        handler.assert_awaited_once_with(ctx, {"value": 42})
        acknowledge.assert_awaited_once_with(ctx.settings, claimed)
