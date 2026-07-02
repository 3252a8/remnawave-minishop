import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARIFF_EDITOR = REPO_ROOT / "frontend/src/admin/sections/TariffEditorModal.svelte"
TARIFF_EDITOR_TABS = REPO_ROOT / "frontend/src/admin/sections/tariffs"
TARIFFS_SECTION = REPO_ROOT / "frontend/src/admin/sections/TariffsSection.svelte"
LOCALES = (REPO_ROOT / "locales/ru.json", REPO_ROOT / "locales/en.json")


def tariff_editor_source() -> str:
    paths = [
        TARIFF_EDITOR,
        *sorted(TARIFF_EDITOR_TABS.glob("TariffEditor*Tab.svelte")),
        TARIFF_EDITOR_TABS / "tariffEditorTabUtils.ts",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_create_tariff_save_button_uses_store_validation_instead_of_key_disable():
    source = TARIFF_EDITOR.read_text(encoding="utf-8")
    save_start = source.index("onclick={tariffsStore.saveTariffDraft}")
    save_block = source[save_start : source.index("</AdminButton>", save_start)]

    assert "disabled={tariffsSaving}" in save_block
    assert "!tariffDraft.key.trim()" not in save_block


def test_tariff_editor_updates_draft_through_store_methods():
    source = tariff_editor_source()

    assert "bind:value={tariffsStore.tariffDraft" not in source
    assert "bind:value={row." not in source
    assert "tariffDraft.enabled =" not in source
    assert "updateDraftField(" in source
    assert "updateDraftRow(" in source


def test_tariff_cards_show_regular_traffic_limit():
    source = TARIFFS_SECTION.read_text(encoding="utf-8")
    facts_start = source.index('class="admin-tariff-facts"')
    facts_block = source[facts_start : source.index("</div>", facts_start)]

    assert "function tariffGbLimitLabel(" in source
    assert "tariff_regular_traffic" in facts_block
    assert "tariffMonthlyTrafficLimit(tariff)" in facts_block
    assert "tariffPremiumTrafficLimit(tariff)" in facts_block
    assert "tariffDeviceLimit(tariff)" in facts_block
    assert "premium_monthly_gb || 0" not in facts_block
    assert "tariff.hwid_device_limit ??" not in facts_block


def test_traffic_topup_always_toggle_labels_are_localized():
    source = tariff_editor_source()
    required_keys = {
        "admin_tariff_topup_always_hint",
        "admin_tariff_topup_always_label",
        "admin_tariff_premium_topup_always_hint",
        "admin_tariff_premium_topup_always_label",
    }

    for key in required_keys:
        assert key.removeprefix("admin_") in source

    for path in LOCALES:
        messages = json.loads(path.read_text(encoding="utf-8"))
        missing = sorted(required_keys - set(messages))
        assert not missing, f"{path.name} is missing {missing}"
