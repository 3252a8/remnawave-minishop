import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
USER_DETAIL = REPO_ROOT / "frontend/src/admin/sections/UserDetailModal.svelte"
STATS_SECTION = REPO_ROOT / "frontend/src/admin/sections/StatsSection.svelte"
ADMIN_PANEL = REPO_ROOT / "frontend/src/admin/AdminPanel.svelte"
ADMIN_CSS = REPO_ROOT / "frontend/src/styles/admin.css"
USERS_STORE = REPO_ROOT / "frontend/src/lib/admin/stores/usersStore.ts"


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


def test_action_save_buttons_require_dirty_valid_state():
    source = _source()

    assert "tariffActionDirty" in source
    assert "premiumOverrideDirty" in source
    assert "regularOverrideDirty" in source
    assert "hwidLimitDirty" in source
    assert "premiumOverrideDraftValid" in source
    assert "regularOverrideDraftValid" in source
    assert "hwidLimitDraftValid" in source
    assert "grantTrafficGbValid" in source
    assert "class:is-dirty={tariffActionDirty}" in source
    assert "class:is-dirty={premiumOverrideDirty}" in source
    assert "class:is-dirty={regularOverrideDirty}" in source
    assert "class:is-dirty={hwidLimitDirty}" in source
    assert "!tariffActionDirty" in source
    assert "!premiumOverrideDirty" in source
    assert "!regularOverrideDirty" in source
    assert "!hwidLimitDirty" in source
    assert "!grantTrafficGbValid" in source


def test_action_cards_surface_unsaved_state():
    source = _source()

    assert "admin-action-save-controls" in source
    assert "admin-unsaved-hint" in source
    assert "user_action_unsaved_hint" in source
    assert 'at("settings_badge_dirty"' in source

    for language in ("ru", "en"):
        messages = json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8"))
        assert messages["admin_user_action_unsaved_hint"]


def test_user_action_saves_refresh_details_without_reopening_modal():
    store = USERS_STORE.read_text(encoding="utf-8")
    action_start = store.index("async function extendUser()")
    action_end = store.index("async function deleteUser()", action_start)
    action_block = store[action_start:action_end]

    assert "async function refreshOpenedUserDetail" in store
    assert "userTariffActionBaselineKey" in store
    assert "premiumBonusGbBaseline" in store
    assert "regularBonusGbBaseline" in store
    assert "hwidDeviceLimitBaseline" in store
    assert "await openUser(" not in action_block
    assert action_block.count("await refreshOpenedUserDetail(") >= 7
    assert "resetPremium: false" in action_block
    assert "resetRegular: false" in action_block
    assert "resetHwid: false" in action_block


def test_stats_recent_payments_open_payment_and_user_cards():
    source = STATS_SECTION.read_text(encoding="utf-8")
    table_start = source.index("{#each recentPayments as p (p.payment_id)}")
    table_end = source.index("{/each}", table_start)
    table_block = source[table_start:table_end]

    assert "paymentsStore.openPayment(p)" in table_block
    assert "onOpenUserCard(p.user_id)" in table_block
    assert "payment_detail_open" in table_block
    assert "payments_open_user" in table_block
    assert "admin-payment-id-btn" in source
    assert "admin-payments-user-btn" in source


def test_stats_recent_payment_user_button_stays_in_current_section():
    source = ADMIN_PANEL.read_text(encoding="utf-8")

    assert "onOpenUserCard={openSectionUserCard}" in source
    assert re.search(
        r'\$: openSectionUserCard\s*=\s*active === "payments"\s*\?\s*openPaymentUserCard'
        r'\s*:\s*active === "logs"\s*\?\s*openLogsUserCard\s*:\s*openUserCard;',
        source,
        re.S,
    )
