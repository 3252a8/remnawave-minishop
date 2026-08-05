"""Sign-in runs while the customer's browser waits, so its calls to Telegram are bounded.

The OAuth callback, the Mini App auth route and the account-link route all reach out to Telegram
before they answer. An unbounded call on any of them surfaces to the customer as a 504 from the
reverse proxy, with no way back into the app — so each is capped, and the signing keys are
fetched once per lifespan rather than once per login.
"""

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import jwt

from bot.app.web import webapp_auth
from bot.app.web.webapp import telegram_notifications as notifications
from tests.support.settings_stub import settings_stub

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENT_ID = 8353391008
NONCE = "nonce-value"


class _FakeSigningKey:
    key = "fake-signing-key"


def _fake_claims(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {
        "nonce": NONCE,
        "iat": int(time.time()),
        "id": 4242,
        "given_name": "Alex",
    }


class TelegramOauthJwksTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.constructed: list[dict[str, Any]] = []
        self.get_signing_key = lambda _token: _FakeSigningKey()
        constructed = self.constructed
        test_case = self

        class FakeJWKClient:
            def __init__(self, uri: str, **kwargs: Any) -> None:
                constructed.append({"uri": uri, **kwargs})

            def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
                return test_case.get_signing_key(token)

        for patcher in (
            patch.object(webapp_auth, "_telegram_jwks_client", None),
            patch.object(jwt, "PyJWKClient", FakeJWKClient),
            patch.object(jwt, "decode", _fake_claims),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def _validate(self) -> dict[str, Any] | None:
        claims: dict[str, Any] | None = await webapp_auth.validate_telegram_oauth_id_token(
            "header.payload.signature",
            client_id=CLIENT_ID,
            expected_nonce=NONCE,
            max_age_seconds=300,
        )
        return claims

    async def test_signing_keys_are_fetched_once_instead_of_once_per_login(self) -> None:
        first = await self._validate()
        second = await self._validate()

        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        assert first is not None
        self.assertEqual(first["id"], 4242)
        self.assertEqual(
            len(self.constructed),
            1,
            "a new JWKS client per login refetches the key set on every login",
        )

    async def test_jwks_client_is_built_with_a_cache_and_a_timeout(self) -> None:
        await self._validate()

        self.assertEqual(self.constructed[0]["uri"], webapp_auth.TELEGRAM_OAUTH_JWKS_URL)
        self.assertIs(self.constructed[0]["cache_jwk_set"], True)
        self.assertEqual(
            self.constructed[0]["lifespan"],
            webapp_auth.TELEGRAM_OAUTH_JWKS_LIFESPAN_SECONDS,
        )
        self.assertEqual(
            self.constructed[0]["timeout"],
            webapp_auth.TELEGRAM_OAUTH_JWKS_TIMEOUT_SECONDS,
        )

    async def test_a_stalled_key_fetch_gives_up_instead_of_hanging_the_login(self) -> None:
        def stalled(_token: str) -> _FakeSigningKey:
            time.sleep(0.5)
            return _FakeSigningKey()

        self.get_signing_key = stalled
        with patch.object(webapp_auth, "TELEGRAM_OAUTH_VALIDATION_TIMEOUT_SECONDS", 0.05):
            started = time.monotonic()
            result = await self._validate()
            elapsed = time.monotonic() - started

        self.assertIsNone(result)
        self.assertLess(elapsed, 0.4, "the login waited for the stalled key fetch")


class _Session:
    def __init__(self) -> None:
        self.rollback_count = 0

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        self.rollback_count += 1


class TelegramNotificationProbeTimeoutTests(IsolatedAsyncioTestCase):
    """Every sign-in path runs this probe on a request the customer is waiting on."""

    async def test_a_stalled_bot_api_yields_unknown_instead_of_stalling_the_request(self) -> None:
        session = _Session()

        async def stalled(**_kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(5)
            return {"ok": True, "status": "enabled"}

        patches = (
            patch.object(notifications, "get_settings", lambda _request: settings_stub()),
            patch.object(notifications, "get_session_factory", lambda _request: lambda: session),
            patch.object(notifications, "get_bot", lambda _request: object()),
            patch.object(notifications, "get_i18n", lambda _request: None),
            patch.object(notifications, "get_bot_username", lambda _request: "shop_bot"),
            patch.object(
                notifications.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=SimpleNamespace(user_id=7, is_banned=False)),
            ),
            patch.object(notifications, "probe_telegram_notifications", stalled),
            patch.object(notifications, "TELEGRAM_NOTIFICATIONS_PROBE_TIMEOUT_SECONDS", 0.05),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        started = time.monotonic()
        result = await notifications._probe_telegram_notifications_for_user_id(object(), 7)
        elapsed = time.monotonic() - started

        self.assertEqual(result["status"], "unknown")
        self.assertIs(result["enabled"], False)
        self.assertEqual(session.rollback_count, 1)
        self.assertLess(elapsed, 1.0, "the request waited for the stalled Bot API call")


def test_every_sign_in_path_shares_the_bounded_probe() -> None:
    """The bound lives in the helper, so no call site can reintroduce an unbounded probe."""

    helper = (REPO_ROOT / "backend/bot/app/web/webapp/telegram_notifications.py").read_text(
        encoding="utf-8"
    )
    callers = [
        (REPO_ROOT / "backend/bot/app/web/webapp/auth_oauth.py").read_text(encoding="utf-8"),
        (REPO_ROOT / "backend/bot/app/web/webapp/account.py").read_text(encoding="utf-8"),
    ]

    assert "asyncio.wait_for(" in helper
    assert "TELEGRAM_NOTIFICATIONS_PROBE_TIMEOUT_SECONDS" in helper
    for caller in callers:
        assert "_probe_telegram_notifications_for_user_id(request, int(" in caller
