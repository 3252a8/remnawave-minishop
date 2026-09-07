from types import SimpleNamespace
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch, sentinel

from aiohttp import web

from bot.app.web.webapp.balance import balance_topup_route


class WebAppBalanceTopupTests(IsolatedAsyncioTestCase):
    async def test_topup_is_rejected_when_balance_feature_is_disabled(self) -> None:
        request = cast(web.Request, object())
        settings = SimpleNamespace(balance_settings=SimpleNamespace(enabled=False))
        with (
            patch("bot.app.web.webapp.balance._require_user_id", return_value=42),
            patch(
                "bot.app.web.webapp.balance._enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch("bot.app.web.webapp.balance.get_settings", return_value=settings),
            patch(
                "bot.app.web.webapp.balance._json_error",
                return_value=sentinel.response,
            ) as json_error,
        ):
            response = await balance_topup_route(request)

        self.assertIs(response, sentinel.response)
        json_error.assert_called_once_with(
            403,
            "user_balance_disabled",
            "User balance is disabled",
        )
