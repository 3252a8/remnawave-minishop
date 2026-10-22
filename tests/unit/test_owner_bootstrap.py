import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import make_mocked_request
from pydantic import ValidationError

from bot.app.web.webapp import owner_bootstrap
from config.settings_auth import AuthenticationSettings


@pytest.mark.parametrize(
    "telegram_id,email", [("", ""), (None, None), ("777", " OWNER@EXAMPLE.COM ")]
)
def test_optional_owner_configuration_is_normalized(telegram_id, email):
    settings = AuthenticationSettings(
        _env_file=None, BOOTSTRAP_OWNER_TELEGRAM_ID=telegram_id, BOOTSTRAP_OWNER_EMAIL=email
    )
    assert (777 if telegram_id else None) == settings.BOOTSTRAP_OWNER_TELEGRAM_ID
    assert ("owner@example.com" if email else None) == settings.BOOTSTRAP_OWNER_EMAIL


@pytest.mark.parametrize(
    "configuration",
    [
        {"BOOTSTRAP_OWNER_TELEGRAM_ID": "0"},
        {"BOOTSTRAP_OWNER_TELEGRAM_ID": "-1"},
        {"BOOTSTRAP_OWNER_TELEGRAM_ID": "777,888"},
        {"BOOTSTRAP_OWNER_EMAIL": "owner"},
        {"BOOTSTRAP_OWNER_EMAIL": "a@b@c.com"},
    ],
)
def test_owner_configuration_rejects_invalid_identifiers(configuration):
    with pytest.raises(ValidationError):
        AuthenticationSettings(_env_file=None, **configuration)


@pytest.mark.parametrize(
    "user_id,configured,granted",
    [(1, True, True), (1, True, False), (None, True, False), (1, False, False)],
)
def test_authenticated_request_bootstraps_before_authorization(user_id, configured, granted):
    settings = SimpleNamespace(
        BOOTSTRAP_OWNER_TELEGRAM_ID=777 if configured else None,
        BOOTSTRAP_OWNER_EMAIL=None,
    )
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    grant = AsyncMock(return_value=granted)

    async def handler(request):
        if granted:
            session.commit.assert_awaited_once()
        return "response"

    with (
        patch.object(owner_bootstrap, "get_settings", return_value=settings),
        patch.object(owner_bootstrap, "get_session_factory", return_value=factory),
        patch.object(owner_bootstrap, "extract_authenticated_user_id", return_value=user_id),
        patch.object(owner_bootstrap, "bootstrap_configured_owner", grant),
    ):
        assert (
            asyncio.run(
                owner_bootstrap.owner_bootstrap_middleware(
                    make_mocked_request("GET", "/api/admin/stats"), handler
                )
            )
            == "response"
        )
    if user_id is not None and configured:
        grant.assert_awaited_once_with(session, user_id, telegram_id=777, email=None)
        assert session.commit.await_count == int(granted)
    else:
        factory.assert_not_called()
