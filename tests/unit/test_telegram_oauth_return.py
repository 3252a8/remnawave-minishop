import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from aiohttp import web

from bot.app.web.webapp import auth_oauth
from bot.app.web.webapp.auth_common import _telegram_oauth_redirect_url
from bot.app.web.webapp_auth import create_webapp_session_token, verify_webapp_session_token


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        TELEGRAM_ENABLED=True,
        TELEGRAM_LOGIN_ENABLED=True,
        BOT_TOKEN="42:secret",
        TELEGRAM_OAUTH_CLIENT_ID=42,
        TELEGRAM_OAUTH_CLIENT_SECRET="client-secret",
        TELEGRAM_OAUTH_REQUEST_ACCESS="write",
        WEBAPP_LOGIN_TOKEN_TTL_SECONDS=600,
        WEBAPP_SESSION_SECRET="session-secret",
        WEBAPP_SESSION_TTL_SECONDS=3600,
        WEBAPP_AUTH_MAX_AGE_SECONDS=3600,
        SUBSCRIPTION_MINI_APP_URL="https://app.example.test/",
    )


def _request(settings: SimpleNamespace, *, user_id: int = -100) -> SimpleNamespace:
    return SimpleNamespace(
        app={"settings": settings},
        query={"purpose": "link"},
        headers={},
        cookies={"rw_webapp_session": create_webapp_session_token(settings, user_id)},
    )


@pytest.mark.parametrize("failure", ["not_configured", "disabled"])
def test_link_start_failure_returns_to_security(failure: str) -> None:
    settings = _settings()
    if failure == "disabled":
        settings.TELEGRAM_LOGIN_ENABLED = False
    else:
        settings.TELEGRAM_OAUTH_CLIENT_SECRET = None
    with pytest.raises(web.HTTPFound) as raised:
        asyncio.run(auth_oauth.telegram_oauth_start_route(_request(settings)))
    assert raised.value.location == f"/settings/security?telegram_auth={failure}"


def test_link_callback_round_trips_signed_state_and_keeps_email_account() -> None:
    settings = _settings()
    request = _request(settings)
    with pytest.raises(web.HTTPFound) as started:
        asyncio.run(auth_oauth.telegram_oauth_start_route(request))
    query = parse_qs(urlsplit(str(started.value.location)).query)
    request.cookies["rw_tg_oauth_state"] = started.value.cookies["rw_tg_oauth_state"].value
    request.query = {"state": query["state"][0], "code": "authorization-code"}
    user = SimpleNamespace(user_id=-100, telegram_id=42, panel_user_uuid=None, is_banned=False)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = session
    with (
        patch.object(auth_oauth, "get_session_factory", return_value=lambda: context),
        patch.object(auth_oauth.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
        patch.object(
            auth_oauth, "_exchange_telegram_oauth_code", AsyncMock(return_value={"id_token": "jwt"})
        ),
        patch.object(
            auth_oauth, "validate_telegram_oauth_id_token", AsyncMock(return_value={"id": 42})
        ) as validate,
        patch.object(auth_oauth, "_link_telegram_to_user", AsyncMock(return_value=user)) as link,
        patch.object(
            auth_oauth, "_grant_deferred_referral_welcome_bonus_after_telegram_link", AsyncMock()
        ),
        patch.object(auth_oauth, "_invalidate_webapp_user_caches", AsyncMock()),
        patch.object(auth_oauth, "_probe_telegram_notifications_for_user_id", AsyncMock()),
        pytest.raises(web.HTTPFound) as finished,
    ):
        asyncio.run(auth_oauth.telegram_oauth_callback_route(request))
    assert finished.value.location == "/settings/security?telegram_auth=success"
    link.assert_awaited_once_with(
        request,
        session,
        current_user_id=-100,
        telegram_user={"id": 42},
        settings=settings,
        merge_reason="telegram_link",
    )
    session.commit.assert_awaited_once()
    assert validate.await_args is not None
    assert validate.await_args.kwargs["expected_nonce"] == query["nonce"][0]
    token = finished.value.cookies["rw_webapp_session"].value
    assert verify_webapp_session_token(settings, token) == -100
    assert finished.value.cookies["rw_tg_oauth_state"]["max-age"] == "0"


@pytest.mark.parametrize("state_failure", ["missing", "tampered", "mismatch"])
def test_invalid_state_returns_to_authenticated_security_without_linking(
    state_failure: str,
) -> None:
    settings = _settings()
    request = _request(settings)
    with pytest.raises(web.HTTPFound) as started:
        asyncio.run(auth_oauth.telegram_oauth_start_route(request))
    query = parse_qs(urlsplit(str(started.value.location)).query)
    cookie = started.value.cookies["rw_tg_oauth_state"].value
    if state_failure != "missing":
        request.cookies["rw_tg_oauth_state"] = cookie + (
            "tampered" if state_failure == "tampered" else ""
        )
    request.query = {
        "state": query["state"][0] + ("x" if state_failure == "mismatch" else ""),
        "code": "code",
    }
    with (
        patch.object(auth_oauth, "_exchange_telegram_oauth_code", AsyncMock()) as exchange,
        patch.object(auth_oauth, "_link_telegram_to_user", AsyncMock()) as link,
        pytest.raises(web.HTTPFound) as raised,
    ):
        asyncio.run(auth_oauth.telegram_oauth_callback_route(request))
    assert raised.value.location == "/settings/security?telegram_auth=invalid_state"
    exchange.assert_not_awaited()
    link.assert_not_awaited()


def test_security_redirect_allowlist_rejects_external_urls() -> None:
    assert _telegram_oauth_redirect_url("/settings/security", status="success") == (
        "/settings/security?telegram_auth=success"
    )
    assert _telegram_oauth_redirect_url("//other.test/settings/security") == "/"
    assert _telegram_oauth_redirect_url("/settings/security/../../other") == "/"
