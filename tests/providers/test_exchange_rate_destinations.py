import asyncio
from decimal import Decimal

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from bot.payment_providers.paykilla.config import PaykillaConfig, _exchange_rate_sync
from bot.utils.http_transport import fetch_json, fetch_json_sync
from bot.utils.outbound_network import OutboundPolicy, approved_endpoints


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1:9/a"])
def test_sync_exchange_override_cannot_read_files_or_probe_internal_services(url: str) -> None:
    config = PaykillaConfig()
    config.EXCHANGE_RATE_URL = url
    assert _exchange_rate_sync(config, "USD", "RUB") is None


def test_both_http_paths_keep_rates_and_reject_unsafe_redirects() -> None:
    async def run() -> None:
        async def rates(_request: web.Request) -> web.Response:
            return web.json_response({"result": "success", "rates": {"RUB": 90}})

        async def redirect(_request: web.Request) -> web.Response:
            raise web.HTTPFound("http://127.0.0.2:9/private")

        app = web.Application()
        app.router.add_get("/rates", rates)
        app.router.add_get("/redirect", redirect)
        server = TestServer(app)
        await server.start_server()
        try:
            policy = OutboundPolicy(approved_endpoints([str(server.make_url("/"))]))
            url = str(server.make_url("/rates"))
            assert await fetch_json(url, total_seconds=2, policy=policy) == {
                "result": "success",
                "rates": {"RUB": 90},
            }
            config = PaykillaConfig(EXCHANGE_RATE_URL=url)
            assert await asyncio.to_thread(_exchange_rate_sync, config, "USD", "RUB") == Decimal(
                "90"
            )
            redirect_url = str(server.make_url("/redirect"))
            with pytest.raises(ValueError):
                await fetch_json(redirect_url, total_seconds=2, policy=policy)
            with pytest.raises(ValueError):
                await asyncio.to_thread(fetch_json_sync, redirect_url, timeout=2, policy=policy)
        finally:
            await server.close()

    asyncio.run(run())
