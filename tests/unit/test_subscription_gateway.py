"""The public raw path must preserve bytes while enforcing the access boundary."""

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestServer, make_mocked_request

from bot.app.web.webapp import subscription_access
from bot.app.web.webapp.subscription_gateway import _representation
from bot.services.remnawave_subscription_source import (
    RemnawaveSubscriptionSource,
    SubscriptionTransportError,
    filter_client_headers,
    filter_panel_headers,
    panel_subscription_url,
)
from bot.services.subscription_delivery import (
    DeliveryRequest,
    DeliveryResult,
    SubscriptionDeliveryService,
)
from bot.utils import install_links
from tests.support.settings_stub import settings_stub


class SubscriptionGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_share_token_uses_current_short_uuid_not_local_subscription_uuid(self) -> None:
        class FakePanel:
            async def __aenter__(self):
                return self

            async def __aexit__(self, _type, _exc, _tb):
                return False

            async def get_user_by_uuid_lookup(self, _user_uuid):
                return {
                    "ok": True,
                    "user": {
                        "shortUuid": "current-short",
                        "subscriptionUrl": "https://panel.test/sub/current-short",
                    },
                }

        local = SimpleNamespace(
            panel_user_uuid="panel-user",
            panel_subscription_uuid="full-subscription-uuid",
        )
        issue = AsyncMock(return_value="a" * 32)
        with (
            patch.object(install_links, "install_guide_share_links_enabled", return_value=True),
            patch.object(install_links, "PanelApiService", return_value=FakePanel()),
            patch.object(install_links.subscription_dal, "ensure_install_share_token", issue),
        ):
            url = await install_links.ensure_user_install_guide_share_url(
                SimpleNamespace(),
                settings_stub(SUBSCRIPTION_MINI_APP_URL="https://shop.test/app"),
                1,
                local_subscription=local,
            )
        self.assertEqual(url, f"https://shop.test/s/{'a' * 32}")
        assert issue.await_args is not None
        self.assertEqual(issue.await_args.kwargs["panel_short_uuid"], "current-short")

    async def test_panel_side_rotation_invalidates_bound_public_token(self) -> None:
        class SessionFactory:
            def __call__(self):
                return self

            async def __aenter__(self):
                return object()

            async def __aexit__(self, _type, _exc, _tb):
                return False

        local = SimpleNamespace(
            panel_user_uuid="panel-user",
            install_share_panel_short_uuid="old-short",
            is_active=True,
            end_date=datetime.now(UTC) + timedelta(days=1),
        )
        panel = SimpleNamespace(
            get_user_by_uuid_lookup=AsyncMock(
                return_value={
                    "ok": True,
                    "user": {
                        "shortUuid": "new-short",
                        "subscriptionUrl": "https://panel.test/new-short",
                    },
                }
            )
        )
        with (
            patch.object(subscription_access, "get_session_factory", return_value=SessionFactory()),
            patch.object(subscription_access, "_panel_service_from_app", return_value=panel),
            patch.object(
                subscription_access.subscription_dal,
                "get_subscription_by_install_share_token",
                AsyncMock(return_value=local),
            ),
        ):
            result = await subscription_access.resolve_subscription_access(
                SimpleNamespace(app={}), "a" * 32
            )
        self.assertIsNone(result)

    def test_representation_and_url_contract(self) -> None:
        token = "a" * 32
        browser = make_mocked_request(
            "GET", f"/s/{token}", headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"}
        )
        client = make_mocked_request(
            "GET", f"/s/{token}", headers={"User-Agent": "sing-box/1.0", "Accept": "*/*"}
        )
        preview = make_mocked_request("GET", f"/s/{token}", headers={"User-Agent": "TelegramBot"})
        self.assertEqual(_representation(browser), "page")
        self.assertEqual(_representation(client), "subscription")
        self.assertEqual(_representation(preview), "page")
        self.assertEqual(
            panel_subscription_url("https://panel.test/prefix/api", "short-id", "json"),
            "https://panel.test/prefix/api/sub/short-id/json",
        )

    def test_header_filter_removes_secrets_and_connection_fields(self) -> None:
        filtered = filter_client_headers(
            {
                "User-Agent": "client",
                "X-Hwid": "device",
                "X-Policy": "A",
                "Authorization": "Bearer secret",
                "Cookie": "session=secret",
                "x-forwarded-for": "1.2.3.4",
                "Connection": "X-Policy",
                "X-Minishop-Edge-Token": "secret",
            }
        )
        self.assertEqual(filtered["X-Hwid"], "device")
        self.assertNotIn("X-Policy", filtered)
        self.assertNotIn("Authorization", filtered)
        self.assertNotIn("Cookie", filtered)
        self.assertNotIn("x-forwarded-for", filtered)
        panel = filter_panel_headers(
            {
                "Content-Type": "application/yaml",
                "X-Policy": "A",
                "Set-Cookie": "secret",
                "Content-Length": "3",
                "Connection": "X-Policy",
            }
        )
        self.assertEqual(panel, {"Content-Type": "application/yaml"})

    async def test_local_source_uses_delivery_contract_without_panel_binding(self) -> None:
        class LocalSource:
            async def fetch(self, binding: object, request: DeliveryRequest) -> DeliveryResult:
                self_binding = binding
                assert self_binding == "local-resource"
                return DeliveryResult(200, {"Content-Type": "application/json"}, b'{"ok":1}')

        result = await SubscriptionDeliveryService(LocalSource()).deliver(
            "local-resource", DeliveryRequest(None, {"User-Agent": "client"}, "127.0.0.1")
        )
        self.assertEqual(result.body, b'{"ok":1}')

    async def test_remnawave_adapter_preserves_binary_body_and_safe_headers(self) -> None:
        seen: dict[str, str] = {}

        async def subscription(request: web.Request) -> web.Response:
            seen.update(request.headers)
            return web.Response(
                status=200,
                body=b"\x00\xff\nraw",
                headers={
                    "Content-Type": "application/octet-stream",
                    "subscription-userinfo": "upload=1",
                    "x-hwid-limit": "2",
                    "X-Policy": "allowed",
                    "Set-Cookie": "secret",
                },
            )

        app = web.Application()
        app.router.add_get("/prefix/api/sub/{short_uuid}", subscription)
        async with TestServer(app) as server:
            settings = settings_stub(PANEL_API_URL=str(server.make_url("/prefix/api")))
            result = await RemnawaveSubscriptionSource(settings).fetch(
                SimpleNamespace(panel_short_uuid="short-id"),
                DeliveryRequest(
                    None,
                    {
                        "User-Agent": "happ/1.0",
                        "x-hwid": "device-a",
                        "X-Policy": "present",
                        "Authorization": "Bearer secret",
                    },
                    "192.0.2.2",
                ),
            )
        self.assertEqual(result.body, b"\x00\xff\nraw")
        self.assertEqual(result.headers["subscription-userinfo"], "upload=1")
        self.assertNotIn("Set-Cookie", result.headers)
        self.assertEqual(seen["x-hwid"], "device-a")
        self.assertEqual(seen["X-Policy"], "present")
        self.assertEqual(seen["x-remnawave-real-ip"], "192.0.2.2")
        self.assertNotIn("Authorization", seen)

    async def test_html_challenge_is_an_upstream_error(self) -> None:
        async def challenge(_request: web.Request) -> web.Response:
            return web.Response(text="<html>login</html>", content_type="text/html")

        app = web.Application()
        app.router.add_get("/api/sub/{short_uuid}", challenge)
        async with TestServer(app) as server:
            settings = settings_stub(PANEL_API_URL=str(server.make_url("/api")))
            with self.assertRaises(SubscriptionTransportError) as failure:
                await RemnawaveSubscriptionSource(settings).fetch(
                    SimpleNamespace(panel_short_uuid="short-id"),
                    DeliveryRequest(None, {"User-Agent": "happ"}, "192.0.2.2"),
                )
        self.assertEqual(failure.exception.status, 502)
