import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.services import panel_api_service
from bot.utils import config_link
from bot.utils.config_link import prepare_config_links
from bot.utils.ttl_cache import AsyncTTLCache


class AsyncTTLCacheSingleflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_redis_backed_cache_uses_local_singleflight_on_cold_miss(self):
        settings = SimpleNamespace(REDIS_URL="redis://example", REDIS_KEY_PREFIX="test")
        cache = AsyncTTLCache(ttl_seconds=60, settings=settings, namespace="bench")
        loader_calls = 0
        set_calls = 0

        async def loader():
            nonlocal loader_calls
            loader_calls += 1
            await asyncio.sleep(0.001)
            return {"ok": True}

        async def fake_get(settings, key):
            return None

        async def fake_set(settings, key, value, ttl):
            nonlocal set_calls
            set_calls += 1

        with (
            patch("bot.infra.redis.cache_get_json", new=fake_get),
            patch("bot.infra.redis.cache_set_json", new=fake_set),
        ):
            values = await asyncio.gather(*(cache.get_or_load("same", loader) for _ in range(100)))

        self.assertEqual(values, [{"ok": True}] * 100)
        self.assertEqual(loader_calls, 1)
        self.assertEqual(set_calls, 1)


class Crypt4LinkCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        config_link._CRYPT4_LINK_CACHES.clear()

    async def test_prepare_config_links_singleflights_same_crypt4_link(self):
        config_link._CRYPT4_LINK_CACHES.clear()
        settings = SimpleNamespace(
            CRYPT4_ENABLED=True,
            CRYPT4_REDIRECT_URL="",
            CRYPT4_LINK_CACHE_TTL_SECONDS=3600,
            PANEL_API_URL="https://panel.example.test/api",
            PANEL_API_KEY="key",
            USER_HWID_DEVICE_LIMIT=None,
        )
        encrypt_calls = 0

        async def fake_encrypt(self, raw_link):
            nonlocal encrypt_calls
            encrypt_calls += 1
            await asyncio.sleep(0.001)
            return "happ://crypt4/encrypted"

        async def fake_close(self):
            return None

        with (
            patch.object(panel_api_service.PanelApiService, "encrypt_happ_link", fake_encrypt),
            patch.object(panel_api_service.PanelApiService, "close_session", fake_close),
        ):
            values = await asyncio.gather(
                *(
                    prepare_config_links(settings, "https://panel.example.test/sub/user")
                    for _ in range(100)
                )
            )

        self.assertEqual(values, [("happ://crypt4/encrypted", "happ://crypt4/encrypted")] * 100)
        self.assertEqual(encrypt_calls, 1)


if __name__ == "__main__":
    unittest.main()
