import asyncio
from unittest.mock import Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from bot.payment_providers import registry
from bot.payment_providers.cloudpayments.service import CloudPaymentsConfig
from bot.payment_providers.shared.http_client import HttpClientMixin, post_json_request
from bot.services.settings_override_service import update_overrides
from config.settings import Settings


class Client(HttpClientMixin):
    def __init__(self, config: CloudPaymentsConfig) -> None:
        self.config = config
        self._init_http_client()


def test_payment_credentials_never_follow_a_foreign_origin() -> None:
    async def run() -> None:
        received: list[object] = []
        leaked: list[object] = []

        async def attacker(request: web.Request) -> web.Response:
            leaked.append(await request.json())
            return web.json_response({"ok": True})

        attacker_app = web.Application()
        attacker_app.router.add_post("/", attacker)
        attacker_server = TestServer(attacker_app)
        await attacker_server.start_server()

        async def api(request: web.Request) -> web.Response:
            received.append(await request.json())
            return web.json_response({"ok": True})

        async def redirect(_request: web.Request) -> web.Response:
            raise web.HTTPTemporaryRedirect(str(attacker_server.make_url("/")))

        app = web.Application()
        app.router.add_post("/", api)
        app.router.add_post("/redirect", redirect)
        server = TestServer(app)
        await server.start_server()
        config = CloudPaymentsConfig(BASE_URL=str(server.make_url("/")))
        client = Client(config)
        try:
            session = await client._get_session()
            secret = {"api_key": "test-secret"}
            ok, _ = await post_json_request(
                session, str(server.make_url("/")), body=secret, log_prefix="test"
            )
            assert ok and received == [secret]
            ok, _ = await post_json_request(
                session, str(server.make_url("/redirect")), body=secret, log_prefix="test"
            )
            assert not ok
            config.BASE_URL = str(attacker_server.make_url("/"))
            ok, _ = await post_json_request(
                session, config.BASE_URL, body=secret, log_prefix="test"
            )
            assert not ok and leaked == []
            # Explicit reconfiguration gets a new policy; an in-flight session
            # keeps its original origin and cannot leak keys via a redirect.
            updated_session = await client._get_session()
            assert updated_session is not session
            assert not session.closed
            ok, _ = await post_json_request(
                updated_session, config.BASE_URL, body=secret, log_prefix="test"
            )
            assert ok and leaked == [secret]
            ok, _ = await post_json_request(
                updated_session, str(server.make_url("/")), body=secret, log_prefix="test"
            )
            assert not ok and received == [secret]
        finally:
            await client.close()
            await server.close()
            await attacker_server.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:secret@api.example.com",
        "https://api.example.com:65536",
        "http://169.254.169.254/latest/meta-data",
        "http://[::ffff:169.254.169.254]/latest/meta-data",
        "http://0.0.0.0/api",
        "http://224.0.0.1/api",
    ],
)
def test_settings_reject_unsafe_api_urls_before_persisting_any_change(url: str) -> None:
    registry.build_provider_configs(force=True)
    settings = Settings(
        _env_file=None, BOT_TOKEN="token", POSTGRES_USER="test", POSTGRES_PASSWORD="test"
    )
    session_factory = Mock(
        side_effect=AssertionError("An unsafe API URL must not reach the database")
    )
    result = asyncio.run(
        update_overrides(settings, session_factory, updates={"CLOUDPAYMENTS_BASE_URL": url})
    )
    assert result == {
        "ok": False,
        "errors": {"CLOUDPAYMENTS_BASE_URL": "unapproved_payment_api_origin"},
    }
    session_factory.assert_not_called()
