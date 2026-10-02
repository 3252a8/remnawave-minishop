"""The public raw path must preserve bytes while enforcing the access boundary."""

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer, make_mocked_request

from bot.app.web.context import SETTINGS
from bot.app.web.webapp import subscription_access, subscription_gateway
from bot.app.web.webapp.subscription_gateway import _representation
from bot.services.remnawave_subscription_source import (
    _MAX_PANEL_HEADER_BYTES,
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

    async def test_happ_receives_raw_subscription_even_when_html_is_accepted(self) -> None:
        subscription_body = b"trojan://example.test#node\n" * 400
        upstream_user_agents: list[str] = []

        async def panel_subscription(request: web.Request) -> web.Response:
            upstream_user_agents.append(request.headers["User-Agent"])
            return web.Response(body=subscription_body, content_type="text/plain")

        panel_app = web.Application()
        panel_app.router.add_get("/api/sub/{short_uuid}", panel_subscription)
        async with TestServer(panel_app) as panel_server:
            settings = settings_stub(
                PANEL_API_URL=str(panel_server.make_url("/api")),
                SUBSCRIPTION_GATEWAY_ENABLED=True,
            )
            shop_app = web.Application()
            shop_app[SETTINGS] = settings
            shop_app[subscription_gateway._DELIVERY_SEMAPHORE_KEY] = asyncio.Semaphore(64)
            shop_app.router.add_get(
                "/s/{share_token}", subscription_gateway.subscription_gateway_route
            )
            with (
                patch.object(
                    subscription_gateway,
                    "resolve_subscription_access",
                    AsyncMock(return_value=SimpleNamespace(panel_short_uuid="short-id")),
                ),
                patch.object(subscription_gateway, "_rate_limited", AsyncMock(return_value=None)),
            ):
                async with (
                    TestServer(shop_app) as shop_server,
                    ClientSession() as client,
                    client.get(
                        shop_server.make_url("/s/" + "a" * 32),
                        headers={
                            "user-agent": "Happ/4.2.1/Windows/2609041405606",
                            "Accept": "text/html, */*",
                        },
                    ) as response,
                ):
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.content_type, "text/plain")
                    self.assertEqual(await response.read(), subscription_body)
        self.assertEqual(upstream_user_agents, ["Happ/4.2.1/Windows/2609041405606"])

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
                        "x-hwid": "device-123456",
                        "x-device-os": "Windows",
                        "x-ver-os": "11",
                        "x-device-model": "Desktop",
                        "x-remnawave-real-ip": "198.51.100.99",
                        "X-Policy": "present",
                        "Authorization": "Bearer secret",
                    },
                    "192.0.2.2",
                ),
            )
        self.assertEqual(result.body, b"\x00\xff\nraw")
        self.assertEqual(result.headers["subscription-userinfo"], "upload=1")
        self.assertNotIn("Set-Cookie", result.headers)
        self.assertEqual(seen["x-hwid"], "device-123456")
        self.assertEqual(seen["X-Policy"], "present")
        self.assertEqual(seen["x-remnawave-real-ip"], "192.0.2.2")
        self.assertEqual(seen["x-device-os"], "Windows")
        self.assertEqual(seen["x-ver-os"], "11")
        self.assertEqual(seen["x-device-model"], "Desktop")
        self.assertNotIn("Authorization", seen)

    async def test_large_client_settings_survive_the_public_gateway(self) -> None:
        client_settings = "a" * (48 * 1024)

        async def subscription(_request: web.Request) -> web.Response:
            return web.Response(
                body=b"raw profile",
                headers={
                    "X-Client-Settings": client_settings,
                    "x-hwid-limit": "2",
                    "Profile-Web-Page-Url": "https://panel.test/default",
                },
            )

        panel_app = web.Application()
        panel_app.router.add_get("/api/sub/{short_uuid}", subscription)
        async with TestServer(panel_app) as panel_server:
            shop_app = web.Application()
            shop_app[SETTINGS] = settings_stub(
                PANEL_API_URL=str(panel_server.make_url("/api")),
                SUBSCRIPTION_GATEWAY_ENABLED=True,
                SUBSCRIPTION_MINI_APP_URL="https://shop.test",
                SUBSCRIPTION_GATEWAY_REWRITE_PROFILE_PAGE_URL=True,
            )
            shop_app[subscription_gateway._DELIVERY_SEMAPHORE_KEY] = asyncio.Semaphore(64)
            shop_app.router.add_get(
                "/s/{share_token}", subscription_gateway.subscription_gateway_route
            )
            with (
                patch.object(
                    subscription_gateway,
                    "resolve_subscription_access",
                    AsyncMock(return_value=SimpleNamespace(panel_short_uuid="short-id")),
                ),
                patch.object(subscription_gateway, "_rate_limited", AsyncMock(return_value=None)),
            ):
                async with (
                    TestServer(shop_app) as shop_server,
                    ClientSession(max_field_size=128 * 1024) as client,
                    client.get(
                        shop_server.make_url("/s/" + "a" * 32),
                        headers={"user-agent": "Happ/1.0"},
                    ) as response,
                ):
                    self.assertEqual(response.status, 200)
                    self.assertEqual(await response.read(), b"raw profile")
                    self.assertEqual(response.headers["X-Client-Settings"], client_settings)
                    self.assertEqual(response.headers["x-hwid-limit"], "2")
                    self.assertEqual(
                        response.headers.getall("profile-web-page-url"),
                        ["https://shop.test/s/" + "a" * 32 + "?view=page"],
                    )

    async def test_panel_header_limits_fail_instead_of_delivering_partial_settings(self) -> None:
        for headers in (
            {"X-Client-Settings": "a" * (_MAX_PANEL_HEADER_BYTES + 1)},
            {f"X-Settings-{i}": "a" * (20 * 1024) for i in range(4)},
        ):
            with self.subTest(headers=list(headers)):

                async def subscription(
                    _request: web.Request, response_headers: dict[str, str] = headers
                ) -> web.Response:
                    return web.Response(body=b"raw", headers=response_headers)

                app = web.Application()
                app.router.add_get("/api/sub/{short_uuid}", subscription)
                async with TestServer(app) as server:
                    with self.assertRaises(SubscriptionTransportError) as failure:
                        await RemnawaveSubscriptionSource(
                            settings_stub(PANEL_API_URL=str(server.make_url("/api")))
                        ).fetch(
                            SimpleNamespace(panel_short_uuid="short-id"),
                            DeliveryRequest(None, {"user-agent": "Happ/1.0"}, "192.0.2.2"),
                        )
                self.assertEqual(failure.exception.status, 502)

    async def test_panel_hwid_rejections_keep_status_and_client_instructions(self) -> None:
        for status, flag in ((404, "x-hwid-not-supported"), (403, "x-hwid-max-devices-reached")):
            with self.subTest(status=status):

                async def subscription(
                    request: web.Request, response_status: int = status, response_flag: str = flag
                ) -> web.Response:
                    self.assertEqual(request.headers["x-hwid"], "device-123456")
                    return web.Response(
                        status=response_status,
                        body=b"device limit",
                        headers={response_flag: "true"},
                    )

                app = web.Application()
                app.router.add_get("/api/sub/{short_uuid}", subscription)
                async with TestServer(app) as server:
                    result = await RemnawaveSubscriptionSource(
                        settings_stub(PANEL_API_URL=str(server.make_url("/api")))
                    ).fetch(
                        SimpleNamespace(panel_short_uuid="short-id"),
                        DeliveryRequest(
                            None, {"USER-AGENT": "Happ/1.0", "X-HWID": "device-123456"}, "192.0.2.2"
                        ),
                    )
                self.assertEqual(result.status, status)
                self.assertEqual(result.body, b"device limit")
                self.assertEqual(result.headers[flag], "true")

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
