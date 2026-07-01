"""Feature entitlement provider contract and admin API exposure."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.app.web import admin_api
from bot.app.web.admin_api_impl import settings as admin_settings_routes
from bot.plugins import Plugin, PluginContext, register, reset_plugins, run_setup
from bot.services.entitlements import (
    MARKETING_CAMPAIGNS_ENTITLEMENT,
    MARKETING_WINBACK_ENTITLEMENT,
    RESERVED_ENTITLEMENT_KEYS,
    DefaultEntitlements,
    active_entitlements_source,
    features,
    get_entitlements,
    has_feature,
    reset_entitlements,
)
from config.settings import Settings


@pytest.fixture(autouse=True)
def _clean_entitlements_state():
    reset_plugins()
    reset_entitlements()
    yield
    reset_plugins()
    reset_entitlements()


def make_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "BOT_TOKEN": "x",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "ADMIN_IDS": "1",
    }
    values.update(overrides)
    return Settings(**values)


class _AsyncSessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FeaturePlugin(Plugin):
    name = "feature_plugin"

    def __init__(self, names):
        self.provider = DefaultEntitlements(names)

    def entitlements_provider(self):
        return self.provider


def test_default_entitlements_are_empty():
    provider = get_entitlements()

    assert provider.features() == set()
    assert provider.has_feature("admin.extra") is False
    assert features() == set()
    assert has_feature("admin.extra") is False
    assert active_entitlements_source() == "core"


def test_marketing_entitlement_keys_are_reserved_only():
    assert RESERVED_ENTITLEMENT_KEYS == {
        MARKETING_WINBACK_ENTITLEMENT,
        MARKETING_CAMPAIGNS_ENTITLEMENT,
    }
    assert features().isdisjoint(RESERVED_ENTITLEMENT_KEYS)


def test_plugin_entitlements_provider_becomes_active():
    register(FeaturePlugin({"admin.extra", "reports"}))

    run_setup(PluginContext(settings=make_settings()))

    assert active_entitlements_source() == "feature_plugin"
    assert has_feature("admin.extra") is True
    assert features() == {"admin.extra", "reports"}


def test_last_plugin_entitlements_provider_wins():
    register(FeaturePlugin({"first"}))

    class LaterFeaturePlugin(FeaturePlugin):
        name = "later_feature_plugin"

    register(LaterFeaturePlugin({"second"}))

    run_setup(PluginContext(settings=make_settings()))

    assert active_entitlements_source() == "later_feature_plugin"
    assert features() == {"second"}


def test_admin_settings_response_includes_default_features():
    response = asyncio.run(_admin_settings_response(make_settings()))

    payload = json.loads(response.text)

    assert payload["ok"] is True
    assert payload["features"] == []


def test_admin_settings_response_uses_plugin_features():
    register(FeaturePlugin({"reports", "admin.extra"}))
    settings = make_settings()
    run_setup(PluginContext(settings=settings))

    response = asyncio.run(_admin_settings_response(settings))

    payload = json.loads(response.text)
    assert payload["features"] == ["admin.extra", "reports"]


async def _admin_settings_response(settings: Settings):
    request = SimpleNamespace(
        app={"settings": settings, "async_session_factory": _AsyncSessionFactory()},
        headers={},
        cookies={},
        admin_telegram_id=1,
    )
    request.get = lambda key, default=None: getattr(request, key, default)

    with (
        patch.object(admin_settings_routes, "_require_admin_user_id", return_value=1),
        patch.object(
            admin_settings_routes.app_settings_dal,
            "get_overrides_with_meta",
            AsyncMock(return_value=[]),
        ),
    ):
        return await admin_api.admin_settings_get_route(request)
