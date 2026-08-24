from __future__ import annotations

import asyncio
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
