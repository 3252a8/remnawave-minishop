import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.squad_overrides import (
    SquadOverrideMixin,
    detect_panel_manual_internal_squads,
    normalize_panel_external_squad_uuid,
    normalize_panel_internal_squad_uuids,
)
from db.dal import user_panel_squad_override_dal as override_dal
from tests.support.settings_stub import settings_stub


class _PanelSquads(PanelApiService):
    """Panel API double whose squad list answers come from ``lists`` in order."""

    def __init__(self, *lists: Any) -> None:
        super().__init__(
            settings_stub(PANEL_API_URL="https://panel.example.test/api", PANEL_API_KEY="key")
        )
        self.squad_lists = AsyncMock(side_effect=list(lists))

    async def get_internal_squads(self, *, fresh: bool = False) -> list[dict[str, Any]] | None:
        result: list[dict[str, Any]] | None = await self.squad_lists(fresh=fresh)
        return result


class _SquadOverrideHost(SquadOverrideMixin):
    def __init__(self, panel_service: PanelApiService) -> None:
        self.panel_service = panel_service
        self.settings = panel_service.settings


def _build_squads(
    host: _SquadOverrideHost,
    *,
    manual: list[str],
    keep: tuple[str, ...] = (),
) -> tuple[list[str], AsyncMock]:
    """Build the squad list of a user with ``manual`` overrides on top of ``base-squad``."""
    deactivate = AsyncMock(return_value=1)
    with (
        patch.object(
            override_dal, "get_active_internal_squad_uuids", AsyncMock(return_value=manual)
        ),
        patch.object(override_dal, "deactivate_internal_override", deactivate),
        patch.object(override_dal, "get_active_external_override", AsyncMock(return_value=None)),
    ):
        payload = asyncio.run(
            host.build_effective_panel_squad_fields(
                MagicMock(spec=AsyncSession),
                user_id=42,
                panel_user_uuid="panel-user",
                managed_internal_squads=["base-squad"],
                discover_panel_overrides=False,
                keep_manual_internal_squads=keep,
                source="test",
            )
        )
    return payload["activeInternalSquads"], deactivate


def _squads(*uuids: str) -> list[dict[str, Any]]:
    return [{"uuid": uuid, "name": uuid} for uuid in uuids]


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


def test_effective_squads_drop_manual_squad_deleted_in_panel():
    panel = _PanelSquads(_squads("base-squad", "manual-live"), _squads("base-squad", "manual-live"))

    squads, deactivate = _build_squads(
        _SquadOverrideHost(panel), manual=["manual-live", "manual-gone"]
    )

    assert squads == ["base-squad", "manual-live"]
    assert panel.squad_lists.await_args_list == [call(fresh=False), call(fresh=True)]
    deactivate.assert_awaited_once()
    assert deactivate.await_args.kwargs == {
        "user_id": 42,
        "panel_user_uuid": "panel-user",
        "squad_uuid": "manual-gone",
    }


def test_effective_squads_keep_manual_squad_missing_only_from_cached_list():
    panel = _PanelSquads(_squads("base-squad"), _squads("base-squad", "manual-new"))

    squads, deactivate = _build_squads(_SquadOverrideHost(panel), manual=["manual-new"])

    assert squads == ["base-squad", "manual-new"]
    assert panel.squad_lists.await_count == 2
    deactivate.assert_not_awaited()


def test_effective_squads_do_not_refetch_when_cached_list_has_every_squad():
    panel = _PanelSquads(_squads("base-squad", "manual-live"))

    squads, deactivate = _build_squads(_SquadOverrideHost(panel), manual=["MANUAL-LIVE"])

    assert squads == ["base-squad", "MANUAL-LIVE"]
    assert panel.squad_lists.await_args_list == [call(fresh=False)]
    deactivate.assert_not_awaited()


def test_effective_squads_keep_manual_squads_when_panel_list_is_unavailable():
    for answers in (
        [None],
        [TimeoutError()],
        [_squads("base-squad"), None],
        [_squads("base-squad"), []],
        [_squads("base-squad"), TimeoutError()],
    ):
        squads, deactivate = _build_squads(
            _SquadOverrideHost(_PanelSquads(*answers)), manual=["manual-unknown"]
        )

        assert squads == ["base-squad", "manual-unknown"]
        deactivate.assert_not_awaited()


def test_effective_squads_skip_panel_lookup_without_manual_squads():
    panel = _PanelSquads()

    squads, deactivate = _build_squads(_SquadOverrideHost(panel), manual=[])

    assert squads == ["base-squad"]
    panel.squad_lists.assert_not_awaited()
    deactivate.assert_not_awaited()


def test_effective_squads_never_drop_squads_an_admin_is_adding():
    panel = _PanelSquads(_squads("base-squad"), _squads("base-squad"))

    squads, deactivate = _build_squads(
        _SquadOverrideHost(panel), manual=["admin-new", "manual-gone"], keep=("admin-new",)
    )

    assert squads == ["base-squad", "admin-new"]
    deactivate.assert_awaited_once()
    assert deactivate.await_args.kwargs["squad_uuid"] == "manual-gone"

    only_new = _PanelSquads()
    squads, deactivate = _build_squads(
        _SquadOverrideHost(only_new), manual=["admin-new"], keep=("ADMIN-NEW",)
    )

    assert squads == ["base-squad", "admin-new"]
    only_new.squad_lists.assert_not_awaited()
    deactivate.assert_not_awaited()


def test_effective_squads_reuse_a_confirmed_deletion_for_other_users():
    panel = _PanelSquads(_squads("base-squad"), _squads("base-squad"), _squads("base-squad"))
    host = _SquadOverrideHost(panel)

    first, first_deactivate = _build_squads(host, manual=["manual-gone"])
    second, second_deactivate = _build_squads(host, manual=["manual-gone"])

    assert first == second == ["base-squad"]
    first_deactivate.assert_awaited_once()
    second_deactivate.assert_awaited_once()
    assert panel.squad_lists.await_args_list == [
        call(fresh=False),
        call(fresh=True),
        call(fresh=False),
    ]
