import json
import re
from pathlib import Path

from bot.app.web.admin_settings_manifest import manifest_payload

REPO_ROOT = Path(__file__).resolve().parents[1]

SUPPORT_RELATED_SETTINGS = (
    "LOG_SUPPORT_THREAD_ID",
    "SUPPORT_TICKETS_ENABLED",
    "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED",
    "SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS",
    "SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS",
    "SUPPORT_TICKET_MAX_BODY_LENGTH",
    "SUPPORT_TICKET_MAX_SUBJECT_LENGTH",
    "SUPPORT_TICKET_RATE_LIMIT_PER_HOUR",
)

SUBSCRIPTION_PURCHASE_DESCRIPTION_SETTINGS = (
    "SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED",
    "SUBSCRIPTION_PURCHASE_DESCRIPTION_RU",
    "SUBSCRIPTION_PURCHASE_DESCRIPTION_EN",
)

SUBSCRIPTION_GUIDE_SETTINGS = (
    "SUBSCRIPTION_GUIDES_ENABLED",
    "SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED",
    "SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED",
    "SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED",
    "SUBSCRIPTION_PAGE_CONFIG_PATH",
    "SUBSCRIPTION_PAGE_CONFIG_JSON",
)

ADMIN_TARIFF_SETTINGS_PAGE_KEYS = {
    "admin_tariffs_trial_title",
    "admin_tariffs_trial_subtitle",
    "admin_tariffs_trial_enabled",
    "admin_tariffs_trial_days",
    "admin_tariffs_trial_traffic",
    "admin_tariffs_trial_strategy",
    "admin_tariffs_trial_squads",
    "admin_tariffs_trial_squads_hint",
    "admin_tariffs_trial_add_squad",
    "admin_tariffs_trial_group_switch",
    "admin_tariffs_trial_group_switch_hint",
    "admin_tariffs_trial_group_general",
    "admin_tariffs_trial_group_general_hint",
    "admin_tariffs_trial_group_reset",
    "admin_tariffs_trial_group_reset_hint",
    "admin_tariffs_trial_group_squads",
    "admin_tariffs_trial_group_squads_hint",
    "admin_tariffs_legacy_title",
    "admin_tariffs_legacy_subtitle",
    "admin_tariffs_legacy_period",
    "admin_tariffs_legacy_enabled",
    "admin_tariffs_legacy_traffic_packages",
    "admin_tariffs_legacy_stars_traffic_packages",
    "admin_tariffs_legacy_traffic_hint",
    "admin_payment_rub",
    "admin_payment_stars",
}

ADMIN_VISIBLE_RU_KEYS = {
    "admin_appearance_theme_accent",
    "admin_clear",
    "admin_save",
    "admin_saving",
    "admin_search",
    "admin_settings_badge_override",
    "admin_settings_badge_secret",
    "admin_settings_badge_dirty",
    "admin_settings_icon_current",
    "admin_settings_icon_default_value",
    "admin_settings_icon_empty",
    "admin_settings_icon_picker_title",
    "admin_settings_icon_use_default",
    "admin_tariff_label_premium_squads",
    "admin_tariff_premium",
    "admin_tariff_squads",
    "admin_tariff_tab_premium",
}

ADMIN_AT_SIMPLE_FALLBACK_RE = re.compile(
    r"""\bat\(\s*["'`](?P<key>[^"'`$]+)["'`]\s*,\s*\{[^)]*?\}\s*,\s*["'`](?P<fallback>[^"'`$]*)["'`]""",
    re.DOTALL,
)


def _manifest_by_key() -> dict[str, dict]:
    return {item["key"]: item for item in manifest_payload()}


def _manifest_items() -> list[dict]:
    return manifest_payload()


def _locale(language: str) -> dict[str, str]:
    return json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text(encoding="utf-8"))


def test_webapp_title_is_first_general_admin_setting():
    items = _manifest_items()
    manifest = {item["key"]: item for item in items}
    field = manifest["WEBAPP_TITLE"]

    assert field["section"] == "general"
    assert field["section_order"] == 1
    assert [item["key"] for item in items if item["section"] == "general"][0] == "WEBAPP_TITLE"


def test_support_settings_manifest_uses_admin_i18n_keys():
    manifest = _manifest_by_key()

    assert manifest["SUPPORT_TICKETS_ENABLED"]["section"] == "support"
    assert manifest["SUPPORT_TICKETS_ENABLED"]["section_order"] == 8

    for setting_key in SUPPORT_RELATED_SETTINGS:
        field = manifest[setting_key]
        prefix = f"admin_settings_field_{setting_key.lower()}"

        assert field["i18n_label_key"] == f"{prefix}_label"
        assert field["i18n_description_key"] == f"{prefix}_description"


def test_support_settings_i18n_keys_exist_in_admin_locales():
    manifest = _manifest_by_key()

    for language in ("ru", "en"):
        messages = _locale(language)

        assert "admin_settings_section_support" in messages
        for setting_key in SUPPORT_RELATED_SETTINGS:
            field = manifest[setting_key]
            assert field["i18n_label_key"] in messages
            assert field["i18n_description_key"] in messages


def test_subscription_purchase_description_settings_i18n_keys_exist():
    manifest = _manifest_by_key()

    for language in ("ru", "en"):
        messages = _locale(language)
        for setting_key in SUBSCRIPTION_PURCHASE_DESCRIPTION_SETTINGS:
            field = manifest[setting_key]
            assert field["section"] == "payments"
            assert field["subsection"] == "checkout"
            assert field["i18n_label_key"] in messages
            assert field["i18n_description_key"] in messages


def test_subscription_guide_settings_i18n_keys_exist():
    manifest = _manifest_by_key()

    assert manifest["SUBSCRIPTION_GUIDES_ENABLED"]["section"] == "subscription_guides"
    assert manifest["SUBSCRIPTION_GUIDES_ENABLED"]["section_order"] == 10
    assert manifest["SUBSCRIPTION_PAGE_CONFIG_JSON"]["type"] == "json"

    for language in ("ru", "en"):
        messages = _locale(language)

        assert "admin_settings_section_subscription_guides" in messages
        for setting_key in SUBSCRIPTION_GUIDE_SETTINGS:
            field = manifest[setting_key]
            assert field["i18n_label_key"] in messages
            assert field["i18n_description_key"] in messages


def test_payment_provider_settings_include_webhook_metadata():
    manifest = _manifest_by_key()

    assert manifest["FREEKASSA_ENABLED"]["webhook_path"] == "/webhook/freekassa"
    assert manifest["FREEKASSA_ENABLED"]["provider_id"] == "freekassa"
    assert manifest["PAYMENT_PLATEGA_CRYPTO_WEBAPP_LABEL_RU"]["webhook_path"] == "/webhook/platega"
    assert manifest["YOOKASSA_SHOP_ID"]["webhook_requires_base_url"] is True
    assert "webhook_path" not in manifest["PAYMENT_STARS_WEBAPP_LABEL_RU"]


def test_legacy_tariff_settings_are_separated_from_payment_settings():
    manifest = _manifest_by_key()
    payment_method_fields = [
        item for item in _manifest_items() if item["key"] == "PAYMENT_METHODS_ORDER"
    ]

    assert len(payment_method_fields) == 1
    assert payment_method_fields[0]["section"] == "payments"
    assert manifest["MONTH_1_ENABLED"]["section"] == "pricing"
    assert manifest["MONTH_1_ENABLED"]["section_order"] == 11
    assert manifest["TRIAL_ENABLED"]["section"] == "pricing"
    assert manifest["TRIAL_ENABLED"]["subsection"] == "trial"
    assert manifest["TRIAL_SQUAD_UUIDS"]["section"] == "pricing"
    assert manifest["TRIAL_SQUAD_UUIDS"]["subsection"] == "trial"


def test_platega_settings_share_one_admin_subsection():
    manifest = _manifest_by_key()
    platega_keys = [
        key for key in manifest if key.startswith("PLATEGA_") or key.startswith("PAYMENT_PLATEGA_")
    ]

    assert platega_keys
    assert {manifest[key]["subsection"] for key in platega_keys} == {"Platega"}


def test_tariff_settings_page_i18n_keys_exist():
    for language in ("ru", "en"):
        messages = _locale(language)
        assert ADMIN_TARIFF_SETTINGS_PAGE_KEYS <= messages.keys()


def test_visible_admin_russian_labels_do_not_fall_back_to_english():
    messages = _locale("ru")

    for key in ADMIN_VISIBLE_RU_KEYS:
        assert key in messages

    missing_latin_fallbacks = []
    for file_path in (REPO_ROOT / "frontend" / "src" / "admin").rglob("*"):
        if file_path.suffix not in {".svelte", ".js"}:
            continue
        text = file_path.read_text(encoding="utf-8")
        for match in ADMIN_AT_SIMPLE_FALLBACK_RE.finditer(text):
            locale_key = f"admin_{match.group('key')}"
            fallback = match.group("fallback")
            if locale_key in messages:
                continue
            has_latin = any("A" <= char <= "Z" or "a" <= char <= "z" for char in fallback)
            has_cyrillic = any("А" <= char <= "я" or char in "Ёё" for char in fallback)
            if has_latin and not has_cyrillic:
                missing_latin_fallbacks.append((locale_key, fallback, str(file_path)))

    assert missing_latin_fallbacks == []
