import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.subscription_service_impl.squad_overrides import (
    detect_panel_manual_internal_squads,
    normalize_panel_external_squad_uuid,
    normalize_panel_internal_squad_uuids,
)
from db.dal import user_panel_squad_override_dal as override_dal


def test_normalize_panel_internal_squads_supports_strings_objects_and_nested_items():
    panel_user = {
        "activeInternalSquads": [
            "base-squad",
            {"uuid": "extra-a"},
            {"internalSquadUuid": "extra-b"},
            {"squadUuid": "extra-c"},
            {"internalSquad": {"uuid": "extra-d"}},
            {"squad": {"uuid": "extra-e"}},
            {"uuid": "extra-a"},
            {"uuid": ""},
        ]
    }

    assert normalize_panel_internal_squad_uuids(panel_user) == [
        "base-squad",
        "extra-a",
        "extra-b",
        "extra-c",
        "extra-d",
        "extra-e",
    ]


def test_normalize_panel_internal_squads_distinguishes_missing_from_empty():
    assert normalize_panel_internal_squad_uuids({}) is None
    assert normalize_panel_internal_squad_uuids({"active_internal_squads": []}) == []
    assert normalize_panel_internal_squad_uuids({"activeInternalSquadUuids": None}) == []


def test_detect_panel_manual_internal_squads_subtracts_managed_squads():
    assert detect_panel_manual_internal_squads(
        ["base-a", "manual-a", "premium-a", "manual-a"],
        ["base-a", "premium-a"],
    ) == ["manual-a"]


def test_normalize_panel_external_squad_uuid_supports_known_wire_keys():
    assert normalize_panel_external_squad_uuid({"externalSquadUuid": " external-a "}) == (
        True,
        "external-a",
    )
    assert normalize_panel_external_squad_uuid({"external_squad_uuid": None}) == (True, None)
    assert normalize_panel_external_squad_uuid({"externalSquadUUID": {"uuid": "external-b"}}) == (
        True,
        "external-b",
    )
    assert normalize_panel_external_squad_uuid({}) == (False, None)


def test_deactivate_managed_overrides_only_targets_panel_discovery_rows():
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=SimpleNamespace(rowcount=2))
    session.flush = AsyncMock()

    affected = asyncio.run(
        override_dal.deactivate_panel_internal_overrides_for_squads(
            session,
            user_id=42,
            panel_user_uuid="panel-user",
            squad_uuids=["base-squad", "premium-squad"],
        )
    )

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert affected == 2
    assert "user_panel_squad_overrides.source =" in sql
    assert "user_panel_squad_overrides.override_key IN" in sql
    assert "panel" in compiled.params.values()
    session.flush.assert_awaited_once()
