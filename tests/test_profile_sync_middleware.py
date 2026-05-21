import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.middlewares import profile_sync as profile_sync_module
from bot.middlewares.profile_sync import ProfileSyncMiddleware


class ProfileSyncMiddlewareCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        profile_sync_module._LOCAL_PROFILE_SYNC_CHECKS.clear()

    async def asyncTearDown(self):
        profile_sync_module._LOCAL_PROFILE_SYNC_CHECKS.clear()

    def _settings(self):
        return SimpleNamespace(
            PROFILE_SYNC_CACHE_TTL_SECONDS=900,
            REDIS_URL="redis://redis:6379/0",
            REDIS_KEY_PREFIX="shop",
        )

    async def test_profile_sync_skips_repeated_user_checks_inside_ttl(self):
        middleware = ProfileSyncMiddleware()
        handler = AsyncMock(return_value="ok")
        event = SimpleNamespace()
        tg_user = SimpleNamespace(
            id=42,
            username="alice",
            first_name="Alice",
            last_name="Smith",
        )
        db_user = SimpleNamespace(
            user_id=42,
            telegram_id=42,
            username="alice",
            first_name="Alice",
            last_name="Smith",
            email=None,
            panel_user_uuid=None,
        )
        cache_store = {}

        async def fake_get(_settings, key):
            return cache_store.get(key)

        async def fake_set(_settings, key, value, ttl):
            cache_store[key] = value

        data = {
            "session": AsyncMock(),
            "event_from_user": tg_user,
            "settings": self._settings(),
        }
        with (
            patch.object(profile_sync_module, "cache_get_json", fake_get),
            patch.object(profile_sync_module, "cache_set_json", fake_set),
            patch.object(
                profile_sync_module.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=db_user),
            ) as get_user,
        ):
            first = await middleware(handler, event, data)
            second = await middleware(handler, event, data)

        self.assertEqual(first, "ok")
        self.assertEqual(second, "ok")
        get_user.assert_awaited_once()
        self.assertEqual(handler.await_count, 2)


if __name__ == "__main__":
    unittest.main()
