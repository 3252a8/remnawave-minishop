import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.app.web.context import SETTINGS, initialize_webapp_runtime_context
from bot.app.web.webapp.constants import WEBAPP_CSRF_COOKIE_NAME, WEBAPP_SESSION_COOKIE_NAME
from bot.app.web.webapp.routes import setup_subscription_webapp_routes
from bot.app.web.webapp_auth import verify_webapp_session_token
from bot.plugins.extensions import ExtensionContributions, ExtensionError, LoginProvider
from bot.plugins.extensions import auth as plugin_auth
from bot.plugins.extensions.registry import ExtensionRegistry, get_registry, set_registry
from config.settings import Settings


def test_public_plugin_login_uses_core_session_and_hides_stale_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        BOT_TOKEN="123:test",
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        TELEGRAM_LOGIN_ENABLED=False,
        PASSKEY_LOGIN_ENABLED=False,
        QR_LOGIN_ENABLED=False,
        WEBAPP_SESSION_SECRET="plugin-test-session",
        SUBSCRIPTION_MINI_APP_URL="https://shop.example/cabinet/",
        _env_file=None,
    )
    generation_current = True
    monkeypatch.setattr(plugin_auth, "generation_is_current", lambda: generation_current)
    monkeypatch.setattr(plugin_auth, "get_session_factory", MagicMock())
    user_lookup = AsyncMock(return_value=SimpleNamespace(is_banned=False))
    monkeypatch.setattr(plugin_auth.user_dal, "get_user_by_id", user_lookup)
    previous_registry = get_registry()
    registry = ExtensionRegistry()

    async def start(request: web.Request) -> web.Response:
        assert request.query["lang"] == "en"
        raise web.HTTPFound("https://sso.example/authorize")

    async def callback(request: web.Request) -> web.Response:
        response = await plugin_auth.complete_login(
            request, owner="work", provider="sso", user_id=42
        )
        assert isinstance(response, web.Response)
        return response

    registry.register(
        "work",
        "1",
        ExtensionContributions(login_providers=(LoginProvider("sso", "Work SSO", start),)),
    )

    async def scenario() -> None:
        nonlocal generation_current
        app = web.Application()
        app[SETTINGS] = settings
        initialize_webapp_runtime_context(app)
        setup_subscription_webapp_routes(app)
        app.router.add_get("/auth/plugins/work/sso/callback", callback)
        async with TestClient(TestServer(app)) as client:
            bootstrap = await client.get("/api/bootstrap")
            assert bootstrap.status == 200
            assert bootstrap.headers["Cache-Control"] == "private, no-cache"
            active_etag = bootstrap.headers["ETag"]
            config = (await bootstrap.json())["config"]
            assert config["authProviders"] == []
            assert config["pluginLoginProviders"] == [
                {
                    "id": "work:sso",
                    "name": "Work SSO",
                    "startPath": "/cabinet/auth/plugins/work/sso/start",
                }
            ]

            # The production reverse proxy strips the public cabinet prefix.
            path = config["pluginLoginProviders"][0]["startPath"].removeprefix("/cabinet")
            started = await client.get(f"{path}?lang=en", allow_redirects=False)
            assert started.status == 302
            assert started.headers["Location"] == "https://sso.example/authorize"
            assert started.headers["Cache-Control"] == "no-store"
            unknown = await client.get("/auth/plugins/work/unknown/start", allow_redirects=False)
            assert unknown.status == 404

            callback_path = "/auth/plugins/work/sso/callback"
            completed = await client.get(callback_path, allow_redirects=False)
            assert completed.status == 303
            location = urlsplit(completed.headers["Location"])
            assert location.path == "/cabinet/"
            assert parse_qs(location.query) == {"external_auth": ["work/sso:success"]}
            assert completed.headers["Cache-Control"] == "no-store"
            session = completed.cookies[WEBAPP_SESSION_COOKIE_NAME]
            assert session["httponly"] and session["secure"]
            assert verify_webapp_session_token(settings, session.value) == 42
            assert completed.cookies[WEBAPP_CSRF_COOKIE_NAME].value

            user_lookup.return_value.is_banned = True
            denied = await client.get(callback_path, allow_redirects=False)
            assert denied.status == 403 and not denied.cookies

            generation_current = False
            assert (await client.get(path, allow_redirects=False)).status == 503
            assert (await client.get(callback_path, allow_redirects=False)).status == 503
            bootstrap = await client.get("/api/bootstrap", headers={"If-None-Match": active_etag})
            assert bootstrap.status == 200 and bootstrap.headers["ETag"] != active_etag
            assert (await bootstrap.json())["config"]["pluginLoginProviders"] == []

    set_registry(registry)
    try:
        asyncio.run(scenario())
    finally:
        set_registry(previous_registry)


def test_plugin_login_provider_requires_plain_name_and_unique_id() -> None:
    registry = ExtensionRegistry()
    handler = AsyncMock()
    with pytest.raises(ExtensionError, match="invalid_extension_login_provider"):
        registry.register(
            "work",
            "1",
            ExtensionContributions(login_providers=(LoginProvider("sso", " ", handler),)),
        )
    provider = LoginProvider("sso", "Work SSO", handler)
    with pytest.raises(ExtensionError, match="duplicate_extension_identifier"):
        registry.register("work", "1", ExtensionContributions(login_providers=(provider, provider)))
    assert not registry.owners()
