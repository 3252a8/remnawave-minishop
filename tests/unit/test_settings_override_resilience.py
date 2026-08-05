"""A broken provider env must not take the whole settings layer down with it.

One provider whose env config cannot be built used to abort ``build_provider_configs``
entirely: every other provider lost its bundle, ``load_overrides_from_db`` gave
up before applying anything, and the admin panel reported saves that the running
process silently ignored.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from bot.payment_providers import registry
from bot.payment_providers.base import ProviderEnvConfig
from bot.payment_providers.tribute.config import TributeConfig
from bot.services import settings_override_service as svc
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


class _FakeSpec:
    def __init__(self, spec_id: str, service_key: str, config_class: Any) -> None:
        self.id = spec_id
        self.service_key = service_key
        self.config_class = config_class
        self.presentation_class = None


class _WorkingConfig(ProviderEnvConfig):
    model_config = SettingsConfigDict(env_prefix="WORKING_", extra="ignore")

    ENABLED: bool = True


def test_broken_provider_config_does_not_drop_the_other_bundles(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        registry,
        "PAYMENT_PROVIDER_SPECS",
        (
            _FakeSpec("broken", "broken_service", _BrokenConfig),
            _FakeSpec("working", "working_service", _WorkingConfig),
        ),
    )

    with caplog.at_level(logging.ERROR, logger="bot.payment_providers.registry"):
        bundles = registry.build_provider_configs(force=True)

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


@pytest.fixture
def _memory_overrides(monkeypatch) -> dict[str, Any]:
    store: dict[str, Any] = {}

    async def upsert(session: Any, *, key: str, value: Any, updated_by: int | None) -> None:
        store[key] = value

    async def delete(session: Any, key: str) -> None:
        store.pop(key, None)

    monkeypatch.setattr(svc.app_settings_dal, "upsert_override", upsert)
    monkeypatch.setattr(svc.app_settings_dal, "delete_override", delete)
    return store


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
