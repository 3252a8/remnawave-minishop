from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from bot.app.web.context import set_service_context
from bot.infra.observability import (
    ERROR_REPORTER_SERVICE_KEY,
    observability_error_middleware,
    report_error,
)
from bot.plugins import PluginContext
from config.settings import Settings


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "BOT_TOKEN": "x",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "ADMIN_IDS": "1",
    }
    values.update(overrides)
    return Settings(**values)


@dataclass
class RecordingReporter:
    calls: list[tuple[BaseException, str, dict[str, object] | None]] = field(default_factory=list)

    async def report_error(
        self,
        exc: BaseException,
        *,
        source: str,
        attributes: dict[str, object] | None = None,
    ) -> None:
        self.calls.append((exc, source, attributes))


def test_plugin_context_resolves_observability_services() -> None:
    reporter = RecordingReporter()
    ctx = PluginContext(
        settings=make_settings(),
        services={ERROR_REPORTER_SERVICE_KEY: reporter},
    )

    assert ctx.error_reporter is reporter


def test_report_error_keeps_reporter_failures_isolated(caplog: pytest.LogCaptureFixture) -> None:
    class FailingReporter:
        async def report_error(
            self,
            exc: BaseException,
            *,
            source: str,
            attributes: dict[str, object] | None = None,
        ) -> None:
            raise RuntimeError("reporter failed")

    async def run() -> None:
        with caplog.at_level("ERROR"):
            await report_error(
                FailingReporter(),
                RuntimeError("original"),
                source="test.source",
            )

    asyncio.run(run())

    assert "Error reporter failed while handling test.source" in caplog.text


@pytest.mark.parametrize(
    ("path", "reported_path"),
    [
        ("/boom", "/boom"),
        ("/s/" + "a" * 32, "/s/[redacted]"),
        (
            "/api/subscription-guides/public/" + "a" * 32,
            "/api/subscription-guides/public/[redacted]",
        ),
    ],
)
def test_observability_middleware_reports_handler_exception(path: str, reported_path: str) -> None:
    reporter = RecordingReporter()
    app = web.Application(middlewares=[observability_error_middleware])
    set_service_context(app, ERROR_REPORTER_SERVICE_KEY, reporter)
    request = make_mocked_request("GET", path, app=app)

    async def handler(request: web.Request) -> web.Response:
        raise RuntimeError("boom")

    async def run() -> None:
        with pytest.raises(RuntimeError, match="boom"):
            await observability_error_middleware(request, handler)

    asyncio.run(run())

    assert len(reporter.calls) == 1
    exc, source, attributes = reporter.calls[0]
    assert isinstance(exc, RuntimeError)
    assert str(exc) == "boom"
    assert source == "aiohttp.handler"
    assert attributes == {"method": "GET", "path": reported_path}
