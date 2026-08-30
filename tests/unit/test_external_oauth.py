import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import web

from bot.app.web.webapp import external_oauth


class _ScalarResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _SessionFactory:
    def __init__(self) -> None:
        self.session = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult()),
            add=Mock(),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )

    def __call__(self):
        session = self.session

        class _Context:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return _Context()


def _provider(key: str = "google") -> external_oauth.ExternalProvider:
    return external_oauth.ExternalProvider(
        key=key,
        authorization_url="https://accounts.example/authorize",
        token_url="https://accounts.example/token",
        client_id="client",
        client_secret="secret",
        scopes=("openid", "email"),
    )


def _request(*, purpose: str, user_id: int | None = None, provider: str = "google"):
    state: dict[str, object] = {
        "provider": provider,
        "purpose": purpose,
        "state": "state",
        "verifier": "verifier",
        "nonce": "nonce",
    }
    if user_id is not None:
        state["user_id"] = user_id
    return (
        SimpleNamespace(
            match_info={"provider": provider},
            query={"code": "oauth-code"},
            cookies={},
        ),
        state,
    )


def _profile() -> dict[str, object]:
    return {
        "subject": "google-subject",
        "email": "same@example.com",
        "email_verified": True,
        "display_name": "Example User",
        "picture_url": None,
    }


async def _login_with_claimed_oidc_email_requires_confirmation_without_duplicate() -> None:
    for provider_key in ("google", "yandex"):
        factory = _SessionFactory()
        request, state = _request(purpose="login", provider=provider_key)
        existing = SimpleNamespace(
            user_id=41,
            is_banned=False,
            language_code="ru",
            email="same@example.com",
            email_verified_at=object(),
            notification_email="same@example.com",
        )
        create_email_user = AsyncMock()
        request_code = AsyncMock(
            return_value=SimpleNamespace(ok=True, error=None, retry_after=None, code=None)
        )
        ensure_primary = AsyncMock()
        set_pending_cookie = Mock()

        with (
            patch.object(
                external_oauth,
                "get_settings",
                return_value=SimpleNamespace(
                    DEFAULT_LANGUAGE="ru",
                    EMAIL_CODE_RESEND_SECONDS=60,
                ),
            ),
            patch.object(external_oauth, "get_session_factory", return_value=factory),
            patch.object(
                external_oauth,
                "get_email_auth_service",
                return_value=SimpleNamespace(request_code=request_code),
            ),
            patch.object(external_oauth, "_provider", return_value=_provider(provider_key)),
            patch.object(external_oauth, "_read_state", return_value=state),
            patch.object(external_oauth, "_callback_url", return_value="https://app/callback"),
            patch.object(external_oauth, "_post_token", AsyncMock(return_value={"id_token": "x"})),
            patch.object(external_oauth, "_google_profile", AsyncMock(return_value=_profile())),
            patch.object(external_oauth, "_yandex_profile", AsyncMock(return_value=_profile())),
            patch.object(external_oauth, "_verified_email_owner", AsyncMock(return_value=existing)),
            patch.object(
                external_oauth.user_email_dal, "ensure_primary_user_email_address", ensure_primary
            ),
            patch.object(external_oauth.user_dal, "create_email_user", create_email_user),
            patch.object(external_oauth, "_set_pending_cookie", set_pending_cookie),
        ):
            response = await external_oauth.external_oauth_callback_route(request)

        assert response.headers["Location"] == (
            f"/?external_auth={provider_key}:email_confirmation_required"
        )
        request_code.assert_awaited_once_with(
            factory.session,
            email="same@example.com",
            purpose="external_oauth_link",
            language_code="ru",
            target_user_id=41,
        )
        ensure_primary.assert_awaited_once_with(factory.session, existing)
        create_email_user.assert_not_awaited()
        set_pending_cookie.assert_called_once()
        factory.session.commit.assert_awaited_once()


def test_login_with_claimed_oidc_email_requires_confirmation_without_duplicate() -> None:
    asyncio.run(_login_with_claimed_oidc_email_requires_confirmation_without_duplicate())


async def _authenticated_provider_link_merges_claimed_email_before_linking() -> None:
    factory = _SessionFactory()
    request, state = _request(purpose="link", user_id=42)
    source = SimpleNamespace(user_id=-41)
    target = SimpleNamespace(
        user_id=42,
        is_banned=False,
        email="primary@example.com",
        email_verified_at=object(),
        notification_email="primary@example.com",
        first_name="Target",
    )
    merge_users = AsyncMock(return_value=target)
    upsert_address = AsyncMock()

    with (
        patch.object(external_oauth, "get_settings", return_value=SimpleNamespace()),
        patch.object(external_oauth, "get_session_factory", return_value=factory),
        patch.object(external_oauth, "_provider", return_value=_provider()),
        patch.object(external_oauth, "_read_state", return_value=state),
        patch.object(external_oauth, "_callback_url", return_value="https://app/callback"),
        patch.object(external_oauth, "_post_token", AsyncMock(return_value={"id_token": "x"})),
        patch.object(external_oauth, "_google_profile", AsyncMock(return_value=_profile())),
        patch.object(external_oauth, "_extract_authenticated_user_id", return_value=42),
        patch.object(
            external_oauth.user_email_dal,
            "get_user_by_verified_email_address",
            AsyncMock(return_value=source),
        ),
        patch.object(external_oauth.user_dal, "merge_users", merge_users),
        patch.object(
            external_oauth.user_dal,
            "get_user_by_id",
            AsyncMock(return_value=target),
        ),
        patch.object(
            external_oauth.user_email_dal,
            "upsert_user_email_address",
            upsert_address,
        ),
        patch.object(
            external_oauth,
            "_sync_panel_identity_for_user",
            AsyncMock(),
        ),
        patch.object(
            external_oauth,
            "_invalidate_webapp_user_caches",
            AsyncMock(),
        ),
        patch.object(external_oauth, "create_webapp_session_token", return_value="token"),
        patch.object(external_oauth, "_set_webapp_auth_cookies"),
    ):
        response = await external_oauth.external_oauth_callback_route(request)

    assert response.headers["Location"] == "/settings/security?external_auth=google:success"
    merge_users.assert_awaited_once_with(
        factory.session,
        source_user_id=-41,
        target_user_id=42,
        reason="google_verified_email_link",
        send_user_email=True,
    )
    upsert_address.assert_awaited_once()
    factory.session.commit.assert_awaited_once()


def test_authenticated_provider_link_merges_claimed_email_before_linking() -> None:
    asyncio.run(_authenticated_provider_link_merges_claimed_email_before_linking())


async def _provider_link_merges_distinct_identity_and_email_owners() -> None:
    factory = _SessionFactory()
    identity_owner = SimpleNamespace(user_id=-70)
    email_owner = SimpleNamespace(user_id=-71)
    identity = SimpleNamespace(
        user_id=identity_owner.user_id,
        subject="google-subject",
        email=None,
        email_verified=False,
        display_name=None,
        picture_url=None,
        last_used_at=None,
    )
    factory.session.execute = AsyncMock(side_effect=[_ScalarResult(identity), _ScalarResult(None)])
    request, state = _request(purpose="link", user_id=42)
    target = SimpleNamespace(
        user_id=42,
        is_banned=False,
        email="primary@example.com",
        email_verified_at=object(),
        notification_email="primary@example.com",
        first_name="Target",
    )
    merge_users = AsyncMock(return_value=target)

    with (
        patch.object(external_oauth, "get_settings", return_value=SimpleNamespace()),
        patch.object(external_oauth, "get_session_factory", return_value=factory),
        patch.object(external_oauth, "_provider", return_value=_provider()),
        patch.object(external_oauth, "_read_state", return_value=state),
        patch.object(external_oauth, "_callback_url", return_value="https://app/callback"),
        patch.object(external_oauth, "_post_token", AsyncMock(return_value={"id_token": "x"})),
        patch.object(external_oauth, "_google_profile", AsyncMock(return_value=_profile())),
        patch.object(external_oauth, "_extract_authenticated_user_id", return_value=42),
        patch.object(
            external_oauth.user_email_dal,
            "get_user_by_verified_email_address",
            AsyncMock(return_value=email_owner),
        ),
        patch.object(external_oauth.user_dal, "merge_users", merge_users),
        patch.object(external_oauth.user_dal, "get_user_by_id", AsyncMock(return_value=target)),
        patch.object(
            external_oauth.user_email_dal,
            "upsert_user_email_address",
            AsyncMock(),
        ),
        patch.object(external_oauth, "_sync_panel_identity_for_user", AsyncMock()),
        patch.object(external_oauth, "_invalidate_webapp_user_caches", AsyncMock()),
        patch.object(external_oauth, "create_webapp_session_token", return_value="token"),
        patch.object(external_oauth, "_set_webapp_auth_cookies"),
    ):
        response = await external_oauth.external_oauth_callback_route(request)

    assert response.headers["Location"] == "/settings/security?external_auth=google:success"
    assert [call.kwargs["source_user_id"] for call in merge_users.await_args_list] == [-71, -70]
    assert identity.user_id == 42
    factory.session.commit.assert_awaited_once()


def test_provider_link_merges_distinct_identity_and_email_owners() -> None:
    asyncio.run(_provider_link_merges_distinct_identity_and_email_owners())


async def _confirmed_email_attaches_provider_to_existing_account() -> None:
    for provider_key in ("google", "yandex"):
        factory = _SessionFactory()
        user = SimpleNamespace(
            user_id=41,
            is_banned=False,
            first_name="",
            telegram_id=None,
        )
        pending = {
            "provider": provider_key,
            "subject": f"{provider_key}-subject",
            "email": "secondary@example.com",
            "target_user_id": 41,
            "display_name": "Example User",
            "picture_url": "",
            "referral": "",
        }
        verify_code = AsyncMock(return_value=SimpleNamespace(ok=True, error=None, retry_after=None))
        upsert_address = AsyncMock()

        with (
            patch.object(
                external_oauth,
                "get_settings",
                return_value=SimpleNamespace(qa_auth_enabled=False),
            ),
            patch.object(external_oauth, "_read_pending", return_value=pending),
            patch.object(external_oauth, "_provider", return_value=_provider(provider_key)),
            patch.object(external_oauth, "get_session_factory", return_value=factory),
            patch.object(
                external_oauth,
                "get_email_auth_service",
                return_value=SimpleNamespace(verify_code=verify_code),
            ),
            patch.object(
                external_oauth,
                "_parse_model_payload",
                AsyncMock(return_value=SimpleNamespace(code="123456")),
            ),
            patch.object(
                external_oauth,
                "_pending_target",
                AsyncMock(return_value=(user, None, None)),
            ),
            patch.object(
                external_oauth.user_email_dal,
                "upsert_user_email_address",
                upsert_address,
            ),
            patch.object(
                external_oauth,
                "_apply_referral_to_existing_user",
                AsyncMock(return_value=False),
            ),
            patch.object(external_oauth, "_sync_panel_identity_for_user", AsyncMock()),
            patch.object(external_oauth, "_invalidate_webapp_user_caches", AsyncMock()),
            patch.object(external_oauth, "create_webapp_session_token", return_value="token"),
            patch.object(
                external_oauth,
                "_build_webapp_auth_response",
                return_value=web.json_response({"ok": True}),
            ),
            patch.object(external_oauth, "_clear_pending_cookie"),
        ):
            response = await external_oauth.external_oauth_pending_verify_route(
                SimpleNamespace(cookies={})
            )

        assert response.status == 200
        verify_code.assert_awaited_once_with(
            factory.session,
            email="secondary@example.com",
            purpose="external_oauth_link",
            code="123456",
            target_user_id=41,
        )
        identity = factory.session.add.call_args.args[0]
        assert identity.provider == provider_key
        assert identity.subject == f"{provider_key}-subject"
        assert identity.user_id == 41
        upsert_address.assert_awaited_once()
        factory.session.commit.assert_awaited_once()


def test_confirmed_email_attaches_google_and_yandex_to_existing_account() -> None:
    asyncio.run(_confirmed_email_attaches_provider_to_existing_account())


async def _pending_target_rejects_identity_owned_by_another_account() -> None:
    factory = _SessionFactory()
    target = SimpleNamespace(user_id=41, is_banned=False)
    email_owner = SimpleNamespace(user_id=41)
    conflicting_identity = SimpleNamespace(user_id=99)
    factory.session.execute = AsyncMock(return_value=_ScalarResult(conflicting_identity))
    pending = {
        "provider": "google",
        "subject": "google-subject",
        "email": "same@example.com",
        "target_user_id": 41,
    }

    with (
        patch.object(external_oauth.user_dal, "lock_user_by_id", AsyncMock(return_value=target)),
        patch.object(
            external_oauth,
            "_verified_email_owner",
            AsyncMock(return_value=email_owner),
        ),
    ):
        user, identity, error = await external_oauth._pending_target(
            factory.session, pending, lock=True
        )

    assert user is None
    assert identity is None
    assert error == "identity_conflict"


def test_pending_target_rejects_identity_owned_by_another_account() -> None:
    asyncio.run(_pending_target_rejects_identity_owned_by_another_account())
