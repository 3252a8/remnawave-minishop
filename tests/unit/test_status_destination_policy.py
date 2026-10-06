import asyncio
import socket

import pytest
from aiohttp import web
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver
from aiohttp.test_utils import TestServer

from bot.services.server_status.service import ProviderFetchError, ServerStatusService
from bot.services.settings_override_service import apply_overrides
from config.settings import Settings


@pytest.mark.parametrize("provider", ["uptime-kuma", "xray-checker"])
def test_status_override_cannot_probe_an_unapproved_loopback(provider: str) -> None:
    async def run() -> None:
        settings = Settings(
            _env_file=None, BOT_TOKEN="token", POSTGRES_USER="test", POSTGRES_PASSWORD="test"
        )
        service = ServerStatusService(settings)
        try:
            with pytest.raises(ProviderFetchError, match="invalid_response"):
                await service._fetch_json(provider, "http://127.0.0.1:9/api/status-page/a")
        finally:
            await service.close()

    asyncio.run(run())


@pytest.mark.parametrize("key", ["SERVER_STATUS_KUMA_URL", "SERVER_STATUS_XRAY_CHECKER_URL"])
def test_admin_status_url_changes_replace_dns_policy_without_restart(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        async def status(request: web.Request) -> web.Response:
            return web.json_response({"host": request.host})

        async def resolve(
            _resolver: ThreadedResolver,
            host: str,
            port: int = 0,
            family: socket.AddressFamily = socket.AF_INET,
        ) -> list[ResolveResult]:
            return [
                {
                    "hostname": host,
                    "host": "127.0.0.1",
                    "port": port,
                    "family": family,
                    "proto": socket.IPPROTO_TCP,
                    "flags": 0,
                }
            ]

        monkeypatch.setattr(ThreadedResolver, "resolve", resolve)
        app = web.Application()
        app.router.add_get("/{tail:.*}", status)
        server = TestServer(app)
        await server.start_server()
        settings = Settings(
            _env_file=None, BOT_TOKEN="token", POSTGRES_USER="test", POSTGRES_PASSWORD="test"
        )
        service = ServerStatusService(settings)
        await service.start()
        original = service._session
        try:
            for host in ("remnawave-xray-checker", "replacement-checker"):
                url = str(server.make_url("/status/a").with_host(host))
                assert apply_overrides(settings, {key: url}) == 1
                assert await service._fetch_json("xray-checker", url) == {
                    "host": f"{host}:{server.port}"
                }
            assert service._session is not original
            assert original is not None and not original.closed
            with pytest.raises(ProviderFetchError, match="invalid_response"):
                await service._fetch_json(
                    "xray-checker",
                    str(server.make_url("/status/a").with_host("remnawave-xray-checker")),
                )
            with pytest.raises(ValueError):
                service._outbound_policy.check_address(
                    "replacement-checker", int(server.port or 0) + 1, "127.0.0.1"
                )
            assert apply_overrides(settings, {key: None}) == 1
            await service.start()
            with pytest.raises(ValueError):
                service._outbound_policy.check_address(
                    "replacement-checker", int(server.port or 0), "127.0.0.1"
                )
        finally:
            await service.close()
            await server.close()
        assert original.closed

    asyncio.run(run())


def test_status_url_change_preserves_in_flight_request() -> None:
    async def run() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_status(_request: web.Request) -> web.Response:
            started.set()
            await release.wait()
            return web.json_response({"old": True})

        app = web.Application()
        app.router.add_get("/status", slow_status)
        server = TestServer(app)
        await server.start_server()
        url = str(server.make_url("/status"))
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            SERVER_STATUS_XRAY_CHECKER_URL=url,
        )
        service = ServerStatusService(settings)
        task = asyncio.create_task(service._fetch_json("xray-checker", url))
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            assert (
                apply_overrides(
                    settings, {"SERVER_STATUS_XRAY_CHECKER_URL": "http://replacement:2112"}
                )
                == 1
            )
            await service.start()
            release.set()
            assert await task == {"old": True}
            with pytest.raises(ValueError):
                service._outbound_policy.check_url(url)
        finally:
            release.set()
            await task
            await service.close()
            await server.close()

    asyncio.run(run())
