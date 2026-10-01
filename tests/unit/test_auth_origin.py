import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from bot.app.web.webapp.assets import _csrf_protection_middleware


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/token",
        "/api/auth/logout",
        "/api/auth/email/verify",
        "/api/auth/email/password",
        "/api/auth/passkey/verify",
    ],
)
@pytest.mark.parametrize("cookies", [{}, {"rw_webapp_session": "victim"}])
def test_cross_origin_login_and_logout_never_reach_the_handler(path: str, cookies: dict) -> None:
    settings = SimpleNamespace(SUBSCRIPTION_MINI_APP_URL="https://shop.test")
    request = SimpleNamespace(
        method="POST",
        path=path,
        cookies=cookies,
        headers={"Origin": "https://attacker.test"},
        app={"settings": settings},
    )
    handler = AsyncMock(return_value=web.Response(text="ok"))
    response = asyncio.run(_csrf_protection_middleware(request, handler))
    assert response.status == 403
    handler.assert_not_awaited()


def test_same_origin_login_works_without_an_existing_csrf_cookie() -> None:
    settings = SimpleNamespace(SUBSCRIPTION_MINI_APP_URL="https://shop.test")
    request = SimpleNamespace(
        method="POST",
        path="/api/auth/token",
        cookies={},
        headers={"Origin": "https://shop.test"},
        app={"settings": settings},
    )
    handler = AsyncMock(return_value=web.Response(text="ok"))
    assert asyncio.run(_csrf_protection_middleware(request, handler)).status == 200
    handler.assert_awaited_once()
