import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import account as account_module


class _JsonRequest(SimpleNamespace):
    async def json(self):
        return self.payload


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class WebAppAccountLanguageTests(IsolatedAsyncioTestCase):
    async def test_account_language_route_updates_language_and_invalidates_cache(self):
        settings = SimpleNamespace()
        session = SimpleNamespace(
            flush=AsyncMock(),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        user = SimpleNamespace(user_id=42, language_code="ru", is_banned=False)
        i18n = SimpleNamespace(
            locales_data={"ru": {}, "en": {}},
            reload_overrides_from_file=Mock(),
        )
        request = _JsonRequest(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(session),
                "i18n": i18n,
            },
            payload={"language": "en"},
        )

        with (
            patch.object(account_module, "_require_user_id", return_value=42),
            patch.object(
                account_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch.object(
                account_module,
                "_invalidate_webapp_user_caches",
                AsyncMock(),
            ) as invalidate_cache,
        ):
            response = await account_module.account_language_route(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text), {"ok": True, "language": "en"})
        self.assertEqual(user.language_code, "en")
        i18n.reload_overrides_from_file.assert_called_once_with()
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        invalidate_cache.assert_awaited_once_with(settings, 42)
