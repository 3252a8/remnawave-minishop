import asyncio
from typing import cast
from unittest.mock import AsyncMock

from bot.services import support_presence
from config.settings import Settings
from tests.support.settings_stub import settings_stub


def test_support_typing_local_fallback_expires(monkeypatch):
    clock = [100.0]
    settings = cast(Settings, settings_stub(REDIS_URL=None))
    support_presence._local_typing_expiry.clear()
    monkeypatch.setattr(support_presence, "get_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(support_presence.time, "monotonic", lambda: clock[0])

    async def exercise() -> None:
        await support_presence.set_support_typing(settings, 42, "user", typing=True)

        assert await support_presence.is_support_typing(settings, 42, "user") is True
        clock[0] += support_presence.SUPPORT_TYPING_TTL_SECONDS + 0.1
        assert await support_presence.is_support_typing(settings, 42, "user") is False

    asyncio.run(exercise())


def test_support_typing_uses_redis_ttl_and_clears(monkeypatch):
    redis = AsyncMock()
    redis.get.return_value = "1"
    settings = cast(Settings, settings_stub(REDIS_URL="redis://example.test/0"))
    monkeypatch.setattr(support_presence, "get_redis", AsyncMock(return_value=redis))

    async def exercise() -> None:
        await support_presence.set_support_typing(settings, 7, "admin", typing=True)

        key = support_presence._presence_key(settings, 7, "admin")
        redis.set.assert_awaited_once_with(
            key,
            "1",
            ex=support_presence.SUPPORT_TYPING_TTL_SECONDS,
        )
        assert await support_presence.is_support_typing(settings, 7, "admin") is True

        await support_presence.set_support_typing(settings, 7, "admin", typing=False)
        redis.delete.assert_awaited_once_with(key)
        redis.get.side_effect = RuntimeError("redis unavailable")
        assert await support_presence.is_support_typing(settings, 7, "admin") is False

    asyncio.run(exercise())
