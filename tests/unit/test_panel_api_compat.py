from bot.services.panel_api_compat import (
    PanelApiCompatibility,
    PanelUserIdMode,
    compatible_panel_user_reference,
    normalize_panel_user,
    numeric_panel_user_id,
)
from bot.services.panel_api_contracts import PanelApiCapability, PanelApiGeneration


def test_metadata_selects_user_identity_contract() -> None:
    legacy = PanelApiCompatibility.from_metadata({"response": {"version": "2.8.1"}})

    assert legacy.user_id_mode is PanelUserIdMode.UUID
    assert legacy.version == "2.8.1"
    assert legacy.generation is PanelApiGeneration.RW2_UUID
    assert legacy.support_status == "maintenance"

    for version in ("v3.0.0", "3.1.0", "3.2.0", "3.2.1"):
        current = PanelApiCompatibility.from_metadata({"response": {"version": version}})

        assert current.user_id_mode is PanelUserIdMode.NUMERIC_ID
        assert current.version == version
        assert current.generation is PanelApiGeneration.RW3_NUMERIC
        assert current.support_status == "current"
        assert current.supports(PanelApiCapability.USER_STREAM_FILTERS) is True

    assert current.certified_versions == ("3.2.1", "3.2.0", "3.1.0", "3.0.0")


def test_unknown_metadata_does_not_guess_a_generation() -> None:
    compatibility = PanelApiCompatibility.from_metadata({"response": {"version": "development"}})

    assert compatibility.user_id_mode is PanelUserIdMode.UNKNOWN
    assert compatibility.version is None


def test_future_major_is_unverified_and_best_effort_compatible() -> None:
    compatibility = PanelApiCompatibility.from_metadata({"response": {"version": "4.0.0"}})

    assert compatibility.version == "4.0.0"
    assert compatibility.generation is PanelApiGeneration.UNKNOWN
    assert compatibility.user_id_mode is PanelUserIdMode.UNKNOWN
    assert compatibility.support_status == "unverified"
    assert compatibility.unreviewed_generation is True
    assert compatibility.explicitly_unsupported is False
    assert compatibility.supports(PanelApiCapability.USER_STREAM) is None


def test_v3_user_gets_a_legacy_uuid_alias_without_losing_id() -> None:
    source = {"id": 42, "username": "tg_42"}

    normalized = normalize_panel_user(source)

    assert normalized == {"id": 42, "uuid": "42", "username": "tg_42"}
    assert source == {"id": 42, "username": "tg_42"}


def test_v2_uuid_wins_when_response_also_contains_internal_id() -> None:
    normalized = normalize_panel_user({"id": 42, "uuid": "panel-uuid"})

    assert normalized == {"id": 42, "uuid": "panel-uuid"}


def test_numeric_identifier_rejects_ambiguous_values() -> None:
    assert numeric_panel_user_id("42") == 42
    assert numeric_panel_user_id(42) == 42
    assert numeric_panel_user_id(True) is None
    assert numeric_panel_user_id("0") is None
    assert numeric_panel_user_id("panel-uuid") is None


def test_user_reference_is_strict_for_known_generations_and_inferred_when_unknown() -> None:
    legacy = PanelApiCompatibility.from_metadata({"response": {"version": "2.8.1"}})
    current = PanelApiCompatibility.from_metadata({"response": {"version": "3.0.0"}})
    unknown = PanelApiCompatibility.unknown()

    assert compatible_panel_user_reference("panel-uuid", legacy) == "panel-uuid"
    assert compatible_panel_user_reference("42", legacy) is None
    assert compatible_panel_user_reference("42", current) == "42"
    assert compatible_panel_user_reference("panel-uuid", current) is None
    assert compatible_panel_user_reference("00042", unknown) == "42"
    assert compatible_panel_user_reference("panel-uuid", unknown) == "panel-uuid"
    assert compatible_panel_user_reference("", unknown) is None
