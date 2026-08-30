import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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


def _provider() -> external_oauth.ExternalProvider:
    return external_oauth.ExternalProvider(
        key="google",
        authorization_url="https://accounts.example/authorize",
        token_url="https://accounts.example/token",
        client_id="client",
        client_secret="secret",
        scopes=("openid", "email"),
    )


def _request(*, purpose: str, user_id: int | None = None):
    state: dict[str, object] = {
        "provider": "google",
        "purpose": purpose,
        "state": "state",
        "verifier": "verifier",
        "nonce": "nonce",
    }
    if user_id is not None:
        state["user_id"] = user_id
    return (
        SimpleNamespace(
            match_info={"provider": "google"},
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


async def _login_with_claimed_oidc_email_does_not_create_duplicate_user() -> None:
    factory = _SessionFactory()
    request, state = _request(purpose="login")
    existing = SimpleNamespace(user_id=41)
    create_email_user = AsyncMock()

    with (
        patch.object(external_oauth, "get_settings", return_value=SimpleNamespace()),
        patch.object(external_oauth, "get_session_factory", return_value=factory),
        patch.object(external_oauth, "_provider", return_value=_provider()),
        patch.object(external_oauth, "_read_state", return_value=state),
        patch.object(external_oauth, "_callback_url", return_value="https://app/callback"),
        patch.object(external_oauth, "_post_token", AsyncMock(return_value={"id_token": "x"})),
        patch.object(external_oauth, "_google_profile", AsyncMock(return_value=_profile())),
        patch.object(
            external_oauth.user_email_dal,
            "get_user_by_verified_email_address",
            AsyncMock(return_value=existing),
        ),
        patch.object(external_oauth.user_dal, "create_email_user", create_email_user),
    ):
        response = await external_oauth.external_oauth_callback_route(request)

    assert response.headers["Location"] == "/?external_auth=google:account_exists"
    create_email_user.assert_not_awaited()
    factory.session.commit.assert_not_awaited()


def test_login_with_claimed_oidc_email_does_not_create_duplicate_user() -> None:
    asyncio.run(_login_with_claimed_oidc_email_does_not_create_duplicate_user())


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
