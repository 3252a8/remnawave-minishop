import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import cache_helpers


class WebappRedisCacheInvalidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalidate_webapp_user_caches_deletes_me_and_devices_keys(self):
        settings = SimpleNamespace(REDIS_URL="redis://redis:6379/0", REDIS_KEY_PREFIX="shop")
        deleted = []

        async def fake_delete(_settings, *keys):
            deleted.extend(keys)

        with patch.object(cache_helpers, "cache_delete", fake_delete):
            await cache_helpers.invalidate_webapp_user_caches(
                settings,
                42,
                "42",
                99,
                include_devices=True,
            )

        self.assertEqual(
            deleted,
            [
                "shop:cache:webapp:me:42",
                "shop:cache:webapp:devices:42",
                "shop:cache:webapp:me:99",
                "shop:cache:webapp:devices:99",
            ],
        )

    async def test_invalidate_all_webapp_user_payloads_deletes_namespace_patterns(self):
        settings = SimpleNamespace(REDIS_URL="redis://redis:6379/0", REDIS_KEY_PREFIX="shop")
        patterns = []

        async def fake_delete_pattern(_settings, pattern):
            patterns.append(pattern)
            return 0

        with patch.object(cache_helpers, "cache_delete_pattern", fake_delete_pattern):
            await cache_helpers.invalidate_all_webapp_user_payloads(settings, include_devices=True)

        self.assertEqual(
            patterns,
            [
                "shop:cache:webapp:me:*",
                "shop:cache:webapp:devices:*",
            ],
        )


if __name__ == "__main__":
    unittest.main()
