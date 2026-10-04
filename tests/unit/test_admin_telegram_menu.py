from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web

from bot.app.web import session as session_module
from bot.app.web.admin_api_impl import telegram_emoji, telegram_menu
from bot.app.web.context import I18N, SETTINGS
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from tests.support.settings_stub import settings_stub


class _Request(dict):
    def __init__(self, app):
        super().__init__()
        self.app = app

    async def json(self):
        return {}


def make_request(monkeypatch, payload=None, *, admin=False):
    app = web.Application()
    app[SETTINGS] = Settings(_env_file=None, POSTGRES_USER="test", POSTGRES_PASSWORD="test")
    app[I18N] = JsonI18n("locales", default="en")
    request = _Request(app)
    request["admin_authorized"] = admin
    monkeypatch.setattr(request, "json", AsyncMock(return_value=payload or {}))
    monkeypatch.setattr(session_module, "extract_authenticated_user_id", lambda _request: 42)
    monkeypatch.setattr(telegram_menu, "current_settings", AsyncMock(return_value=app[SETTINGS]))
    return request


@pytest.mark.parametrize(
    "handler",
    [
        telegram_menu.admin_telegram_menu_route,
        telegram_menu.admin_telegram_menu_save_route,
        telegram_menu.admin_telegram_menu_preview_route,
        telegram_menu.admin_telegram_menu_test_route,
        telegram_emoji.admin_telegram_emoji_library_route,
        telegram_emoji.admin_telegram_emoji_add_route,
        telegram_emoji.admin_telegram_emoji_remove_route,
        telegram_emoji.admin_telegram_emoji_refresh_route,
        telegram_emoji.admin_telegram_emoji_catalog_route,
        telegram_emoji.admin_telegram_emoji_media_route,
    ],
)
def test_all_telegram_design_endpoints_require_admin_auth(handler, monkeypatch) -> None:
    request = make_request(monkeypatch)
    with pytest.raises(web.HTTPForbidden):
        asyncio.run(handler(request))
    monkeypatch.setattr(session_module, "extract_authenticated_user_id", lambda _request: None)
    with pytest.raises(web.HTTPUnauthorized):
        asyncio.run(handler(request))


def test_color_configuration_and_preview_work_without_a_telegram_bot(monkeypatch) -> None:
    request = make_request(monkeypatch, admin=True)
    response = asyncio.run(telegram_menu.admin_telegram_menu_route(request))
    config = json.loads(response.text)
    assert config["ok"] is True
    assert config["capabilities"]["icon"]["state"] == "unknown"
    assert {item["code"] for item in config["languages"]} >= {"ru", "en"}
    monkeypatch.setattr(
        request,
        "json",
        AsyncMock(
            return_value={
                "appearance": {"buttons": {"personal_account": {"style": "primary"}}},
                "language": "en",
                "screen": "main",
                "scenario": "new",
            }
        ),
    )
    preview = json.loads(asyncio.run(telegram_menu.admin_telegram_menu_preview_route(request)).text)
    assert preview["ok"] is True
    account = next(
        button for row in preview["rows"] for button in row if button["id"] == "personal_account"
    )
    assert account["style"] == "primary"
    assert json.loads(request.app[SETTINGS].TELEGRAM_MENU_APPEARANCE_JSON)["buttons"] == {}


def test_saving_a_stale_revision_does_not_write_or_require_telegram(monkeypatch) -> None:
    request = make_request(
        monkeypatch, {"appearance": {"buttons": {}}, "expected_revision": "0" * 64}, admin=True
    )
    persist = AsyncMock()
    monkeypatch.setattr(telegram_menu, "persist_setting", persist)
    response = asyncio.run(telegram_menu.admin_telegram_menu_save_route(request))
    assert response.status == 409
    assert json.loads(response.text)["error"] == "telegram_menu_conflict"
    persist.assert_not_awaited()


def test_test_message_cannot_choose_arbitrary_recipient_or_unlinked_admin(monkeypatch) -> None:
    body = {"appearance": {"buttons": {}}, "language": "en", "chat_id": 999}
    request = make_request(monkeypatch, body, admin=True)
    with pytest.raises(web.HTTPBadRequest):
        asyncio.run(telegram_menu.admin_telegram_menu_test_route(request))
    del body["chat_id"]
    response = asyncio.run(telegram_menu.admin_telegram_menu_test_route(request))
    assert response.status == 400
    assert json.loads(response.text)["error"] == "telegram_menu_test_telegram_required"


class TelegramEmojiResourceQuotaTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_emoji_palettes_do_not_consume_account_api_quota(self):
        from aiohttp.test_utils import TestClient, TestServer

        from bot.app.web.webapp import rate_limits, resource_middleware

        async def handler(request):
            return web.json_response({"ok": True})

        settings = settings_stub(
            REDIS_URL="",
            WEBAPP_RATE_LIMIT_MAX_REQUESTS=30,
            WEBAPP_RATE_LIMIT_TTL_SECONDS=60,
            trusted_proxies=[],
        )
        app = web.Application(middlewares=[resource_middleware.api_resource_middleware])
        app.router.add_get("/api/admin/telegram-emoji/media/{emoji_id}", handler)
        app.router.add_get("/api/admin/users", handler)
        with (
            patch.object(resource_middleware, "get_settings", return_value=settings),
            patch.object(resource_middleware, "extract_authenticated_user_id", return_value=42),
            patch.object(rate_limits, "get_settings", return_value=settings),
            patch.object(rate_limits, "get_redis", AsyncMock(return_value=None)),
            patch.object(rate_limits, "get_webapp_rate_limit_buckets", return_value={}),
            patch.object(rate_limits, "get_webapp_rate_limit_lock", return_value=asyncio.Lock()),
        ):
            async with TestClient(TestServer(app)) as client:
                # Two complete 96-emoji views must fit without blocking normal
                # account requests, even when they share one session and IP.
                for _view in range(2):
                    for emoji_id in range(1, 97):
                        response = await client.get(f"/api/admin/telegram-emoji/media/{emoji_id}")
                        self.assertEqual(response.status, 200)
                for _request in range(120):
                    response = await client.get("/api/admin/users")
                    self.assertEqual(response.status, 200)
                blocked = await client.get("/api/admin/users")
                self.assertEqual(blocked.status, 429)
                self.assertGreaterEqual(int(blocked.headers["Retry-After"]), 1)

    async def test_emoji_media_quota_is_bounded_and_only_applies_to_valid_authenticated_reads(self):
        from aiohttp.test_utils import TestClient, TestServer

        from bot.app.web.webapp import rate_limits, resource_middleware

        async def handler(request):
            return web.json_response({"ok": True})

        settings = settings_stub(
            REDIS_URL="",
            WEBAPP_RATE_LIMIT_MAX_REQUESTS=1,
            WEBAPP_RATE_LIMIT_TTL_SECONDS=60,
            trusted_proxies=[],
        )
        prefix = "/api/admin/telegram-emoji/media/"
        cases = (
            ("GET", prefix + "5368651601797984900", 42, 16),
            ("GET", prefix + "5368651601797984900", None, 8),
            ("POST", prefix + "5368651601797984900", 42, 4),
            ("GET", prefix + "0", 42, 4),
            ("GET", prefix + "1" * 21, 42, 4),
            ("GET", prefix + "123/extra", 42, 4),
        )
        for method, path, user_id, allowed in cases:
            with self.subTest(method=method, path=path, user_id=user_id):
                app = web.Application(middlewares=[resource_middleware.api_resource_middleware])
                app.router.add_route("*", "/api/{path:.*}", handler)
                with (
                    patch.object(resource_middleware, "get_settings", return_value=settings),
                    patch.object(
                        resource_middleware, "extract_authenticated_user_id", return_value=user_id
                    ),
                    patch.object(rate_limits, "get_settings", return_value=settings),
                    patch.object(rate_limits, "get_redis", AsyncMock(return_value=None)),
                    patch.object(rate_limits, "get_webapp_rate_limit_buckets", return_value={}),
                    patch.object(
                        rate_limits, "get_webapp_rate_limit_lock", return_value=asyncio.Lock()
                    ),
                ):
                    async with TestClient(TestServer(app)) as client:
                        for _request in range(allowed):
                            response = await client.request(method, path)
                            self.assertEqual(response.status, 200)
                        blocked = await client.request(method, path)
                        self.assertEqual(blocked.status, 429)
                        self.assertGreaterEqual(int(blocked.headers["Retry-After"]), 1)
