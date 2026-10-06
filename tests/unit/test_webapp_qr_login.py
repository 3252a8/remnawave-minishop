import json
import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from aiohttp import web
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import qr_login as qr_module
from bot.app.web.webapp.payloads import (
    WebAppQrLoginApprovePayload,
    WebAppQrLoginClaimPayload,
    WebAppQrLoginRequestPayload,
)
from db.base import Base
from db.dal import qr_login_dal
from db.models import User

SETTINGS = SimpleNamespace(
    QR_LOGIN_ENABLED=True,
    SUBSCRIPTION_MINI_APP_URL="https://shop.example/",
    WEBAPP_SESSION_SECRET="s" * 48,
    WEBAPP_SESSION_TTL_SECONDS=3600,
    trusted_proxies=[],
)


def _request(cookies=None):
    return cast(
        web.Request,
        SimpleNamespace(
            app={},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/131.0"},
            cookies=cookies or {},
        ),
    )


class WebAppQrLoginRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.factory() as session:
            session.add_all([User(user_id=42), User(user_id=43, is_banned=True)])
            await session.commit()
        self.settings = SimpleNamespace(**vars(SETTINGS))
        self.patches = [
            patch.object(qr_module, "get_settings", return_value=self.settings),
            patch.object(qr_module, "get_session_factory", return_value=self.factory),
            patch.object(qr_module, "check_request_limits", AsyncMock(return_value=None)),
            patch.object(qr_module, "enforce_action_limit", AsyncMock(return_value=None)),
            patch.object(qr_module, "client_ip", return_value="203.0.113.5"),
            patch.object(qr_module, "_invalidate_webapp_user_caches", AsyncMock()),
        ]
        for item in self.patches:
            item.start()

    async def asyncTearDown(self):
        for item in reversed(self.patches):
            item.stop()
        await self.engine.dispose()

    async def _start(self):
        response = await qr_module.qr_login_start_route(_request())
        body = json.loads(response.text)
        cookie = response.cookies[qr_module.QR_LOGIN_COOKIE_NAME].value
        return body, cookie

    async def _poll(self, request_id, cookie):
        payload = WebAppQrLoginRequestPayload(request_id=request_id)
        with patch.object(qr_module, "_parse_model_payload", AsyncMock(return_value=payload)):
            response = await qr_module.qr_login_poll_route(
                _request({qr_module.QR_LOGIN_COOKIE_NAME: cookie})
            )
        return response, json.loads(response.text)

    async def _as_user(self, user_id, route, payload):
        with (
            patch.object(qr_module, "_require_user_id", return_value=user_id),
            patch.object(qr_module, "_parse_model_payload", AsyncMock(return_value=payload)),
        ):
            response = await route(_request())
        return response, json.loads(response.text)

    async def test_everything_is_hidden_while_the_setting_is_off(self):
        self.settings.QR_LOGIN_ENABLED = False
        response = await qr_module.qr_login_start_route(_request())
        self.assertEqual(response.status, 404)
        self.assertEqual(json.loads(response.text)["error"], "qr_login_not_enabled")

    async def test_start_points_the_qr_back_at_the_shop_not_at_telegram(self):
        body, cookie = await self._start()
        code = body["qr_url"].split("#qrlogin=", 1)[1]
        self.assertTrue(body["qr_url"].startswith("https://shop.example/settings#qrlogin="))
        self.assertNotIn("t.me", body["qr_url"])
        self.assertTrue(qr_login_dal.is_token(code))
        self.assertTrue(cookie)
        self.assertEqual((body["expires_in"], body["poll_interval"]), (120, 2))

    async def test_poll_from_another_tab_or_without_cookie_reports_expired(self):
        body, _cookie = await self._start()
        response, data = await self._poll(body["request_id"], "forged")
        self.assertEqual(data["status"], "expired")
        self.assertEqual(response.cookies[qr_module.QR_LOGIN_COOKIE_NAME].value, "")

    async def test_the_waiting_browser_gets_the_session_once(self):
        body, cookie = await self._start()
        code = body["qr_url"].split("#qrlogin=", 1)[1]
        _, claimed = await self._as_user(
            42, qr_module.account_qr_login_claim_route, WebAppQrLoginClaimPayload(code=code)
        )
        self.assertEqual(
            (claimed["browser"], claimed["os"], claimed["ip"]), ("Firefox", "Linux", "203.0.113.5")
        )

        _, scanned = await self._poll(body["request_id"], cookie)
        self.assertEqual(scanned["status"], "scanned")
        number = scanned["match_number"]

        wrong_response, wrong = await self._as_user(
            42,
            qr_module.account_qr_login_approve_route,
            WebAppQrLoginApprovePayload(
                request_id=claimed["request_id"], number=(number + 1) % 100
            ),
        )
        self.assertEqual(
            (wrong_response.status, wrong["error"], wrong["attempts_left"]),
            (400, "qr_login_wrong_number", 2),
        )
        _, approved = await self._as_user(
            42,
            qr_module.account_qr_login_approve_route,
            WebAppQrLoginApprovePayload(request_id=claimed["request_id"], number=number),
        )
        self.assertEqual(approved, {"ok": True, "status": "approved"})

        response, data = await self._poll(body["request_id"], cookie)
        self.assertEqual((data["status"], data["user_id"]), ("approved", 42))
        self.assertTrue(response.cookies["rw_webapp_session"].value)
        self.assertEqual(response.cookies[qr_module.QR_LOGIN_COOKIE_NAME].value, "")
        _, second = await self._poll(body["request_id"], cookie)
        self.assertEqual(second["status"], "expired")

    async def test_a_second_account_cannot_claim_and_a_banned_one_cannot_approve(self):
        body, _cookie = await self._start()
        code = body["qr_url"].split("#qrlogin=", 1)[1]
        banned_response, _ = await self._as_user(
            43, qr_module.account_qr_login_claim_route, WebAppQrLoginClaimPayload(code=code)
        )
        self.assertEqual(banned_response.status, 403)
        await self._as_user(
            42, qr_module.account_qr_login_claim_route, WebAppQrLoginClaimPayload(code=code)
        )
        async with self.factory() as session:
            session.add(User(user_id=44))
            await session.commit()
        conflict_response, conflict = await self._as_user(
            44, qr_module.account_qr_login_claim_route, WebAppQrLoginClaimPayload(code=code)
        )
        self.assertEqual(
            (conflict_response.status, conflict["error"]), (409, "qr_login_already_claimed")
        )
        unknown_response, unknown = await self._as_user(
            42, qr_module.account_qr_login_claim_route, WebAppQrLoginClaimPayload(code="A" * 22)
        )
        self.assertEqual((unknown_response.status, unknown["error"]), (410, "qr_login_expired"))

    async def test_decline_stops_the_waiting_browser(self):
        body, cookie = await self._start()
        code = body["qr_url"].split("#qrlogin=", 1)[1]
        _, claimed = await self._as_user(
            42, qr_module.account_qr_login_claim_route, WebAppQrLoginClaimPayload(code=code)
        )
        await self._as_user(
            42,
            qr_module.account_qr_login_deny_route,
            WebAppQrLoginRequestPayload(request_id=claimed["request_id"]),
        )
        response, data = await self._poll(body["request_id"], cookie)
        self.assertEqual(data["status"], "denied")
        self.assertEqual(response.cookies[qr_module.QR_LOGIN_COOKIE_NAME].value, "")
