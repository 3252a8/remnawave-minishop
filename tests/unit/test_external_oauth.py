import asyncio
import json
from types import SimpleNamespace
from typing import Literal
from unittest.mock import ANY, AsyncMock, Mock, call, patch
from urllib.parse import parse_qs, urlsplit

from aiohttp import web

from bot.app.web.webapp import external_identity_unlink, external_oauth


class _ScalarResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value


class _SessionFactory:
    def __init__(self) -> None:
        self.session = SimpleNamespace(
            execute=AsyncMock(return_value=_ScalarResult()),
            add=Mock(),
            delete=AsyncMock(),
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


def _provider(
    key: Literal["google", "yandex"] = "google",
) -> external_oauth.ExternalProvider:
    return external_oauth.ExternalProvider(
        key=key,
        authorization_url=(
            "https://oauth.yandex.com/authorize"
            if key == "yandex"
            else "https://accounts.example/authorize"
        ),
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
            app={},
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


async def _external_oauth_start_uses_application_language() -> None:
    for requested_language, expected_language, expected_host in (
        ("ru", "ru", "oauth.yandex.ru"),
        ("ru-RU", "ru-ru", "oauth.yandex.ru"),
        ("en", "en", "oauth.yandex.com"),
    ):
        request = SimpleNamespace(
            match_info={"provider": "yandex"},
            query={"lang": requested_language},
            cookies={},
        )
        set_state_cookie = Mock()
        with patch.multiple(
            external_oauth,
            get_settings=Mock(return_value=SimpleNamespace(DEFAULT_LANGUAGE="en")),
            _provider=Mock(return_value=_provider("yandex")),
            _extract_authenticated_user_id=Mock(return_value=None),
            _callback_url=Mock(return_value="https://app.example.com/auth/yandex/callback"),
            _set_state_cookie=set_state_cookie,
        ):
            response = await external_oauth.external_oauth_start_route(request)

        location = urlsplit(response.headers["Location"])
        query = parse_qs(location.query)
        assert location.netloc == expected_host
        assert query["client_id"] == ["client"]
        assert set_state_cookie.call_args.args[2]["language"] == expected_language


def test_external_oauth_start_uses_application_language() -> None:
    asyncio.run(_external_oauth_start_uses_application_language())


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


async def _new_oidc_registration_emits_provider_registration_after_commit() -> None:
    for provider_key in ("google", "yandex"):
        factory = _SessionFactory()
        request, state = _request(purpose="login", provider=provider_key)
        state["language"] = "ru"
        user = SimpleNamespace(
            user_id=-42,
            is_banned=False,
            language_code="ru",
            referred_by_id=7,
            telegram_id=None,
            username=None,
            first_name="Example User",
            email="same@example.com",
            notification_email="same@example.com",
        )
        create_email_user = AsyncMock(return_value=(user, True))
        emit_model = AsyncMock()
        apply_referral = AsyncMock(return_value=False)
        apply_welcome_bonus = AsyncMock()

        with (
            patch.multiple(
                external_oauth,
                get_settings=Mock(return_value=SimpleNamespace(DEFAULT_LANGUAGE="en")),
                get_session_factory=Mock(return_value=factory),
                _provider=Mock(return_value=_provider(provider_key)),
                _read_state=Mock(return_value=state),
                _callback_url=Mock(return_value="https://app/callback"),
                _post_token=AsyncMock(return_value={"id_token": "x"}),
                _google_profile=AsyncMock(return_value=_profile()),
                _yandex_profile=AsyncMock(return_value=_profile()),
                _verified_email_owner=AsyncMock(return_value=None),
                evaluate_registration_invite=AsyncMock(
                    return_value=SimpleNamespace(
                        requires_invite=False,
                        referrer_user_id=7,
                        partner_code=None,
                    )
                ),
                _apply_referral_to_existing_user=apply_referral,
                _apply_referral_welcome_bonus_if_needed=apply_welcome_bonus,
                _sync_panel_identity_for_user=AsyncMock(),
                _invalidate_webapp_user_caches=AsyncMock(),
                create_webapp_session_token=Mock(return_value="token"),
                _set_webapp_auth_cookies=Mock(),
            ),
            patch.multiple(
                external_oauth.user_dal,
                get_user_by_email=AsyncMock(return_value=None),
                create_email_user=create_email_user,
                get_user_by_id=AsyncMock(return_value=user),
            ),
            patch.multiple(
                external_oauth.user_email_dal,
                upsert_user_email_address=AsyncMock(),
            ),
            patch.object(external_oauth.events, "emit_model", emit_model),
        ):
            response = await external_oauth.external_oauth_callback_route(request)

        assert response.headers["Location"] == f"/?external_auth={provider_key}:success"
        create_email_user.assert_awaited_once_with(
            factory.session,
            email="same@example.com",
            language_code="ru",
            email_verified_at=ANY,
            referred_by_id=7,
            registered_via=None,
            email_source=provider_key,
        )
        factory.session.commit.assert_awaited_once()
        apply_referral.assert_awaited_once_with(
            request,
            factory.session,
            user,
            "",
        )
        apply_welcome_bonus.assert_awaited_once_with(
            request,
            factory.session,
            user,
            "",
        )
        assert emit_model.await_args is not None
        payload = emit_model.await_args.args[0]
        assert payload.registered_via == f"{provider_key}_oauth"
        assert payload.user_id == -42
        assert payload.email == "same@example.com"


def test_new_oidc_registration_emits_provider_registration_after_commit() -> None:
    asyncio.run(_new_oidc_registration_emits_provider_registration_after_commit())


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
    emit_model = AsyncMock()

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
        patch.object(external_oauth.events, "emit_model", emit_model),
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
        cancel_source_recurring=ANY,
    )
    upsert_address.assert_awaited_once()
    factory.session.commit.assert_awaited_once()
    assert emit_model.await_args is not None
    payload = emit_model.await_args.args[0]
    assert payload.provider == "google"
    assert payload.link_source == "settings"
    assert payload.user_id == 42
    assert payload.email == "same@example.com"


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
        emit_model = AsyncMock()

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
            patch.object(external_oauth.events, "emit_model", emit_model),
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
        assert emit_model.await_args is not None
        payload = emit_model.await_args.args[0]
        assert payload.provider == provider_key
        assert payload.link_source == "email_confirmation"
        assert payload.user_id == 41


def test_confirmed_email_attaches_google_and_yandex_to_existing_account() -> None:
    asyncio.run(_confirmed_email_attaches_provider_to_existing_account())


async def _unlink_provider_replaces_provider_owned_primary_email() -> None:
    factory = _SessionFactory()
    verified_at = object()
    identity = SimpleNamespace(
        provider="google",
        email="google@example.test",
        email_verified=True,
    )
    provider_address = SimpleNamespace(
        email="google@example.test",
        source="google",
        verified_at=verified_at,
        is_primary=True,
        is_notification=True,
    )
    replacement = SimpleNamespace(
        email="other@example.test",
        source="email",
        verified_at=verified_at,
        is_primary=False,
        is_notification=False,
    )
    user = SimpleNamespace(
        user_id=42,
        is_banned=False,
        email="google@example.test",
        email_verified_at=verified_at,
        notification_email="google@example.test",
        telegram_id=None,
    )
    factory.session.execute = AsyncMock(side_effect=[_ScalarResult([identity]), _ScalarResult(0)])
    upsert_address = AsyncMock()
    sync_panel = AsyncMock()
    invalidate = AsyncMock()

    with (
        patch.object(external_identity_unlink, "_extract_authenticated_user_id", return_value=42),
        patch.object(
            external_identity_unlink,
            "get_settings",
            return_value=SimpleNamespace(
                webapp_auth_providers=["email", "google"],
                PASSKEY_LOGIN_ENABLED=False,
                TELEGRAM_LOGIN_ENABLED=False,
                email_auth_configured=True,
            ),
        ),
        patch.object(external_identity_unlink, "get_session_factory", return_value=factory),
        patch.object(
            external_identity_unlink,
            "_parse_model_payload",
            AsyncMock(return_value=SimpleNamespace(provider="google")),
        ),
        patch.object(
            external_identity_unlink.user_dal,
            "lock_user_by_id",
            AsyncMock(return_value=user),
        ),
        patch.object(
            external_identity_unlink.user_email_dal,
            "ensure_primary_user_email_address",
            AsyncMock(),
        ),
        patch.object(
            external_identity_unlink.user_email_dal,
            "list_user_email_addresses",
            AsyncMock(return_value=[provider_address, replacement]),
        ),
        patch.object(
            external_identity_unlink.user_email_dal,
            "upsert_user_email_address",
            upsert_address,
        ),
        patch.object(external_identity_unlink, "_sync_panel_identity_for_user", sync_panel),
        patch.object(external_identity_unlink, "_invalidate_webapp_user_caches", invalidate),
    ):
        response = await external_identity_unlink.external_identity_unlink_route(SimpleNamespace())

    assert response.status == 200
    assert user.email == "other@example.test"
    assert user.notification_email == "other@example.test"
    upsert_address.assert_awaited_once_with(
        factory.session,
        user_id=42,
        email="other@example.test",
        source="email",
        verified_at=verified_at,
        is_primary=True,
        is_notification=True,
    )
    assert factory.session.delete.await_args_list == [
        call(provider_address),
        call(identity),
    ]
    sync_panel.assert_awaited_once_with(ANY, user)
    factory.session.commit.assert_awaited_once()
    invalidate.assert_awaited_once_with(ANY, 42)


def test_unlink_provider_replaces_provider_owned_primary_email() -> None:
    asyncio.run(_unlink_provider_replaces_provider_owned_primary_email())


async def _unlink_provider_requires_an_independent_email() -> None:
    factory = _SessionFactory()
    identity = SimpleNamespace(
        provider="google",
        email="google@example.test",
        email_verified=True,
    )
    provider_address = SimpleNamespace(
        email="google@example.test",
        source="google",
        verified_at=object(),
        is_primary=True,
        is_notification=True,
    )
    user = SimpleNamespace(
        user_id=42,
        is_banned=False,
        email="google@example.test",
        email_verified_at=object(),
        notification_email="google@example.test",
        telegram_id=100,
    )
    factory.session.execute = AsyncMock(side_effect=[_ScalarResult([identity]), _ScalarResult(0)])

    with (
        patch.object(external_identity_unlink, "_extract_authenticated_user_id", return_value=42),
        patch.object(
            external_identity_unlink,
            "get_settings",
            return_value=SimpleNamespace(
                webapp_auth_providers=["telegram", "google"],
                PASSKEY_LOGIN_ENABLED=False,
                TELEGRAM_LOGIN_ENABLED=True,
                email_auth_configured=False,
            ),
        ),
        patch.object(external_identity_unlink, "get_session_factory", return_value=factory),
        patch.object(
            external_identity_unlink,
            "_parse_model_payload",
            AsyncMock(return_value=SimpleNamespace(provider="google")),
        ),
        patch.object(
            external_identity_unlink.user_dal,
            "lock_user_by_id",
            AsyncMock(return_value=user),
        ),
        patch.object(
            external_identity_unlink.user_email_dal,
            "ensure_primary_user_email_address",
            AsyncMock(),
        ),
        patch.object(
            external_identity_unlink.user_email_dal,
            "list_user_email_addresses",
            AsyncMock(return_value=[provider_address]),
        ),
    ):
        response = await external_identity_unlink.external_identity_unlink_route(SimpleNamespace())

    assert response.status == 409
    assert json.loads(response.text) == {
        "ok": False,
        "error": "replacement_email_required",
    }
    factory.session.delete.assert_not_awaited()
    factory.session.commit.assert_not_awaited()


def test_unlink_provider_requires_an_independent_email() -> None:
    asyncio.run(_unlink_provider_requires_an_independent_email())


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
