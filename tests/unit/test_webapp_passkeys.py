import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import web

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import passkeys as passkeys_module


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class WebAppPasskeyTests(IsolatedAsyncioTestCase):
    async def test_passkey_registration_requires_an_existing_authenticated_account(self):
        parse_payload = AsyncMock()
        request = SimpleNamespace(app={})

        with (
            patch.object(
                passkeys_module,
                "_require_user_id",
                side_effect=web.HTTPUnauthorized(
                    text=json.dumps({"ok": False, "error": "unauthorized"}),
                    content_type="application/json",
                ),
            ),
            patch.object(passkeys_module, "_parse_model_payload", parse_payload),
            self.assertRaises(web.HTTPUnauthorized) as raised,
        ):
            await passkeys_module.account_passkey_register_route(request)

        self.assertEqual(raised.exception.status, 401)
        self.assertEqual(json.loads(raised.exception.text), {"ok": False, "error": "unauthorized"})
        parse_payload.assert_not_awaited()

    async def test_register_route_persists_verified_passkey_with_generated_name(self):
        settings = SimpleNamespace(PASSKEY_LOGIN_ENABLED=True)
        session = SimpleNamespace(
            add=Mock(),
            execute=AsyncMock(
                return_value=SimpleNamespace(scalar_one_or_none=Mock(return_value=None))
            ),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        payload = SimpleNamespace(
            challenge="AQID",
            credential={
                "id": "credential-id",
                "response": {"transports": ["internal"]},
            },
            name="/minishop · Windows",
        )
        verification = SimpleNamespace(
            credential_id=b"credential-id",
            credential_public_key=b"public-key",
            sign_count=7,
            credential_device_type=SimpleNamespace(value="single_device"),
            credential_backed_up=False,
        )
        verify_registration = Mock(return_value=verification)
        request = SimpleNamespace(app={})

        with (
            patch.object(passkeys_module, "_require_user_id", return_value=42),
            patch.object(passkeys_module, "get_settings", return_value=settings),
            patch.object(
                passkeys_module,
                "_parse_model_payload",
                AsyncMock(return_value=payload),
            ),
            patch.object(
                passkeys_module,
                "_webauthn",
                return_value=(None, None, None, None, verify_registration, None, None, None, None),
            ),
            patch.object(
                passkeys_module,
                "get_session_factory",
                return_value=_SessionFactory(session),
            ),
            patch.object(
                passkeys_module,
                "_consume_challenge",
                AsyncMock(return_value=SimpleNamespace()),
            ),
            patch.object(
                passkeys_module,
                "_rp_context",
                return_value=("127.0.0.1", "/minishop", "http://127.0.0.1:8082"),
            ),
            patch.object(
                passkeys_module,
                "_invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate_cache,
        ):
            response = await passkeys_module.account_passkey_register_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text), {"ok": True})
        credential = session.add.call_args.args[0]
        self.assertEqual(credential.user_id, 42)
        self.assertEqual(credential.name, "/minishop · Windows")
        self.assertEqual(credential.public_key, b"public-key")
        self.assertEqual(credential.sign_count, 7)
        self.assertEqual(credential.transports, "internal")
        session.commit.assert_awaited_once()
        verify_registration.assert_called_once_with(
            credential=payload.credential,
            expected_challenge=b"\x01\x02\x03",
            expected_rp_id="127.0.0.1",
            expected_origin="http://127.0.0.1:8082",
            require_user_verification=True,
        )
        invalidate_cache.assert_awaited_once_with(settings, 42)
