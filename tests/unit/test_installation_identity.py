"""Tests for the neutral persistent installation identity service."""

from __future__ import annotations

import asyncio
import uuid

from bot.services import installation_identity


class _Overrides:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.values = dict(values or {})

    async def get(self, _session: object, key: str) -> tuple[bool, object | None]:
        return key in self.values, self.values.get(key)

    async def insert(
        self,
        _session: object,
        *,
        key: str,
        value: object,
        updated_by: int | None,
    ) -> bool:
        assert updated_by is None
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def upsert(
        self,
        _session: object,
        *,
        key: str,
        value: object,
        updated_by: int | None,
    ) -> None:
        assert updated_by is None
        self.values[key] = value


def _install_overrides(monkeypatch, values: dict[str, object] | None = None) -> _Overrides:
    overrides = _Overrides(values)
    monkeypatch.setattr(installation_identity.app_settings_dal, "get_override_value", overrides.get)
    monkeypatch.setattr(
        installation_identity.app_settings_dal,
        "insert_override_if_missing",
        overrides.insert,
    )
    monkeypatch.setattr(installation_identity.app_settings_dal, "upsert_override", overrides.upsert)
    return overrides


def test_creates_identity_without_telemetry_configuration(monkeypatch):
    overrides = _install_overrides(monkeypatch)

    identity = asyncio.run(installation_identity.get_or_create_installation_identity(object()))

    assert str(uuid.UUID(identity)) == identity
    assert overrides.values == {installation_identity.INSTALLATION_ID_KEY: identity}


def test_does_not_adopt_retired_telemetry_identity(monkeypatch):
    retired_identity = str(uuid.uuid4())
    overrides = _install_overrides(monkeypatch, {"TELEMETRY_INSTALLATION_ID": retired_identity})

    identity = asyncio.run(installation_identity.get_or_create_installation_identity(object()))

    assert identity != retired_identity
    assert overrides.values["TELEMETRY_INSTALLATION_ID"] == retired_identity
    assert overrides.values[installation_identity.INSTALLATION_ID_KEY] == identity


def test_repairs_malformed_persisted_identity(monkeypatch):
    overrides = _install_overrides(monkeypatch, {installation_identity.INSTALLATION_ID_KEY: "bad"})

    identity = asyncio.run(installation_identity.get_or_create_installation_identity(object()))

    assert str(uuid.UUID(identity)) == identity
    assert overrides.values[installation_identity.INSTALLATION_ID_KEY] == identity


def test_uses_identity_created_by_a_concurrent_process(monkeypatch):
    concurrent_identity = str(uuid.uuid4())
    overrides = _install_overrides(monkeypatch)

    async def concurrent_insert(
        _session: object,
        *,
        key: str,
        value: object,
        updated_by: int | None,
    ) -> bool:
        assert updated_by is None
        assert key == installation_identity.INSTALLATION_ID_KEY
        assert isinstance(value, str)
        overrides.values[key] = concurrent_identity
        return False

    monkeypatch.setattr(
        installation_identity.app_settings_dal,
        "insert_override_if_missing",
        concurrent_insert,
    )

    identity = asyncio.run(installation_identity.get_or_create_installation_identity(object()))

    assert identity == concurrent_identity
