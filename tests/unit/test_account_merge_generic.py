"""Account-bound proof and confirmation across current and future providers."""

from __future__ import annotations

import asyncio
import json
from itertools import permutations
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import web
from sqlalchemy import String

from bot.app.web.webapp import account_merge_generic as routes
from bot.app.web.webapp import account_merge_proof as proofs
from bot.app.web.webapp import external_oauth, passkeys
from bot.app.web.webapp.external_oauth_providers import ExternalProvider, ExternalProviderKey
from bot.app.web.webapp.payloads import WebAppAccountMergePayload, WebAppExternalIdentityPayload
from db.models import WebAuthnChallenge

PROVIDERS = ("telegram", "google", "yandex", "discord", "future_provider", "email")


def test_new_provider_can_use_the_existing_unlink_contract() -> None:
    assert WebAppExternalIdentityPayload(provider="future_provider").provider == "future_provider"


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        WEBAPP_SESSION_SECRET="test-merge-secret",
        email_auth_configured=False,
        webapp_auth_providers=PROVIDERS,
        TELEGRAM_ENABLED=True,
        TELEGRAM_LOGIN_ENABLED=True,
        PASSKEY_LOGIN_ENABLED=False,
    )


def _request(provider: str = "telegram") -> SimpleNamespace:
    settings = _settings()
    response = web.Response()
    proofs.set_merge_proof(
        response, settings, user_id=101, source_user_id=202, provider=provider, subject="subject"
    )
    return SimpleNamespace(
        app={"settings": settings},
        cookies={proofs.MERGE_COOKIE: response.cookies[proofs.MERGE_COOKIE].value},
    )


def test_merge_proof_rejects_other_account_tampering_expiry_and_replaced_challenge() -> None:
    request = _request("future_provider")
    proof = proofs.read_merge_proof(request, 101)
    assert proof and proof["source_user_id"] == 202
    assert proofs.read_merge_proof(request, 999) is None
    assert not proofs.confirm_merge_target(request, web.Response(), user_id=101, challenge="old")
    response = web.Response()
    assert proofs.confirm_merge_target(
        request, response, user_id=101, challenge=str(proof["challenge"])
    )
    request.cookies[proofs.MERGE_COOKIE] = response.cookies[proofs.MERGE_COOKIE].value
    assert proofs.read_merge_proof(request, 101)["target_confirmed"]
    with patch.object(proofs.time, "time", return_value=int(proof["expires_at"]) + 1):
        assert proofs.read_merge_proof(request, 101) is None
    request.cookies[proofs.MERGE_COOKIE] += "tampered"
    assert proofs.read_merge_proof(request, 101) is None


class _Factory:
    def __init__(self, providers: tuple[str, ...] = ()) -> None:
        result = Mock()
        result.scalars.return_value.all.return_value = list(providers)
        self.session = SimpleNamespace(
            execute=AsyncMock(return_value=result), commit=AsyncMock(), rollback=AsyncMock()
        )

    def __call__(self) -> _Factory:
        return self

    async def __aenter__(self) -> SimpleNamespace:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        pass


@pytest.mark.parametrize(("source_provider", "target_provider"), tuple(permutations(PROVIDERS, 2)))
def test_all_provider_pairs_keep_target_and_require_fresh_confirmation(
    source_provider: str, target_provider: str
) -> None:
    async def scenario() -> None:
        request = _request(source_provider)
        factory = _Factory(
            (target_provider,) if target_provider not in {"telegram", "email"} else ()
        )
        target = SimpleNamespace(
            user_id=101,
            email=None,
            email_verified_at=None,
            is_banned=False,
            telegram_id=99 if target_provider == "telegram" else None,
            panel_user_uuid=None,
        )
        source = SimpleNamespace(user_id=202, is_banned=False, panel_user_uuid=None)
        merge = AsyncMock(return_value=target)
        locks = AsyncMock()
        with (
            patch.object(routes, "_require_user_id", return_value=101),
            patch.object(routes, "get_session_factory", return_value=factory),
            patch.object(routes.user_dal, "get_user_by_id", AsyncMock(return_value=target)),
            patch.object(routes.user_dal, "lock_user_by_id", locks),
            patch.object(routes, "merge_source", AsyncMock(return_value=source)),
            patch.object(
                routes, "_parse_model_payload", AsyncMock(return_value=WebAppAccountMergePayload())
            ),
            patch.object(routes, "_merge_users_for_web", merge),
            patch.object(
                routes, "_build_account_merge_notice", AsyncMock(return_value={"merged": True})
            ),
            patch.object(
                routes, "_sync_merged_panel_identity_for_user", AsyncMock(return_value=True)
            ),
            patch.object(routes, "_invalidate_webapp_user_caches", AsyncMock()),
            patch.object(routes, "create_webapp_session_token", return_value="new-session"),
            patch.object(
                routes, "_build_webapp_auth_response", return_value=web.json_response({"ok": True})
            ),
        ):
            status = json.loads((await routes.account_merge_status_route(request)).text)
            assert status["provider"] == source_provider
            assert status["email_available"] is False
            assert status["providers"] == ([target_provider] if target_provider != "email" else [])
            rejected = await routes.account_merge_confirm_route(request)
            assert rejected.status == 409
            merge.assert_not_awaited()
            proof = proofs.read_merge_proof(request, 101)
            response = web.Response()
            assert proofs.confirm_merge_target(
                request, response, user_id=101, challenge=proof["challenge"]
            )
            request.cookies[proofs.MERGE_COOKIE] = response.cookies[proofs.MERGE_COOKIE].value
            merged = await routes.account_merge_confirm_route(request)
            assert merged.status == 200
            assert merge.await_args is not None
            assert merge.await_args.kwargs["source_user_id"] == 202
            assert merge.await_args.kwargs["target_user_id"] == 101
            assert merged.cookies[proofs.MERGE_COOKIE]["max-age"] == "0"
            factory.session.commit.assert_awaited_once()
            assert [call.args[1] for call in locks.await_args_list] == [101, 202, 101, 202]

    asyncio.run(scenario())


@pytest.mark.parametrize("owner_id", [101, 303, None])
def test_source_proof_cannot_follow_a_reassigned_identity(owner_id: int | None) -> None:
    async def scenario() -> None:
        request = _request()
        owner = SimpleNamespace(user_id=owner_id) if owner_id is not None else None
        with patch.object(routes, "_identity_owner", AsyncMock(return_value=owner)):
            assert await routes.merge_source(Mock(), proofs.read_merge_proof(request, 101)) is None

    asyncio.run(scenario())


def test_email_confirmation_is_bound_to_merge_challenge_and_target() -> None:
    async def scenario() -> None:
        request = _request("discord")
        request.app["settings"].email_auth_configured = True
        user = SimpleNamespace(
            user_id=101, email="target@example.test", email_verified_at=object(), is_banned=False
        )
        service = SimpleNamespace(
            verify_code=AsyncMock(return_value=SimpleNamespace(ok=False, error="invalid_code"))
        )
        factory = _Factory()
        with (
            patch.object(routes, "_require_user_id", return_value=101),
            patch.object(routes, "get_session_factory", return_value=factory),
            patch.object(routes.user_dal, "lock_user_by_id", AsyncMock()),
            patch.object(routes.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(routes, "get_email_auth_service", return_value=service),
            patch.object(
                routes,
                "_parse_model_payload",
                AsyncMock(return_value=WebAppAccountMergePayload(email_code="123456")),
            ),
            patch.object(routes, "_merge_users_for_web", AsyncMock()) as merge,
        ):
            result = await routes.account_merge_confirm_route(request)
        assert result.status == 400
        assert service.verify_code.await_args.kwargs["email"] == user.email
        assert service.verify_code.await_args.kwargs["target_user_id"] == 101
        assert (
            service.verify_code.await_args.kwargs["purpose"]
            == f"merge_account:{proofs.read_merge_proof(request, 101)['challenge']}"
        )
        merge.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("provider", ["google", "yandex", "discord"])
@pytest.mark.parametrize("owner_id", [101, 202])
def test_oauth_reauthentication_proves_only_the_current_account(
    provider: ExternalProviderKey, owner_id: int
) -> None:
    async def scenario() -> None:
        request = _request("telegram")
        request.match_info = {"provider": provider}
        request.query = {"code": "oauth-code"}
        proof = proofs.read_merge_proof(request, 101)
        assert proof
        state = {
            "provider": provider,
            "purpose": "merge",
            "user_id": 101,
            "merge_challenge": proof["challenge"],
        }
        factory = _Factory()
        factory.session.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(
            user_id=owner_id
        )
        with (
            patch.multiple(
                external_oauth,
                _provider=Mock(
                    return_value=ExternalProvider(
                        key=provider,
                        authorization_url="https://provider/authorize",
                        token_url="https://provider/token",
                        client_id="client",
                        client_secret="secret",
                        scopes=(),
                    )
                ),
                _read_state=Mock(return_value=state),
                _callback_url=Mock(return_value="https://app/callback"),
                _post_token=AsyncMock(return_value={"access_token": "token"}),
                _google_profile=AsyncMock(return_value={"subject": "target"}),
                _yandex_profile=AsyncMock(return_value={"subject": "target"}),
                _discord_profile=AsyncMock(return_value={"subject": "target"}),
                _extract_authenticated_user_id=Mock(return_value=101),
                get_session_factory=Mock(return_value=factory),
            ),
            patch.object(
                external_oauth.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=SimpleNamespace(is_banned=False)),
            ),
        ):
            response = await external_oauth.external_oauth_callback_route(request)
        if owner_id == 101:
            assert (
                response.headers["Location"]
                == f"/settings/security?external_auth={provider}:account_merge_ready"
            )
            request.cookies[proofs.MERGE_COOKIE] = response.cookies[proofs.MERGE_COOKIE].value
            result = proofs.read_merge_proof(request, 101)
            assert result and result["target_confirmed"]
        else:
            assert (
                response.headers["Location"] == f"/settings/security?external_auth={provider}:"
                "account_merge_confirmation_required"
            )
            assert proofs.MERGE_COOKIE not in response.cookies
        factory.session.commit.assert_not_awaited()
        assert "rw_webapp_session" not in response.cookies

    asyncio.run(scenario())


@pytest.mark.parametrize("owner_id", [101, 202])
def test_passkey_merge_confirmation_checks_owner_and_uses_a_bound_challenge(owner_id: int) -> None:
    async def scenario() -> None:
        request = _request("future_provider")
        request.app["settings"].PASSKEY_LOGIN_ENABLED = True
        initial = proofs.read_merge_proof(request, 101)
        assert initial
        options_response = web.Response()
        proofs.write_merge_proof(
            options_response,
            request.app["settings"],
            {**initial, "passkey_challenge_hash": passkeys._challenge_hash("AQID")},
        )
        request.cookies[proofs.MERGE_COOKIE] = options_response.cookies[proofs.MERGE_COOKIE].value
        factory = _Factory()
        credential = SimpleNamespace(user_id=owner_id, public_key=b"public-key", sign_count=0)
        factory.session.execute.return_value.scalar_one_or_none.return_value = credential
        verify = Mock(return_value=SimpleNamespace(new_sign_count=1))
        consume = AsyncMock(return_value=object())
        with (
            patch.object(passkeys, "_require_user_id", return_value=101),
            patch.object(passkeys, "get_session_factory", return_value=factory),
            patch.object(
                passkeys,
                "_parse_model_payload",
                AsyncMock(
                    return_value=SimpleNamespace(challenge="AQID", credential={"id": "credential"})
                ),
            ),
            patch.object(
                passkeys,
                "_webauthn",
                return_value=(None, None, None, verify, None, None, None, None, None),
            ),
            patch.object(passkeys, "_consume_challenge", consume),
            patch.object(
                passkeys, "_rp_context", return_value=("app.example", "App", "https://app.example")
            ),
            patch.object(
                passkeys.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=SimpleNamespace(user_id=101, is_banned=False)),
            ),
        ):
            response = await passkeys.account_merge_passkey_verify_route(request)
        assert response.status == (200 if owner_id == 101 else 400)
        proof = proofs.read_merge_proof(request, 101)
        assert proof
        assert consume.await_args is not None
        assert consume.await_args.kwargs["ceremony"] == "account_merge"
        column_length = cast(String, WebAuthnChallenge.__table__.c.ceremony.type).length
        assert column_length is not None
        assert len(consume.await_args.kwargs["ceremony"]) <= column_length
        assert consume.await_args.kwargs["user_id"] == 101
        if owner_id == 101:
            assert proofs.MERGE_COOKIE in response.cookies
            verify.assert_called_once()
        else:
            verify.assert_not_called()
        assert "rw_webapp_session" not in response.cookies

    asyncio.run(scenario())


def test_passkey_from_another_merge_attempt_is_rejected_before_consumption() -> None:
    async def scenario() -> None:
        request = _request("discord")
        request.app["settings"].PASSKEY_LOGIN_ENABLED = True
        api = Mock()
        with (
            patch.object(passkeys, "_require_user_id", return_value=101),
            patch.object(
                passkeys,
                "_parse_model_payload",
                AsyncMock(return_value=SimpleNamespace(challenge="AQID")),
            ),
            patch.object(passkeys, "_webauthn", api),
        ):
            response = await passkeys.account_merge_passkey_verify_route(request)
        assert response.status == 400
        api.assert_not_called()
        assert proofs.MERGE_COOKIE not in response.cookies

    asyncio.run(scenario())
