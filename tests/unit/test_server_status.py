from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta
from typing import cast

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer, make_mocked_request

from bot.app.web.context import SERVER_STATUS_SERVICE, SETTINGS
from bot.app.web.webapp.server_status import server_status_route
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.server_status.kuma import parse_kuma_status_page
from bot.services.server_status.models import ProviderStatus, StatusGroup, StatusItem
from bot.services.server_status.service import (
    MAX_PROVIDER_RESPONSE_BYTES,
    ProviderFetchError,
    ServerStatusService,
)
from bot.services.server_status.xray_checker import parse_xray_proxies
from config.server_status import (
    KumaStatusPageUrlError,
    parse_kuma_status_page_url,
    parse_legacy_kuma_status_page_url,
)
from config.settings import Settings
from tests.support.settings_stub import settings_stub


def _settings(**overrides: object) -> Settings:
    return cast(Settings, settings_stub(**overrides))


def test_kuma_parser_normalizes_heartbeats_uptime_and_incidents() -> None:
    result = parse_kuma_status_page(
        {
            "publicGroupList": [
                {
                    "id": 7,
                    "name": " Europe ",
                    "monitorList": [
                        {"id": 11, "name": "DE-1"},
                        {"id": 12, "name": "DE-2"},
                        {"id": 13, "name": "Maintenance"},
                    ],
                }
            ],
            "incident": {
                "title": "<b>Latency</b>",
                "content": "<p>Investigating <script>secret()</script>now</p>",
                "style": "warning",
                "createdDate": "2026-08-24T10:00:00Z",
            },
            "incidents": [],
        },
        {
            "heartbeatList": {
                "11": [{"status": 1, "ping": 31, "time": "2026-08-24T11:59:30Z"}],
                "12": [{"status": 1}, {"status": 0, "ping": "not-a-number"}],
                "13": [{"status": 3}],
            },
            "uptimeList": {"11_24": 0.9998},
        },
    )

    assert result.status == "partial_outage"
    assert [item.status for item in result.groups[0].items] == [
        "online",
        "offline",
        "maintenance",
    ]
    assert result.groups[0].items[0].uptime_24h == 99.98
    assert result.groups[0].items[1].latency_ms is None
    assert result.incidents[0].title == "Latency"
    assert result.incidents[0].content == "Investigating now"


def test_kuma_parser_accepts_incidents_array_and_missing_heartbeat() -> None:
    result = parse_kuma_status_page(
        {
            "publicGroupList": [{"name": "Servers", "monitorList": [{"id": "a", "name": "A"}]}],
            "incidents": [{"title": "Outage", "content": "Down", "style": "danger"}],
        },
        {"heartbeatList": {}, "uptimeList": {}},
    )

    assert result.groups[0].items[0].status == "unknown"
    assert result.status == "major_outage"


@pytest.mark.parametrize(
    ("value", "page_url", "heartbeat_url"),
    [
        (
            "https://uptime.example.test/status/services",
            "https://uptime.example.test/api/status-page/services",
            "https://uptime.example.test/api/status-page/heartbeat/services",
        ),
        (
            "https://uptime.example.test/kuma/status/team%20services/",
            "https://uptime.example.test/kuma/api/status-page/team%20services",
            "https://uptime.example.test/kuma/api/status-page/heartbeat/team%20services",
        ),
        (
            "https://uptime.example.test/kuma/status/%D1%81%D0%B5%D1%80%D0%B2%D0%B8%D1%81",
            "https://uptime.example.test/kuma/api/status-page/%D1%81%D0%B5%D1%80%D0%B2%D0%B8%D1%81",
            "https://uptime.example.test/kuma/api/status-page/heartbeat/%D1%81%D0%B5%D1%80%D0%B2%D0%B8%D1%81",
        ),
    ],
)
def test_kuma_status_page_url_builds_api_endpoints(
    value: str, page_url: str, heartbeat_url: str
) -> None:
    status_page = parse_kuma_status_page_url(value)

    assert status_page.api_url() == page_url
    assert status_page.api_url("heartbeat") == heartbeat_url


@pytest.mark.parametrize(
    "value",
    [
        "uptime.example.test/status/services",
        "ftp://uptime.example.test/status/services",
        "https:///status/services",
        "https://user:password@uptime.example.test/status/services",
        "https://uptime.example.test/status/services?token=secret",
        "https://uptime.example.test/status/services#details",
        "https://uptime.example.test/services",
        "https://uptime.example.test/status/",
        "https://uptime .example.test/status/services",
        "https://uptime.example.test/status/team%2Fservices",
        "https://uptime.example.test/kuma//status/services",
        "https://uptime.example.test/status/services//",
        "https://uptime.example.test/%2E/status/services",
        "https://uptime.example.test/status/%2E%2E",
        "https://-uptime.example.test/status/services",
        "https://uptime.example.test:0/status/services",
        "",
    ],
)
def test_kuma_status_page_url_rejects_invalid_urls(value: str) -> None:
    with pytest.raises(KumaStatusPageUrlError):
        parse_kuma_status_page_url(value)


def test_legacy_kuma_base_url_is_parsed_only_with_the_separate_slug() -> None:
    status_page = parse_legacy_kuma_status_page_url(
        "https://uptime.example.test/kuma/",
        "team services",
    )

    assert (
        status_page.api_url() == "https://uptime.example.test/kuma/api/status-page/team%20services"
    )


def test_kuma_malformed_published_url_does_not_use_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        service = ServerStatusService(
            _settings(
                SERVER_STATUS_PROVIDER="uptime-kuma",
                SERVER_STATUS_KUMA_URL="https://uptime.example.test/status/",
            )
        )
        monkeypatch.setattr(service, "_fetch_json", pytest.fail)

        with pytest.raises(ProviderFetchError, match="configuration_error"):
            await service._fetch_provider()

    asyncio.run(run())


def test_xray_parser_groups_and_normalizes_public_proxy_fields() -> None:
    result = parse_xray_proxies(
        {
            "success": True,
            "data": [
                {
                    "stableId": "abc",
                    "name": "DE-1",
                    "groupName": "Germany",
                    "online": True,
                    "latencyMs": 42,
                    "lastCheck": 1787572794,
                    "host": "must-not-leak",
                },
                {
                    "stableId": "def",
                    "name": "Fallback",
                    "groupName": "",
                    "online": False,
                    "latencyMs": "invalid",
                    "lastCheck": "invalid",
                },
            ],
        }
    )

    assert result.status == "partial_outage"
    assert [group.name for group in result.groups] == ["Germany", "Servers"]
    assert result.groups[0].items[0].last_check is not None
    assert result.groups[1].items[0].latency_ms is None
    assert "host" not in result.model_dump_json()


@pytest.mark.parametrize("payload", [{}, {"success": False}, [], "invalid"])
def test_xray_parser_rejects_invalid_responses(payload: object) -> None:
    with pytest.raises(ValueError):
        parse_xray_proxies(payload)


def test_disabled_and_url_modes_do_not_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        settings = _settings(SERVER_STATUS_URL="https://status.example.test")
        service = ServerStatusService(settings)
        monkeypatch.setattr(service, "_fetch_provider", pytest.fail)

        disabled = await service.get_status()
        settings.SERVER_STATUS_ENABLED = True
        url_mode = await service.get_status()

        assert disabled.enabled is False
        assert url_mode.enabled is True
        assert url_mode.external_url == "https://status.example.test"
        assert url_mode.sources == []

    asyncio.run(run())


def test_url_mode_without_url_is_not_exposed() -> None:
    async def run() -> None:
        settings = _settings(
            SERVER_STATUS_ENABLED=True,
            SERVER_STATUS_PROVIDER="url",
            SERVER_STATUS_URL="",
        )
        result = await ServerStatusService(settings).get_status()

        assert result.enabled is False
        assert result.external_url is None

    asyncio.run(run())


@pytest.mark.parametrize(
    ("enabled", "provider", "expected"),
    [
        (False, "url", None),
        (True, "uptime-kuma", None),
        (True, "url", "https://status.example.test"),
    ],
)
def test_external_status_url_respects_feature_mode(
    enabled: bool,
    provider: str,
    expected: str | None,
) -> None:
    settings = _settings(
        SERVER_STATUS_ENABLED=enabled,
        SERVER_STATUS_PROVIDER=provider,
        SERVER_STATUS_URL=" https://status.example.test ",
    )

    assert settings.server_status_external_url == expected


def test_refresh_lock_preserves_body_exception() -> None:
    async def run() -> None:
        service = ServerStatusService(_settings())

        with pytest.raises(RuntimeError, match="body failure"):
            async with service._refresh_lock("test"):
                raise RuntimeError("body failure")

    asyncio.run(run())


def test_local_cache_single_flight_and_stale_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        settings = _settings(
            SERVER_STATUS_ENABLED=True,
            SERVER_STATUS_PROVIDER="xray-checker",
            SERVER_STATUS_XRAY_CHECKER_URL="http://internal-checker",
            SERVER_STATUS_CACHE_TTL_SECONDS=30,
            SERVER_STATUS_STALE_TTL_SECONDS=300,
        )
        service = ServerStatusService(settings)
        calls = 0

        async def fetch() -> ProviderStatus:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return ProviderStatus(
                provider="xray-checker",
                status="operational",
                groups=[
                    StatusGroup(
                        id="xray:servers",
                        name="Servers",
                        items=[
                            StatusItem(
                                id="xray:a",
                                name="A",
                                status="online",
                                provider="xray-checker",
                            )
                        ],
                    )
                ],
            )

        monkeypatch.setattr(service, "_fetch_provider", fetch)
        first, second = await asyncio.gather(service.get_status(), service.get_status())

        assert calls == 1
        assert first.status == second.status == "operational"

        fingerprint = service._fingerprint()
        cached_at, cached_status = service._local_cache[fingerprint]
        service._local_cache[fingerprint] = (cached_at - timedelta(seconds=31), cached_status)

        async def fail() -> ProviderStatus:
            raise ProviderFetchError("timeout")

        monkeypatch.setattr(service, "_fetch_provider", fail)
        stale = await service.get_status()
        assert stale.stale is True
        assert stale.updated_at == first.updated_at

    asyncio.run(run())


def test_provider_failure_without_cache_returns_safe_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        settings = _settings(
            SERVER_STATUS_ENABLED=True,
            SERVER_STATUS_PROVIDER="uptime-kuma",
            SERVER_STATUS_URL="https://legacy-status.example.test",
            SERVER_STATUS_KUMA_URL="http://user:secret@internal-kuma",
        )
        service = ServerStatusService(settings)

        async def fail() -> ProviderStatus:
            raise ProviderFetchError("timeout")

        monkeypatch.setattr(service, "_fetch_provider", fail)
        result = await service.get_status()

        assert result.status == "unknown"
        assert result.sources[0].error == "timeout"
        assert result.external_url is None
        assert "internal-kuma" not in result.model_dump_json()
        assert "secret" not in result.model_dump_json()

    asyncio.run(run())


def test_provider_response_size_is_limited() -> None:
    async def run() -> None:
        async def large_response(_: web.Request) -> web.Response:
            return web.Response(body=b" " * (MAX_PROVIDER_RESPONSE_BYTES + 1))

        app = web.Application()
        app.router.add_get("/status", large_response)
        server = TestServer(app)
        service = ServerStatusService(_settings())
        await server.start_server()
        try:
            with pytest.raises(ProviderFetchError, match="response_too_large"):
                await service._fetch_json("uptime-kuma", str(server.make_url("/status")))
        finally:
            await service.close()
            await server.close()

    asyncio.run(run())


def test_provider_reads_chunked_json_until_eof() -> None:
    async def run() -> None:
        async def chunked_response(request: web.Request) -> web.StreamResponse:
            response = web.StreamResponse(headers={"Content-Type": "application/json"})
            await response.prepare(request)
            await response.write(b'{"heartbeatList":')
            await asyncio.sleep(0.01)
            await response.write(b'{"1":[{"status":1}]}}')
            await response.write_eof()
            return response

        app = web.Application()
        app.router.add_get("/status", chunked_response)
        server = TestServer(app)
        service = ServerStatusService(_settings())
        await server.start_server()
        try:
            payload = await service._fetch_json(
                "uptime-kuma",
                str(server.make_url("/status")),
            )
        finally:
            await service.close()
            await server.close()

        assert payload == {"heartbeatList": {"1": [{"status": 1}]}}

    asyncio.run(run())


@pytest.mark.parametrize(
    ("body", "error_type"),
    [
        (b"", "empty_response"),
        (b"<html>provider-secret</html>", "non_json_response"),
    ],
)
def test_provider_invalid_json_response_is_classified_without_body_logging(
    body: bytes,
    error_type: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def run() -> int:
        requests = 0

        async def invalid_response(_: web.Request) -> web.Response:
            nonlocal requests
            requests += 1
            return web.Response(body=body)

        app = web.Application()
        app.router.add_get("/api/status-page/heartbeat/example", invalid_response)
        server = TestServer(app)
        service = ServerStatusService(_settings())
        await server.start_server()
        try:
            with pytest.raises(ProviderFetchError, match="invalid_response"):
                await service._fetch_json(
                    "uptime-kuma",
                    str(server.make_url("/api/status-page/heartbeat/example")),
                )
        finally:
            await service.close()
            await server.close()
        return requests

    with caplog.at_level("WARNING", logger="bot.services.server_status.service"):
        requests = asyncio.run(run())

    assert requests == 1
    assert "path=/api/status-page/heartbeat/example" in caplog.text
    assert "status=200" in caplog.text
    assert f"response_bytes={len(body)}" in caplog.text
    assert f"body_sha256={hashlib.sha256(body).hexdigest()}" in caplog.text
    assert f"body_kind={'empty' if not body else 'html'}" in caplog.text
    assert f"error_type={error_type}" in caplog.text
    assert "provider-secret" not in caplog.text


def test_provider_failure_logs_redirect_target_without_query_or_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def run() -> None:
        async def redirect(_: web.Request) -> web.Response:
            raise web.HTTPFound("/replacement?token=redirect-secret")

        async def replacement(_: web.Request) -> web.Response:
            return web.Response(text="<html>provider-secret</html>", content_type="text/html")

        app = web.Application()
        app.router.add_get("/original", redirect)
        app.router.add_get("/replacement", replacement)
        server = TestServer(app)
        service = ServerStatusService(_settings())
        await server.start_server()
        try:
            with pytest.raises(ProviderFetchError, match="invalid_response"):
                await service._fetch_json(
                    "uptime-kuma",
                    f"{server.make_url('/original')}?token=request-secret",
                )
        finally:
            await service.close()
            await server.close()

    with caplog.at_level("WARNING", logger="bot.services.server_status.service"):
        asyncio.run(run())

    assert "path=/original" in caplog.text
    assert "redirects=1" in caplog.text
    assert "final_path=/replacement" in caplog.text
    assert "content_type=text/html;_charset=utf-8" in caplog.text
    assert "body_kind=html" in caplog.text
    assert "request-secret" not in caplog.text
    assert "redirect-secret" not in caplog.text
    assert "provider-secret" not in caplog.text


def test_kuma_fetches_status_page_before_heartbeats_when_parallel_requests_fail() -> None:
    async def run() -> None:
        status_page_in_progress = False
        status_page_started = asyncio.Event()

        async def status_page(_: web.Request) -> web.Response:
            nonlocal status_page_in_progress
            status_page_in_progress = True
            status_page_started.set()
            try:
                await asyncio.sleep(0.15)
                return web.json_response(
                    {
                        "publicGroupList": [
                            {
                                "id": 1,
                                "name": "Servers",
                                "monitorList": [{"id": 1, "name": "DE-1"}],
                            }
                        ]
                    }
                )
            finally:
                status_page_in_progress = False

        async def heartbeats(_: web.Request) -> web.Response:
            await status_page_started.wait()
            if status_page_in_progress:
                return web.Response(text="temporary upstream error")
            return web.json_response(
                {
                    "heartbeatList": {"1": [{"status": 1}]},
                    "uptimeList": {"1_24": 1},
                }
            )

        app = web.Application()
        app.router.add_get("/api/status-page/example", status_page)
        app.router.add_get("/api/status-page/heartbeat/example", heartbeats)
        server = TestServer(app)
        await server.start_server()
        service = ServerStatusService(
            _settings(
                SERVER_STATUS_PROVIDER="uptime-kuma",
                SERVER_STATUS_KUMA_URL=str(server.make_url("/status/example")),
            )
        )
        try:
            result = await service._fetch_provider()
        finally:
            await service.close()
            await server.close()

        assert result.status == "operational"
        assert result.groups[0].items[0].status == "online"

    asyncio.run(run())


def test_status_route_requires_auth_and_returns_ok_envelope() -> None:
    async def run() -> None:
        settings = _settings(
            SERVER_STATUS_ENABLED=True,
            SERVER_STATUS_PROVIDER="url",
            SERVER_STATUS_URL="https://status.example.test",
        )
        service = ServerStatusService(settings)
        app = web.Application()
        app[SETTINGS] = settings
        app[SERVER_STATUS_SERVICE] = service

        unauthorized = make_mocked_request("GET", "/api/status", app=app)
        with pytest.raises(web.HTTPUnauthorized):
            await server_status_route(unauthorized)

        token = create_webapp_session_token(settings, 42)
        request = make_mocked_request(
            "GET",
            "/api/status",
            headers={"Authorization": f"Bearer {token}"},
            app=app,
        )
        response = await server_status_route(request)

        assert response.status == 200
        assert response.text is not None
        assert '"ok": true' in response.text
        assert '"externalUrl": "https://status.example.test"' in response.text

    asyncio.run(run())
