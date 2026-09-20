import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import account as account_module


class WebAppProfileCacheTests(IsolatedAsyncioTestCase):
    async def test_me_route_tariff_access_bypasses_shared_user_cache(self):
        settings = SimpleNamespace(WEBAPP_ME_CACHE_TTL_SECONDS=60)
        request = SimpleNamespace(
            app={"settings": settings},
            query={},
            headers={"X-Tariff-Access-Code": "ab" * 16},
            match_info={},
        )

        with (
            patch.object(account_module, "_require_user_id", return_value=42),
            patch.object(
                account_module, "_invalidate_webapp_user_caches", AsyncMock()
            ) as invalidate,
            patch.object(
                account_module,
                "_build_user_payload",
                AsyncMock(return_value={"plans": [{"tariff_key": "private"}]}),
            ) as build_payload,
            patch.object(account_module, "webapp_cached_user_payload", AsyncMock()) as cached,
        ):
            response = await account_module.me_route(request)

        invalidate.assert_not_awaited()
        build_payload.assert_awaited_once_with(request, 42)
        cached.assert_not_awaited()
        self.assertEqual(json.loads(response.text)["plans"], [{"tariff_key": "private"}])

    async def test_me_route_fresh_bypasses_cache_and_invalidates_payload(self):
        settings = SimpleNamespace(WEBAPP_ME_CACHE_TTL_SECONDS=60)
        request = SimpleNamespace(app={"settings": settings}, query={"fresh": "1"})

        with (
            patch.object(account_module, "_require_user_id", return_value=42),
            patch.object(
                account_module,
                "_invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate_cache,
            patch.object(
                account_module,
                "_build_user_payload",
                AsyncMock(return_value={"user": {"id": 42}, "subscription": {"active": True}}),
            ) as build_payload,
            patch.object(
                account_module,
                "webapp_cached_user_payload",
                AsyncMock(),
            ) as cached_payload,
        ):
            response = await account_module.me_route(request)

        invalidate_cache.assert_awaited_once_with(settings, 42)
        build_payload.assert_awaited_once_with(request, 42)
        cached_payload.assert_not_awaited()
        self.assertEqual(
            json.loads(response.text),
            {"ok": True, "user": {"id": 42}, "subscription": {"active": True}},
        )
