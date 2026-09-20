import re
from types import SimpleNamespace

import pytest

from bot.services.panel_tariff_tags import (
    configured_tariff_tags,
    panel_tariff_tag_for_key,
    plan_panel_tariff_tag,
)


@pytest.mark.parametrize("key", ["trial", "TRIAL", "_trial_", "Trial", None])
@pytest.mark.parametrize("configured", [False, True])
def test_trial_marker_cannot_collide_with_a_tariff(key, configured):
    config = SimpleNamespace(tariffs=[SimpleNamespace(key=key)]) if configured else None
    assert panel_tariff_tag_for_key(key, config, is_trial=True) == "TRIAL"
    assert panel_tariff_tag_for_key(key, config) != "TRIAL"
    plan = plan_panel_tariff_tag(
        current_tag="TRIAL", managed_tag=None, desired_tag="STANDARD", known_tariff_tags=()
    )
    assert plan.verification_payload == {"tag": "STANDARD"}


def test_tariff_key_is_mapped_to_remnawave_tag_constraints() -> None:
    assert panel_tariff_tag_for_key("standard") == "STANDARD"
    generated = panel_tariff_tag_for_key("premium-plan-for-friends")
    assert generated is not None
    assert len(generated) <= 16
    assert re.fullmatch(r"[A-Z0-9_]+", generated)


def test_colliding_readable_keys_get_distinct_stable_tags() -> None:
    config = SimpleNamespace(
        tariffs=(
            SimpleNamespace(key="plan-a", legacy_keys=()),
            SimpleNamespace(key="plan_a", legacy_keys=()),
        )
    )

    first = panel_tariff_tag_for_key("plan-a", config)
    second = panel_tariff_tag_for_key("plan_a", config)

    assert first != second
    assert {first, second} == configured_tariff_tags(config)


def test_empty_panel_tag_is_claimed_for_current_tariff() -> None:
    plan = plan_panel_tariff_tag(
        current_tag=None,
        managed_tag=None,
        desired_tag="STANDARD",
        known_tariff_tags={"STANDARD"},
    )

    assert plan.allowed is True
    assert plan.needs_patch is True
    assert plan.verification_payload == {"tag": "STANDARD"}
    assert plan.managed_tag_after == "STANDARD"


def test_previous_managed_tag_is_replaced_on_tariff_change() -> None:
    plan = plan_panel_tariff_tag(
        current_tag="BASIC",
        managed_tag="BASIC",
        desired_tag="PREMIUM",
        known_tariff_tags={"BASIC", "PREMIUM"},
    )

    assert plan.allowed is True
    assert plan.verification_payload == {"tag": "PREMIUM"}


def test_known_legacy_tariff_tag_is_safe_to_reconcile() -> None:
    plan = plan_panel_tariff_tag(
        current_tag="LEGACY_STANDARD",
        managed_tag=None,
        desired_tag="STANDARD",
        known_tariff_tags={"LEGACY_STANDARD", "STANDARD"},
    )

    assert plan.allowed is True
    assert plan.needs_patch is True


def test_manual_remnawave_tag_is_preserved() -> None:
    plan = plan_panel_tariff_tag(
        current_tag="MANUAL_OPERATOR",
        managed_tag=None,
        desired_tag="STANDARD",
        known_tariff_tags={"STANDARD"},
    )

    assert plan.allowed is False
    assert plan.needs_patch is False
    assert plan.verification_payload == {}
    assert plan.managed_tag_after is None


def test_owned_tag_is_cleared_without_an_active_tariff() -> None:
    plan = plan_panel_tariff_tag(
        current_tag="STANDARD",
        managed_tag="STANDARD",
        desired_tag=None,
        known_tariff_tags=set(),
    )

    assert plan.allowed is True
    assert plan.needs_patch is True
    assert plan.verification_payload == {"tag": None}
