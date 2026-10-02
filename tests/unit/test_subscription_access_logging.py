import logging

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from aiohttp.web_log import AccessLogger

from bot.app.web.context import SETTINGS
from bot.app.web.web_server import TrustedProxyAccessLogger
from tests.support.settings_stub import settings_stub


@pytest.fixture
def app() -> web.Application:
    application = web.Application()
    application[SETTINGS] = settings_stub()
    return application


@pytest.mark.parametrize(
    "path",
    ["/s/{token}", "/s/{token}/clash?view=subscription", "/api/subscription-guides/public/{token}"],
)
def test_access_log_masks_subscription_urls_and_referer(
    path: str, caplog: pytest.LogCaptureFixture, app: web.Application
) -> None:
    token = "a" * 32
    referer_token = "b" * 32
    request = make_mocked_request(
        "GET",
        path.format(token=token),
        headers={"Referer": f"https://shop.test/s/{referer_token}?view=page", "User-Agent": "Happ"},
        app=app,
    )
    logger = logging.getLogger("test.subscription.access")
    AccessLogger(logger, AccessLogger.LOG_FORMAT)
    with caplog.at_level(logging.INFO, logger=logger.name):
        TrustedProxyAccessLogger(logger, TrustedProxyAccessLogger.LOG_FORMAT).log(
            request, web.Response(status=404), 0.1
        )
    assert token not in caplog.text
    assert referer_token not in caplog.text
    assert "[redacted]" in caplog.text
    assert "404" in caplog.text
    assert "Happ" in caplog.text
    for record in caplog.records:
        assert token not in str(record.__dict__)
        assert referer_token not in str(record.__dict__)


def test_access_log_masks_subscription_links_on_other_routes_and_custom_headers(
    caplog: pytest.LogCaptureFixture, app: web.Application
) -> None:
    token = "a" * 32
    request = make_mocked_request(
        "GET", "/api/me", headers={"Referer": f"https://shop.test/s/{token}"}, app=app
    )
    response = web.Response(headers={"Location": f"https://shop.test/s/{token}"})
    logger = logging.getLogger("test.subscription.custom_access")
    with caplog.at_level(logging.INFO, logger=logger.name):
        TrustedProxyAccessLogger(logger, "%r %{Referer}i %{Location}o").log(request, response, 0.1)
    assert token not in caplog.text
    assert "/api/me" in caplog.text


def test_access_log_preserves_unrelated_urls(
    caplog: pytest.LogCaptureFixture, app: web.Application
) -> None:
    request = make_mocked_request("GET", "/api/me?language=ru", app=app)
    logger = logging.getLogger("test.subscription.normal_access")
    with caplog.at_level(logging.INFO, logger=logger.name):
        TrustedProxyAccessLogger(logger, TrustedProxyAccessLogger.LOG_FORMAT).log(
            request, web.Response(), 0.1
        )
    assert "/api/me?language=ru" in caplog.text
