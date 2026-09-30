from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.app.web import session as web_session
from bot.app.web.webapp import theme_effects
from tests.support.settings_stub import settings_stub
from tests.unit.test_theme_effects import install_effect, permit
from tests.unit.test_theme_package_api import client_context


@pytest.mark.parametrize("admin_effects_enabled", [False, True])
def test_user_asset_requires_current_consent_and_admin_runtime_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, admin_effects_enabled: bool
) -> None:
    digest = install_effect(tmp_path, allow=True)
    settings = settings_stub(
        WEBAPP_THEMES_DIR=str(tmp_path),
        WEBAPP_DEFAULT_THEME="ocean",
        WEBAPP_PRIMARY_COLOR="#00fe7a",
        WEBAPP_ADMIN_THEME_EFFECTS_ENABLED=admin_effects_enabled,
    )
    monkeypatch.setattr(theme_effects, "get_settings", lambda _request: settings)
    monkeypatch.setattr(web_session, "get_settings", lambda _request: settings)
    monkeypatch.setattr(
        web_session,
        "verify_webapp_session_token",
        lambda _settings, token: {"user": 7, "admin": 8}.get(token),
    )

    @asynccontextmanager
    async def session():
        yield object()

    async def user(_session, user_id):
        return SimpleNamespace(user_id=user_id, is_banned=False)

    async def admin(_session, user_id):
        return user_id == 8

    monkeypatch.setattr(theme_effects, "get_session_factory", lambda _request: session)
    monkeypatch.setattr(theme_effects.user_dal, "get_user_by_id", user)
    monkeypatch.setattr(theme_effects, "is_admin", admin)

    async def scenario() -> None:
        app = web.Application()
        app.router.add_get("/api/theme-effects", theme_effects.theme_effects_route)
        app.router.add_get(
            "/api/theme-effects/assets/{key}/{digest}/{path:.+}",
            theme_effects.theme_effect_asset_route,
        )
        path = f"/api/theme-effects/assets/ocean/{digest}/effects/main.js"
        async with TestClient(TestServer(app)) as client:
            assert (await client.get(path)).status == 401
            # An ordinary user runs the active theme's adapter.
            response = await client.get(path, headers={"Authorization": "Bearer user"})
            assert response.status == 200
            assert response.content_type == "text/javascript"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert "no-store" in response.headers["Cache-Control"]
            # The appearance setting controls normal privileged storefront sessions.
            response = await client.get(
                "/api/theme-effects", headers={"Authorization": "Bearer admin"}
            )
            effect = (await response.json())["effect"]
            if admin_effects_enabled:
                assert effect and effect["key"] == "ocean"
            else:
                assert effect is None
            # Users cannot turn this setting on via a preview query parameter.
            response = await client.get(
                "/api/theme-effects?theme_preview=dark",
                headers={"Authorization": "Bearer user"},
            )
            assert (await response.json())["effect"]["key"] == "ocean"
            # Explicit admin preview remains available with the setting off.
            response = await client.get(
                "/api/theme-effects?theme_preview=ocean",
                headers={"Authorization": "Bearer admin"},
            )
            effect = (await response.json())["effect"]
            assert effect and effect["key"] == "ocean"
            assert (await client.get(path, headers={"Authorization": "Bearer admin"})).status == 200
            # An ordinary user can never pull another theme's adapter.
            other = f"/api/theme-effects/assets/dark/{digest}/effects/main.js"
            assert (await client.get(other, headers={"Authorization": "Bearer user"})).status == 404
            # Revoking consent disables the adapter for previews too.
            permit(tmp_path, False)
            for token in ("user", "admin"):
                response = await client.get(
                    "/api/theme-effects", headers={"Authorization": f"Bearer {token}"}
                )
                assert (await response.json())["effect"] is None
            assert (await client.get(path, headers={"Authorization": "Bearer user"})).status == 404
            assert (await client.get(path, headers={"Authorization": "Bearer admin"})).status == 404

    asyncio.run(scenario())


def test_live_preview_is_sandboxed_and_does_not_grant_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_effect(tmp_path)

    async def scenario() -> None:
        async with client_context(tmp_path, monkeypatch) as client:
            response = await client.get(
                "/api/admin/themes/library/ocean/effects-preview",
                headers={"Authorization": "Bearer user7", "X-Test-Admin": "yes"},
            )
            assert response.status == 200
            csp = response.headers["Content-Security-Policy"]
            assert "sandbox allow-scripts" in csp and "allow-same-origin" not in csp
            assert "connect-src &#x27;none&#x27;" in await response.text()
            from config.theme_packages.registry import read_registry

            assert not read_registry(tmp_path).effects

    asyncio.run(scenario())
