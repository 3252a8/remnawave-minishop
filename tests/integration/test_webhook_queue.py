import asyncio
import json
import time
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from bot.infra import redis as redis_infra
from bot.infra import webhook_queue


class FakeRedis:
    """Minimal async stand-in for redis.asyncio.Redis used by tests."""

    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._ttl: dict[str, float] = {}
        self._lists: dict[str, list[str]] = {}

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        self._expire_if_due(key)
        if nx and key in self._kv:
            return False
        self._kv[key] = value
        if ex is not None:
            self._ttl[key] = time.monotonic() + ex
        else:
            self._ttl.pop(key, None)
        return True

    async def get(self, key: str) -> str | None:
        self._expire_if_due(key)
        return self._kv.get(key)

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self._kv:
                self._kv.pop(key, None)
                self._ttl.pop(key, None)
                removed += 1
            if key in self._lists:
                self._lists.pop(key, None)
                removed += 1
        return removed

    async def lpush(self, key: str, *values: str) -> int:
        bucket = self._lists.setdefault(key, [])
        for value in values:
            bucket.insert(0, value)
        return len(bucket)

    # Keep `timeout` to mirror redis.asyncio.Redis.brpop used by the queue code.
    async def brpop(self, key: str, timeout: int = 0) -> tuple[str, str] | None:  # noqa: ASYNC109
        bucket = self._lists.get(key)
        if bucket:
            return key, bucket.pop()
        # In real Redis, brpop blocks. Tests never use the timeout path.
        return None

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))

    async def eval(self, script: str, numkeys: int, *args: Any) -> int:
        # The only Lua used by the code base releases redis_lock atomically.
        keys = args[:numkeys]
        argv = args[numkeys:]
        if keys and argv and self._kv.get(keys[0]) == argv[0]:
            self._kv.pop(keys[0], None)
            self._ttl.pop(keys[0], None)
            return 1
        return 0

    async def aclose(self) -> None:  # pragma: no cover - close path
        self._kv.clear()
        self._ttl.clear()
        self._lists.clear()

    def _expire_if_due(self, key: str) -> None:
        expires_at = self._ttl.get(key)
        if expires_at is not None and time.monotonic() >= expires_at:
            self._kv.pop(key, None)
            self._ttl.pop(key, None)


def _make_settings(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "REDIS_URL": "redis://redis:6379/0",
        "REDIS_KEY_PREFIX": "remnawave-tg-shop",
        "WEBHOOK_QUEUE_NAME": "webhook-events",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class RedisKeyTests(unittest.TestCase):
    def test_redis_key_joins_prefix_and_parts(self):
        settings = _make_settings(REDIS_KEY_PREFIX="shop")
        self.assertEqual(redis_infra.redis_key(settings, "queue", "events"), "shop:queue:events")

    def test_redis_key_filters_empty_or_colon_only_parts(self):
        settings = _make_settings(REDIS_KEY_PREFIX="shop")
        # Empty / colon-only parts are dropped; numeric and string parts coexist.
        self.assertEqual(
            redis_infra.redis_key(settings, "lock", "", ":", "panel-sync", 42),
            "shop:lock:panel-sync:42",
        )

    def test_redis_key_strips_leading_trailing_colons(self):
        settings = _make_settings(REDIS_KEY_PREFIX=":shop:")
        self.assertEqual(
            redis_infra.redis_key(settings, ":webhook:", "seen"),
            "shop:webhook:seen",
        )


class WebhookQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.fake = FakeRedis()

        async def fake_get_redis(_settings):
            return self.fake

        self._patcher = patch.object(webhook_queue, "get_redis", fake_get_redis)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    async def test_enqueue_returns_false_when_redis_unavailable(self):
        async def no_redis(_settings):
            return None

        with patch.object(webhook_queue, "get_redis", no_redis):
            ok = await webhook_queue.enqueue_webhook_event(
                _make_settings(), "yookassa", {"id": "p_1"}
            )
        self.assertFalse(ok)

    async def test_enqueue_writes_payload_and_increments_depth(self):
        settings = _make_settings()
        ok = await webhook_queue.enqueue_webhook_event(
            settings,
            "yookassa",
            {"id": "p_42", "amount": "100"},
            event_id="payment.succeeded:p_42",
        )
        self.assertTrue(ok)

        depth = await webhook_queue.webhook_queue_depth(settings)
        self.assertEqual(depth, 1)

        popped = await webhook_queue.pop_webhook_event(settings)
        assert popped is not None
        self.assertEqual(popped["provider"], "yookassa")
        self.assertEqual(popped["event_id"], "payment.succeeded:p_42")
        self.assertEqual(popped["payload"], {"id": "p_42", "amount": "100"})
        self.assertIsInstance(popped["enqueued_at"], (int, float))

    async def test_enqueue_dedupes_repeated_event_ids(self):
        settings = _make_settings()
        first = await webhook_queue.enqueue_webhook_event(
            settings,
            "panel",
            {"event": "user.expired", "user": {"telegramId": 1}},
            event_id="user.expired:1",
        )
        second = await webhook_queue.enqueue_webhook_event(
            settings,
            "panel",
            {"event": "user.expired", "user": {"telegramId": 1}},
            event_id="user.expired:1",
        )
        self.assertTrue(first)
        # Dedupe path is treated as a success — the event was already accepted.
        self.assertTrue(second)
        self.assertEqual(await webhook_queue.webhook_queue_depth(settings), 1)

    async def test_pop_returns_none_when_queue_empty(self):
        settings = _make_settings()
        self.assertIsNone(await webhook_queue.pop_webhook_event(settings))

    async def test_pop_skips_invalid_payload(self):
        settings = _make_settings()
        await self.fake.lpush(webhook_queue.webhook_queue_key(settings), "not-json")
        result = await webhook_queue.pop_webhook_event(settings)
        self.assertIsNone(result)

    async def test_queue_key_uses_prefix_and_queue_name(self):
        settings = _make_settings(REDIS_KEY_PREFIX="shop", WEBHOOK_QUEUE_NAME="custom-q")
        self.assertEqual(webhook_queue.webhook_queue_key(settings), "shop:queue:custom-q")

    async def test_enqueue_serializes_unicode_without_escaping(self):
        settings = _make_settings()
        await webhook_queue.enqueue_webhook_event(
            settings, "panel", {"name": "Юзер", "id": 7}, event_id="u:7"
        )
        # Raw payload in Redis preserves Cyrillic without \uXXXX escapes.
        raw = self.fake._lists[webhook_queue.webhook_queue_key(settings)][0]
        self.assertIn("Юзер", raw)
        parsed = json.loads(raw)
        self.assertEqual(parsed["payload"]["name"], "Юзер")


class RedisLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_lock_is_noop_when_redis_unavailable(self):
        async def no_redis(_settings):
            return None

        with patch.object(redis_infra, "get_redis", no_redis):
            async with redis_infra.redis_lock(
                _make_settings(), "panel-sync", ttl_seconds=30
            ) as acquired:
                self.assertTrue(acquired)

    async def test_lock_excludes_concurrent_holders_and_releases_on_exit(self):
        fake = FakeRedis()

        async def fake_get_redis(_settings):
            return fake

        with patch.object(redis_infra, "get_redis", fake_get_redis):
            settings = _make_settings()
            async with redis_infra.redis_lock(settings, "panel-sync", ttl_seconds=30) as first:
                self.assertTrue(first)
                async with redis_infra.redis_lock(settings, "panel-sync", ttl_seconds=30) as second:
                    self.assertFalse(second)
            # After exit, the lock is released and can be re-acquired.
            async with redis_infra.redis_lock(settings, "panel-sync", ttl_seconds=30) as again:
                self.assertTrue(again)


class SleepOrStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_promptly_when_event_set(self):
        event = asyncio.Event()
        event.set()
        await redis_infra.sleep_or_stop(event, seconds=5)  # would hang on a bug

    async def test_times_out_when_event_not_set(self):
        event = asyncio.Event()
        # Tiny timeout keeps the test fast; the function should not raise on timeout.
        await redis_infra.sleep_or_stop(event, seconds=0.01)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
