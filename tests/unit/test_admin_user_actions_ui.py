import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
USER_DETAIL = REPO_ROOT / "frontend/src/admin/sections/UserDetailModal.svelte"
USER_DETAIL_VIEW = REPO_ROOT / "frontend/src/admin/sections/user-detail/UserDetailView.svelte"
USER_DETAIL_ASIDE = REPO_ROOT / "frontend/src/admin/sections/user-detail/UserDetailAside.svelte"
USER_DETAIL_CSS = REPO_ROOT / "frontend/src/admin/sections/UserDetailModal.css"
USER_ACTIONS = REPO_ROOT / "frontend/src/admin/sections/user-detail/UserActionsTab.svelte"
USER_QUICK_ACTIONS = (
    REPO_ROOT / "frontend/src/admin/sections/user-detail/UserQuickActionsBlock.svelte"
)
USER_TARIFF_ACTION = (
    REPO_ROOT / "frontend/src/admin/sections/user-detail/UserTariffActionCard.svelte"
)
USER_TRAFFIC_OVERRIDE_ACTION = (
    REPO_ROOT / "frontend/src/admin/sections/user-detail/UserTrafficOverrideActionCard.svelte"
)
USER_HWID_ACTION = (
    REPO_ROOT / "frontend/src/admin/sections/user-detail/UserHwidLimitActionCard.svelte"
)
USER_TRAFFIC_GRANT_ACTION = (
    REPO_ROOT / "frontend/src/admin/sections/user-detail/UserTrafficGrantActionCard.svelte"
)
USER_DIALOGS = REPO_ROOT / "frontend/src/admin/sections/user-detail/UserDetailDialogs.svelte"
STATS_SECTION = REPO_ROOT / "frontend/src/admin/sections/StatsSection.svelte"
ADMIN_PANEL = REPO_ROOT / "frontend/src/admin/AdminPanel.svelte"
ADMIN_CSS = REPO_ROOT / "frontend/src/styles/admin.css"
USERS_STORE = REPO_ROOT / "frontend/src/lib/admin/stores/usersStore.svelte.ts"


def _source() -> str:
    return USER_DETAIL.read_text(encoding="utf-8")


def _view_source() -> str:
    return USER_DETAIL_VIEW.read_text(encoding="utf-8")


def _aside_source() -> str:
    return USER_DETAIL_ASIDE.read_text(encoding="utf-8")


def _actions_source() -> str:
    return USER_ACTIONS.read_text(encoding="utf-8")


def _quick_actions_source() -> str:
    return USER_QUICK_ACTIONS.read_text(encoding="utf-8")


def _dialogs_source() -> str:
    return USER_DIALOGS.read_text(encoding="utf-8")


def _extend_card_markup() -> str:
    source = _quick_actions_source()
    start = source.index('class="admin-user-action-sheet admin-user-action-sheet--extend"')
    end = source.index('class="admin-reset-trial-btn"', start)
    return source[start:end]


def test_extend_subscription_controls_are_grouped_in_action_card():
    source = _quick_actions_source()
    card = _extend_card_markup()

    assert '<AdminSectionHeader title={at("user_label_extend"' in card
    assert 'class="admin-user-extend-grid"' in card
    assert "bind:value={usersStore.userExtendDays}" in card
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


def test_inactive_tabs_override_specific_tab_display_rules():
    css = ADMIN_CSS.read_text(encoding="utf-8")
    user_detail_css = USER_DETAIL_CSS.read_text(encoding="utf-8")

    assert re.search(
        r"\.admin-tabs-root\s+\.admin-tabs-content\[data-state=\"inactive\"\]\s*{[^}]*display:\s*none",
        css,
        re.S,
    )
    assert '\n.admin-tabs-content[data-state="inactive"] {' not in css
    assert ".admin-user-dialog .admin-user-logs-tab" in user_detail_css
    assert re.search(
        r"\.admin-user-dialog\s+\.admin-user-logs-tab\s*{[^}]*display:\s*flex",
        user_detail_css,
        re.S,
    )


def test_extend_tariff_current_badge_is_localized():
    for language in ("ru", "en"):
        messages = json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8"))
        assert messages["admin_user_tariff_current_badge"]


def test_user_detail_links_include_install_share_link():
    source = _aside_source()

    assert "openedUserDetail.install_share_url" in source
    assert "user_label_install_share" in source
    assert "user_install_share_link_copied" in source

    for language in ("ru", "en"):
        messages = json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8"))
        assert messages["admin_user_install_share_link_label"]
        assert messages["admin_user_label_install_share"]
        assert messages["admin_user_install_share_link_copied"]


def test_action_save_buttons_require_dirty_valid_state():
    actions = _actions_source()
    tariff = USER_TARIFF_ACTION.read_text(encoding="utf-8")
    traffic_override = USER_TRAFFIC_OVERRIDE_ACTION.read_text(encoding="utf-8")
    hwid = USER_HWID_ACTION.read_text(encoding="utf-8")
    grant = USER_TRAFFIC_GRANT_ACTION.read_text(encoding="utf-8")

    assert "tariffActionDirty" in actions
    assert "dirty={premiumOverrideDirty}" in actions
    assert "dirty={regularOverrideDirty}" in actions
    assert "hwidLimitDirty" in actions
    assert "draftValid={premiumOverrideDraftValid}" in actions
    assert "draftValid={regularOverrideDraftValid}" in actions
    assert "hwidLimitDraftValid" in actions
    assert "grantTrafficGbValid" in actions
    assert "class:is-dirty={tariffActionDirty}" in tariff
    assert "class:is-dirty={dirty}" in traffic_override
    assert "class:is-dirty={hwidLimitDirty}" in hwid
    assert "!tariffActionDirty" in tariff
    assert "!dirty" in traffic_override
    assert "!hwidLimitDirty" in hwid
    assert "!grantTrafficGbValid" in grant


def test_action_cards_surface_unsaved_state():
    source = "\n".join(
        [
            USER_TARIFF_ACTION.read_text(encoding="utf-8"),
            USER_TRAFFIC_OVERRIDE_ACTION.read_text(encoding="utf-8"),
            USER_HWID_ACTION.read_text(encoding="utf-8"),
        ]
    )

    assert "admin-action-save-controls" in source
    assert "admin-unsaved-hint" in source
    assert "user_action_unsaved_hint" in source
    assert 'at("settings_badge_dirty"' in source

    for language in ("ru", "en"):
        messages = json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8"))
        assert messages["admin_user_action_unsaved_hint"]


def test_danger_actions_stay_last_in_user_actions_tab():
    source = _actions_source()

    squad_index = source.index("<UserSquadOverridesActionCard")
    danger_index = source.index("<UserDangerActionsCard")

    assert squad_index < danger_index
    assert source[danger_index:].strip().endswith("</Tabs.Content>")


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


def test_tariff_hwid_limit_confirm_flow_is_localized():
    modal = _source()
    tariff = USER_TARIFF_ACTION.read_text(encoding="utf-8")
    dialogs = _dialogs_source()
    store = USERS_STORE.read_text(encoding="utf-8")

    assert "tariffHwidLimitChangeAvailable" in modal
    assert "userTariffHwidConfirmOpen: true" in tariff
    assert "user_tariff_hwid_confirm_title" in dialogs
    assert "userApplyTariffHwidLimit: true" in dialogs
    assert "apply_tariff_hwid_limit" in store

    for language in ("ru", "en"):
        messages = json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text("utf-8"))
        assert messages["admin_user_tariff_hwid_confirm_title"]
        assert messages["admin_user_tariff_hwid_confirm_keep"]
        assert messages["admin_user_tariff_hwid_confirm_apply"]


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
    assert "const openSectionUserCard = $derived(" in source
    assert 'active === "payments"' in source
    assert "openPaymentUserCard" in source
    assert 'active === "logs"' in source
    assert "openLogsUserCard" in source
