"""A broken provider env must not take the whole settings layer down with it.

One provider whose env config cannot be built used to abort ``build_provider_configs``
entirely: every other provider lost its bundle, ``load_overrides_from_db`` gave
up before applying anything, and the admin panel reported saves that the running
process silently ignored.
"""

from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp.test_utils import make_mocked_request
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from bot.app.web.admin_api_impl import settings as settings_api
from bot.app.web.admin_api_impl.panel_links import build_panel_user_admin_url
from bot.app.web.webapp import external_oauth
from bot.payment_providers import registry
from bot.payment_providers.base import PaymentProviderSpec, ProviderEnvConfig
from bot.payment_providers.paykilla.config import PaykillaConfig
from bot.payment_providers.tribute.config import TributeConfig
from bot.services import settings_override_service as svc
from bot.services.partner_program_service import PartnerProgramService
from config.settings import Settings


@pytest.fixture(autouse=True)
def _restore_provider_configs():
    # These tests rebuild the process-wide bundle singleton; hand the next test
    # a set built from the isolated env instead of their leftovers.
    yield
    registry.build_provider_configs(force=True)


class _BrokenConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(env_prefix="BROKEN_", extra="ignore")

    ENABLED: bool = False

    @model_validator(mode="after")
    def _always_fail(self) -> _BrokenConfig:
        raise ValueError("BROKEN_ENABLED is not usable")


class _WorkingConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(env_prefix="WORKING_", extra="ignore")

    ENABLED: bool = True


def test_broken_provider_config_does_not_drop_the_other_bundles(monkeypatch, caplog) -> None:
    specs = tuple(
        PaymentProviderSpec(
            id=name,
            provider_key=name,
            label=name,
            pending_status=f"pending_{name}",
            enabled=lambda _: True,
            service_key=f"{name}_service",
            config_class=config,
        )
        for name, config in (("broken", _BrokenConfig), ("working", _WorkingConfig))
    )

    with (
        monkeypatch.context() as patch,
        caplog.at_level(logging.ERROR, logger="bot.payment_providers.registry"),
    ):
        patch.setattr(registry, "PAYMENT_PROVIDER_SPECS", specs)
        bundles = registry.build_provider_configs(force=True)
        assert registry.reporting_fee_sources("broken") == {}
        assert registry.reporting_fee_sources("working") == {
            "working": {"": [("WORKING_REPORTING_FEE_PERCENT", None)]}
        }

    assert bundles["broken_service"].config is None
    assert bundles["working_service"].config is not None
    assert bundles["working_service"].config.ENABLED is True
    assert "Payment provider broken is disabled" in caplog.text


def test_shop_flag_without_id_no_longer_breaks_the_config_build(monkeypatch) -> None:
    # The exact operator mistake the admin panel itself can produce: the Shop
    # toggle is on before the Shop ID has been filled in.
    monkeypatch.setenv("TRIBUTE_ENABLED", "true")
    monkeypatch.setenv("TRIBUTE_API_KEY", "key")
    monkeypatch.setenv("TRIBUTE_SHOP_ENABLED", "true")
    monkeypatch.delenv("TRIBUTE_SHOP_ID", raising=False)

    bundles = registry.build_provider_configs(force=True)

    config = bundles["tribute_service"].config
    assert isinstance(config, TributeConfig)
    assert config.ENABLED is True
    assert config.SHOP_ID is None
    # Every other provider still has its bundle.
    assert bundles["yookassa_service"].config is not None


class _Ctx:
    async def __aenter__(self) -> _Ctx:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False


class _FakeSession(_Ctx):
    def begin(self) -> _Ctx:
        return _Ctx()

    async def execute(self, statement: object) -> None:
        pass


@pytest.fixture
def _memory_overrides(monkeypatch) -> dict[str, Any]:
    store: dict[str, Any] = {}

    async def upsert(session: Any, *, key: str, value: Any, updated_by: int | None) -> None:
        store[key] = value

    async def delete(session: Any, key: str) -> None:
        store.pop(key, None)

    async def get_values(session: Any, keys: frozenset[str]) -> dict[str, Any]:
        return {key: store[key] for key in keys if key in store}

    monkeypatch.setattr(svc.app_settings_dal, "upsert_override", upsert)
    monkeypatch.setattr(svc.app_settings_dal, "delete_override", delete)
    monkeypatch.setattr(svc.app_settings_dal, "get_override_values", get_values)
    return store


def test_admin_validates_complete_telegram_chat_menu_before_persisting(_memory_overrides):
    settings = Settings(_env_file=None)
    mode_key = "TELEGRAM_CHAT_MENU_MODE"
    text_key = "TELEGRAM_CHAT_MENU_TEXT"
    url_key = "TELEGRAM_CHAT_MENU_URL"

    result = asyncio.run(
        svc.update_overrides(
            settings,
            _FakeSession,
            updates={mode_key: "web_app", url_key: "http://app.example.com/"},
        )
    )
    assert result["errors"] == {
        text_key: "telegram_chat_menu_text_required",
        url_key: "telegram_chat_menu_url_invalid",
    }
    assert _memory_overrides == {}

    saved = {mode_key: "web_app", text_key: "My app", url_key: "https://app.example.com/"}
    result = asyncio.run(svc.update_overrides(settings, _FakeSession, updates=saved))
    assert result["ok"]
    assert _memory_overrides == saved
    assert settings.TELEGRAM_CHAT_MENU_MODE == "web_app"

    result = asyncio.run(
        svc.update_overrides(settings, _FakeSession, updates={}, deletes=[url_key])
    )
    assert result["errors"] == {url_key: "telegram_chat_menu_url_invalid"}
    assert _memory_overrides == saved

    result = asyncio.run(
        svc.update_overrides(settings, _FakeSession, updates={mode_key: "keep"}, deletes=[url_key])
    )
    assert result["ok"]
    assert _memory_overrides == {mode_key: "keep", text_key: "My app"}
    assert settings.TELEGRAM_CHAT_MENU_MODE == "keep"


def test_update_overrides_reports_settings_the_process_could_not_apply(
    monkeypatch,
    caplog,
    _memory_overrides,
) -> None:
    settings = object()
    monkeypatch.setattr(svc, "_apply_value", lambda *args, **kwargs: False)

    with caplog.at_level(logging.ERROR, logger="bot.services.settings_override_service"):
        result = asyncio.run(
            svc.update_overrides(
                settings,  # type: ignore[arg-type]
                lambda: _FakeSession(),
                updates={"TRIBUTE_ENABLED": False},
                deletes=[],
                actor_id=1,
            )
        )

    assert result["ok"] is True
    assert result["not_applied"] == ["TRIBUTE_ENABLED"]
    # The value is still persisted: a restart is enough to pick it up.
    assert _memory_overrides == {"TRIBUTE_ENABLED": False}
    assert "could not apply" in caplog.text


def test_update_overrides_reports_nothing_when_everything_applies(
    monkeypatch,
    _memory_overrides,
) -> None:
    registry.build_provider_configs(force=True)
    settings = object()

    result = asyncio.run(
        svc.update_overrides(
            settings,  # type: ignore[arg-type]
            lambda: _FakeSession(),
            updates={"TRIBUTE_ENABLED": False},
            deletes=[],
            actor_id=1,
        )
    )

    assert result["not_applied"] == []
    assert registry.get_provider_bundle("tribute_service").config.ENABLED is False


def test_worker_refreshes_saved_outbound_settings_and_restores_deleted_overrides(
    monkeypatch, _memory_overrides
) -> None:
    monkeypatch.setenv("SMTP_HOST", "env-mail.internal")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_FALLBACK_PORTS", "465")
    registry.build_provider_configs(force=True)
    bundle = registry.get_provider_bundle("paykilla_service")
    assert bundle is not None and isinstance(bundle.config, PaykillaConfig)
    config = bundle.config
    initial_base_url = config.BASE_URL
    initial_rate_url = config.EXCHANGE_RATE_URL
    initial_private_urls = config._trusted_private_api_urls
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        SMTP_HOST="old-mail.internal",
    )
    keys = {
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_FALLBACK_PORTS",
        "PAYKILLA_BASE_URL",
        "PAYKILLA_EXCHANGE_RATE_URL",
    }
    assert keys <= svc.outbound_runtime_setting_keys()
    _memory_overrides.update(
        SMTP_HOST="new-mail.internal",
        SMTP_PORT=587,
        SMTP_FALLBACK_PORTS="",
        PAYKILLA_BASE_URL="http://payment.internal:8080",
        PAYKILLA_EXCHANGE_RATE_URL="http://rates.internal:8000/{source}",
    )
    monkeypatch.setattr(
        svc.app_settings_dal, "get_all_overrides", AsyncMock(return_value=_memory_overrides)
    )
    assert (
        asyncio.run(svc.refresh_overrides_from_db(settings, lambda: _FakeSession(), keys=keys)) == 5
    )
    assert settings._trusted_smtp_endpoints == (("new-mail.internal", 587),)
    assert config._trusted_private_api_urls == ("http://payment.internal:8080",)
    assert config._trusted_exchange_rate_url == "http://rates.internal:8000/{source}"
    _memory_overrides.clear()
    assert (
        asyncio.run(svc.refresh_overrides_from_db(settings, lambda: _FakeSession(), keys=keys)) == 0
    )
    assert settings._trusted_smtp_endpoints == (
        ("env-mail.internal", 2525),
        ("env-mail.internal", 465),
    )
    assert initial_base_url == config.BASE_URL
    assert initial_rate_url == config.EXCHANGE_RATE_URL
    assert config._trusted_private_api_urls == initial_private_urls


def test_admin_reset_restores_the_original_private_api_approval(_memory_overrides) -> None:
    registry.build_provider_configs(force=True)
    bundle = registry.get_provider_bundle("paykilla_service")
    assert bundle is not None and isinstance(bundle.config, PaykillaConfig)
    config = bundle.config
    initial_private_urls = config._trusted_private_api_urls
    settings = Settings(
        _env_file=None, BOT_TOKEN="token", POSTGRES_USER="test", POSTGRES_PASSWORD="test"
    )
    result = asyncio.run(
        svc.update_overrides(
            settings,
            lambda: _FakeSession(),
            updates={"PAYKILLA_BASE_URL": "http://payment.internal:8080"},
            actor_id=1,
        )
    )
    assert result["ok"] is True
    assert config._trusted_private_api_urls == ("http://payment.internal:8080",)
    result = asyncio.run(
        svc.update_overrides(
            settings, lambda: _FakeSession(), updates={}, deletes=["PAYKILLA_BASE_URL"]
        )
    )
    assert result["ok"] is True
    assert _memory_overrides == {}
    assert config._trusted_private_api_urls == initial_private_urls


@pytest.mark.parametrize(
    ("key", "service_key"),
    [
        ("ROLLYPAY_BASE_URL", "rollypay_service"),
        ("CLOUDPAYMENTS_BASE_URL", "cloudpayments_service"),
    ],
)
@pytest.mark.parametrize("url", ["https://api.example.com/v1", "http://10.1.2.3:8080/api"])
def test_admin_can_persist_and_apply_a_custom_payment_api_url(
    key: str,
    service_key: str,
    url: str,
    _memory_overrides: dict[str, Any],
) -> None:
    registry.build_provider_configs(force=True)
    settings = Settings(
        _env_file=None, BOT_TOKEN="token", POSTGRES_USER="test", POSTGRES_PASSWORD="test"
    )
    result = asyncio.run(
        svc.update_overrides(
            settings, Mock(return_value=_FakeSession()), updates={key: url}, actor_id=1
        )
    )
    assert result["ok"] is True
    assert result["not_applied"] == []
    assert _memory_overrides == {key: url}
    bundle = registry.get_provider_bundle(service_key)
    assert bundle is not None
    config = bundle.config
    assert config is not None
    assert config._trusted_api_urls == (url,)
    assert config._trusted_private_api_urls == (url,)


def test_update_overrides_persists_empty_subscription_purchase_description(
    _memory_overrides,
) -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        SUBSCRIPTION_PURCHASE_DESCRIPTION_RU="Описание",
    )

    result = asyncio.run(
        svc.update_overrides(
            settings,
            lambda: _FakeSession(),
            updates={"SUBSCRIPTION_PURCHASE_DESCRIPTION_RU": ""},
            deletes=[],
            actor_id=1,
        )
    )

    assert result["not_applied"] == []
    assert _memory_overrides == {"SUBSCRIPTION_PURCHASE_DESCRIPTION_RU": ""}
    assert settings.SUBSCRIPTION_PURCHASE_DESCRIPTION_RU == ""
    assert settings.subscription_purchase_description("ru") == ""


def test_update_overrides_persists_selected_webapp_theme(_memory_overrides) -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        WEBAPP_DEFAULT_THEME=None,
    )

    result = asyncio.run(
        svc.update_overrides(
            settings,
            lambda: _FakeSession(),
            updates={"WEBAPP_DEFAULT_THEME": "ocean"},
            deletes=[],
            actor_id=1,
        )
    )

    assert result["ok"] is True
    assert result["not_applied"] == []
    assert _memory_overrides == {"WEBAPP_DEFAULT_THEME": "ocean"}
    assert settings.WEBAPP_DEFAULT_THEME == "ocean"


def test_admin_can_save_and_read_separate_panel_urls(monkeypatch, _memory_overrides) -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
    )
    updates = {
        "PANEL_API_URL": "http://remnawave:3000/api",
        "PANEL_PUBLIC_URL": "https://browser.example.com/prefix/api",
    }
    monkeypatch.setattr(settings_api, "_require_admin_user_id", lambda request: 42)
    monkeypatch.setattr(settings_api, "get_settings", lambda request: settings)
    monkeypatch.setattr(settings_api, "get_session_factory", lambda request: lambda: _FakeSession())
    monkeypatch.setattr(
        settings_api,
        "parse_body_or_400",
        AsyncMock(return_value=SimpleNamespace(updates=updates, deletes=[])),
    )
    refresh = AsyncMock()
    monkeypatch.setattr(settings_api, "refresh_webapp_runtime_after_settings_change", refresh)

    response = asyncio.run(
        settings_api.admin_settings_patch_route(make_mocked_request("PATCH", "/admin/settings"))
    )

    assert response.status == 200
    assert response.text is not None
    assert json.loads(response.text)["not_applied"] == []
    assert _memory_overrides == updates
    assert settings.panel_settings.api_url == updates["PANEL_API_URL"]
    assert (
        build_panel_user_admin_url(settings.PANEL_API_URL, 158, settings.PANEL_PUBLIC_URL)
        == "https://browser.example.com/prefix/dashboard/open/user/158"
    )
    refresh.assert_awaited_once()

    monkeypatch.setattr(
        settings_api.app_settings_dal,
        "get_overrides_with_meta",
        AsyncMock(return_value=[{"key": key} for key in updates]),
    )
    response = asyncio.run(
        settings_api.admin_settings_get_route(make_mocked_request("GET", "/admin/settings"))
    )
    assert response.status == 200
    assert response.text is not None
    fields = {
        field["key"]: field
        for section in json.loads(response.text)["sections"]
        for field in section["fields"]
    }
    for key, expected in updates.items():
        assert fields[key]["value"] == expected
        assert fields[key]["overridden"] is True
        assert fields[key]["value_source"] == "database_override"


def test_legacy_kuma_slug_override_is_applied_but_not_admin_editable() -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        SERVER_STATUS_KUMA_SLUG="environment-slug",
    )

    applied, skipped = svc._apply_overrides(settings, {"SERVER_STATUS_KUMA_SLUG": "saved-slug"})

    assert applied == ["SERVER_STATUS_KUMA_SLUG"]
    assert skipped == []
    assert settings.SERVER_STATUS_KUMA_SLUG == "saved-slug"
    assert svc.get_field_by_key("SERVER_STATUS_KUMA_SLUG") is None


def test_google_oidc_admin_overrides_apply_without_a_restart(_memory_overrides) -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        GOOGLE_OIDC_ENABLED=False,
    )
    assert external_oauth._provider(settings, "google") is None

    updates = {
        "GOOGLE_OIDC_ENABLED": True,
        "GOOGLE_OIDC_CLIENT_ID": "live-client-id",
        "GOOGLE_OIDC_CLIENT_SECRET": "live-client-secret",
    }
    result = asyncio.run(
        svc.update_overrides(
            settings,
            lambda: _FakeSession(),
            updates=updates,
            deletes=[],
            actor_id=1,
        )
    )

    provider = external_oauth._provider(settings, "google")
    assert result["not_applied"] == []
    assert _memory_overrides == updates
    assert provider is not None
    assert provider.client_id == "live-client-id"
    assert provider.client_secret == "live-client-secret"


def test_discord_oidc_admin_overrides_apply_without_a_restart(_memory_overrides) -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        DISCORD_OIDC_ENABLED=False,
    )
    assert external_oauth._provider(settings, "discord") is None

    updates = {
        "DISCORD_OIDC_ENABLED": True,
        "DISCORD_OIDC_CLIENT_ID": "live-discord-client-id",
        "DISCORD_OIDC_CLIENT_SECRET": "live-discord-client-secret",
    }
    result = asyncio.run(
        svc.update_overrides(
            settings,
            lambda: _FakeSession(),
            updates=updates,
            deletes=[],
            actor_id=1,
        )
    )

    provider = external_oauth._provider(settings, "discord")
    assert result["not_applied"] == []
    assert _memory_overrides == updates
    assert provider is not None
    assert provider.client_id == "live-discord-client-id"
    assert provider.client_secret == "live-discord-client-secret"
    assert provider.scopes == ("identify", "email")
    assert provider.uses_pkce is False


def test_referral_link_visibility_rejects_disabling_the_last_link() -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        REFERRAL_WEBAPP_LINK_ENABLED=False,
        REFERRAL_TELEGRAM_LINK_ENABLED=True,
    )

    errors = svc._referral_link_visibility_errors(
        settings,
        {"REFERRAL_TELEGRAM_LINK_ENABLED": False},
        [],
    )

    assert errors == {
        "REFERRAL_TELEGRAM_LINK_ENABLED": "at least one referral link must remain enabled"
    }


def test_referral_link_visibility_allows_an_atomic_link_switch() -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        REFERRAL_WEBAPP_LINK_ENABLED=False,
        REFERRAL_TELEGRAM_LINK_ENABLED=True,
    )

    errors = svc._referral_link_visibility_errors(
        settings,
        {
            "REFERRAL_WEBAPP_LINK_ENABLED": True,
            "REFERRAL_TELEGRAM_LINK_ENABLED": False,
        },
        [],
    )

    assert errors == {}


def test_enabling_automatic_partner_enrollment_materializes_existing_users(
    monkeypatch,
    _memory_overrides,
) -> None:
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
    )
    auto_enroll = AsyncMock(return_value=3)
    monkeypatch.setattr(PartnerProgramService, "auto_enroll_all_users", auto_enroll)

    result = asyncio.run(
        svc.update_overrides(
            settings,
            lambda: _FakeSession(),
            updates={
                "PARTNER_PROGRAM_ENABLED": True,
                "PARTNER_AUTO_ENROLLMENT_ENABLED": True,
            },
            deletes=[],
            actor_id=7,
        )
    )

    assert result["ok"] is True
    assert result["auto_enrolled"] == 3
    assert _memory_overrides == {
        "PARTNER_PROGRAM_ENABLED": True,
        "PARTNER_AUTO_ENROLLMENT_ENABLED": True,
    }
    auto_enroll.assert_awaited_once()
    auto_enroll_call = auto_enroll.await_args
    assert auto_enroll_call is not None
    assert auto_enroll_call.kwargs == {"actor_admin_id": 7}
