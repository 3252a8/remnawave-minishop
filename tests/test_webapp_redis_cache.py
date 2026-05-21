import unittest
from types import SimpleNamespace
from unittest.mock import patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import common as common_module


class WebappRedisCacheInvalidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalidate_webapp_user_caches_deletes_me_and_devices_keys(self):
        settings = SimpleNamespace(REDIS_URL="redis://redis:6379/0", REDIS_KEY_PREFIX="shop")
        deleted = []

        async def fake_delete(_settings, *keys):
            deleted.extend(keys)

        with patch.object(common_module, "cache_delete", fake_delete):
            await common_module._invalidate_webapp_user_caches(
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


if __name__ == "__main__":
    unittest.main()
