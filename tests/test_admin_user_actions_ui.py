import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
USER_DETAIL = REPO_ROOT / "frontend/src/admin/sections/UserDetailModal.svelte"
ADMIN_CSS = REPO_ROOT / "frontend/src/styles/admin.css"


def _source() -> str:
    return USER_DETAIL.read_text(encoding="utf-8")


def _extend_card_markup() -> str:
    source = _source()
    start = source.index('class="admin-user-action-sheet admin-user-action-sheet--extend"')
    end = source.index('class="admin-reset-trial-btn"', start)
    return source[start:end]


def test_extend_subscription_controls_are_grouped_in_action_card():
    source = _source()
    card = _extend_card_markup()

    assert '<AdminSectionHeader title={at("user_label_extend"' in card
    assert 'class="admin-user-extend-grid"' in card
    assert "bind:value={$usersStore.userExtendDays}" in card
    assert 'max="3650"' in card
    assert "items={extendTariffItems}" in card
    assert "onclick={usersStore.extendUser}" in card
    assert source.index("admin-user-action-sheet--extend") < source.index(
        'class="admin-reset-trial-btn"'
    )


def test_extend_tariff_dropdown_uses_admin_select_and_marks_current_tariff():
    source = _source()
    card = _extend_card_markup()

    assert "<AdminSelect" in card
    assert "<select" not in card.lower()
    assert 'class="admin-user-tariff-select admin-user-extend-tariff-select"' in card
    assert "function tariffSelectItem" in source
    assert "user_tariff_current_badge" in source
    assert "markCurrent: true" in source
    assert 'currentSubscriptionTariff?.billing_model === "period"' in source


def test_extend_tariff_state_blocks_invalid_hidden_selection():
    source = _source()

    assert "userExtendTariffValid" in source
    assert 'usersStore.updateState({ userExtendTariffKey: "" })' in source
    assert "!userExtendTariffValid" in source
    assert "extendTariffsLoading" in source


def test_extend_action_styles_fill_the_actions_column():
    css = ADMIN_CSS.read_text(encoding="utf-8")

    assert re.search(
        r"\.admin-user-quick-actions\s*{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)",
        css,
        re.S,
    )
    assert ".admin-user-extend-grid" in css
    assert (
        "grid-template-columns: minmax(112px, 0.72fr) minmax(220px, 1.28fr) minmax(136px, auto);"
    ) in css
    assert re.search(r"\.admin-reset-trial-btn\s*{[^}]*width:\s*100%", css, re.S)


def test_extend_tariff_current_badge_is_localized():
    for language in ("ru", "en"):
        messages = json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8"))
        assert messages["admin_user_tariff_current_badge"]
