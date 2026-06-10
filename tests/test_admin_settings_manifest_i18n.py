import json
import re
from pathlib import Path

import pytest

from bot.app.web.admin_settings_manifest import coerce_value, get_field_by_key, manifest_payload
from bot.middlewares.i18n import resolve_locale_key

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
    "PAYMENT_REQUEST_TIMEOUT_SECONDS",
)

SUBSCRIPTION_GUIDE_SETTINGS = (
    "SUBSCRIPTION_GUIDES_ENABLED",
    "SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED",
    "SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED",
    "SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED",
    "SUBSCRIPTION_PAGE_CONFIG_PATH",
    "SUBSCRIPTION_PAGE_CONFIG_JSON",
)

BACKUP_SETTINGS = (
    "BACKUP_ENABLED",
    "BACKUP_CHAT_ID",
    "BACKUP_THREAD_ID",
    "BACKUP_INTERVAL_SECONDS",
    "BACKUP_LOCAL_RETENTION",
    "BACKUP_COMPOSE_ENABLED",
)

TELEGRAM_ANTIFLOOD_SETTINGS = (
    "TELEGRAM_DROP_NON_PRIVATE_UPDATES",
    "TELEGRAM_ANTIFLOOD_ENABLED",
    "TELEGRAM_ANTIFLOOD_WINDOW_SECONDS",
    "TELEGRAM_ANTIFLOOD_MAX_UPDATES_PER_WINDOW",
    "TELEGRAM_ANTIFLOOD_MESSAGE_MAX_PER_WINDOW",
    "TELEGRAM_ANTIFLOOD_CALLBACK_MAX_PER_WINDOW",
    "TELEGRAM_ANTIFLOOD_INLINE_MAX_PER_WINDOW",
    "TELEGRAM_ANTIFLOOD_START_MAX_PER_WINDOW",
    "TELEGRAM_ANTIFLOOD_EXPENSIVE_CALLBACK_MAX_PER_WINDOW",
    "TELEGRAM_ACTION_COOLDOWN_ENABLED",
    "TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS",
    "TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS",
)

REMNASHOP_MIGRATION_SETTINGS = (
    "MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED",
    "MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED",
    "MIGRATION_REMNASHOP_IMPORTED_AT",
    "MIGRATION_REMNASHOP_NOTES",
)

ADMIN_TARIFF_SETTINGS_PAGE_KEYS = {
    "admin_tariffs_trial_title",
    "admin_tariffs_trial_subtitle",
    "admin_tariffs_trial_enabled",
    "admin_tariffs_trial_without_telegram_enabled",
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
    "admin_tariffs_referral_title",
    "admin_tariffs_referral_subtitle",
    "admin_tariffs_referral_group_welcome",
    "admin_tariffs_referral_group_welcome_hint",
    "admin_tariffs_referral_welcome_bonus_days",
    "admin_tariffs_referral_without_telegram",
    "admin_tariffs_referral_group_rules",
    "admin_tariffs_referral_group_rules_hint",
    "admin_tariffs_referral_one_bonus_per_referee",
    "admin_tariffs_referral_legacy_refs",
    "admin_tariffs_referral_disposable_domains",
    "admin_tariffs_referral_disposable_domains_hint",
    "admin_tariffs_legacy_title",
    "admin_tariffs_legacy_subtitle",
    "admin_tariffs_legacy_period",
    "admin_tariffs_legacy_enabled",
    "admin_tariffs_legacy_ref_inviter",
    "admin_tariffs_legacy_ref_referee",
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


def _has_locale_key(messages: dict[str, str], key: str) -> bool:
    return resolve_locale_key(key) in messages


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

    timeout_field = manifest["PAYMENT_REQUEST_TIMEOUT_SECONDS"]
    assert timeout_field["type"] == "float"
    assert timeout_field["optional"] is False
    assert timeout_field["min"] == 1

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


def test_backup_settings_i18n_keys_exist():
    manifest = _manifest_by_key()

    assert manifest["BACKUP_ENABLED"]["section"] == "backups"
    assert manifest["BACKUP_ENABLED"]["section_order"] == 9
    assert manifest["BACKUP_INTERVAL_SECONDS"]["min"] == 60
    assert manifest["BACKUP_INTERVAL_SECONDS"]["optional"] is False
    assert manifest["BACKUP_LOCAL_RETENTION"]["min"] == 1
    assert manifest["BACKUP_LOCAL_RETENTION"]["optional"] is False

    for language in ("ru", "en"):
        messages = _locale(language)

        assert "admin_settings_section_backups" in messages
        for setting_key in BACKUP_SETTINGS:
            field = manifest[setting_key]
            assert field["i18n_label_key"] in messages
            assert field["i18n_description_key"] in messages


def test_telegram_antiflood_settings_i18n_keys_exist():
    manifest = _manifest_by_key()

    for setting_key in TELEGRAM_ANTIFLOOD_SETTINGS:
        field = manifest[setting_key]
        assert field["section"] == "system"
        assert field["section_order"] == 12
        assert field["subsection"] == "telegram_antiflood"
        assert field["i18n_subsection_key"] == "admin_settings_subsection_telegram_antiflood"

    assert manifest["TELEGRAM_ANTIFLOOD_WINDOW_SECONDS"]["min"] == 1
    for setting_key in (
        "TELEGRAM_ANTIFLOOD_MAX_UPDATES_PER_WINDOW",
        "TELEGRAM_ANTIFLOOD_MESSAGE_MAX_PER_WINDOW",
        "TELEGRAM_ANTIFLOOD_CALLBACK_MAX_PER_WINDOW",
        "TELEGRAM_ANTIFLOOD_INLINE_MAX_PER_WINDOW",
        "TELEGRAM_ANTIFLOOD_START_MAX_PER_WINDOW",
        "TELEGRAM_ANTIFLOOD_EXPENSIVE_CALLBACK_MAX_PER_WINDOW",
        "TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS",
        "TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS",
    ):
        assert manifest[setting_key]["min"] == 0

    for language in ("ru", "en"):
        messages = _locale(language)

        assert "admin_settings_section_system" in messages
        assert "admin_settings_subsection_telegram_antiflood" in messages
        for setting_key in TELEGRAM_ANTIFLOOD_SETTINGS:
            field = manifest[setting_key]
            assert field["i18n_label_key"] in messages
            assert field["i18n_description_key"] in messages


def test_remnashop_migration_settings_i18n_keys_exist():
    manifest = _manifest_by_key()

    for setting_key in REMNASHOP_MIGRATION_SETTINGS:
        field = manifest[setting_key]
        assert field["section"] == "migrations"
        assert field["section_order"] == 13
        assert field["subsection"] == "Remnashop"
        assert field["i18n_subsection_key"] == "admin_settings_subsection_remnashop"

    for language in ("ru", "en"):
        messages = _locale(language)

        assert "admin_settings_section_migrations" in messages
        assert "admin_settings_subsection_remnashop" in messages
        for setting_key in REMNASHOP_MIGRATION_SETTINGS:
            field = manifest[setting_key]
            assert field["i18n_label_key"] in messages
            assert field["i18n_description_key"] in messages


def test_backup_required_numeric_settings_reject_empty_values():
    with pytest.raises(ValueError):
        coerce_value(get_field_by_key("BACKUP_INTERVAL_SECONDS"), "")


def test_trial_required_settings_reject_empty_values():
    for key in (
        "TRIAL_ENABLED",
        "TRIAL_DURATION_DAYS",
        "TRIAL_TRAFFIC_LIMIT_GB",
        "TRIAL_TRAFFIC_STRATEGY",
        "TRIAL_WITHOUT_TELEGRAM_ENABLED",
    ):
        with pytest.raises(ValueError):
            coerce_value(get_field_by_key(key), "")


def test_payment_provider_settings_include_webhook_metadata():
    manifest = _manifest_by_key()

    assert manifest["FREEKASSA_ENABLED"]["webhook_path"] == "/webhook/freekassa"
    assert manifest["FREEKASSA_ENABLED"]["provider_id"] == "freekassa"
    assert manifest["PAYMENT_PLATEGA_CRYPTO_WEBAPP_LABEL_RU"]["webhook_path"] == "/webhook/platega"
    assert manifest["YOOKASSA_SHOP_ID"]["webhook_requires_base_url"] is True
    assert "webhook_path" not in manifest["PAYMENT_STARS_WEBAPP_LABEL_RU"]


def test_remnawave_settings_include_panel_webhook_metadata():
    manifest = _manifest_by_key()
    field = manifest["PANEL_WEBHOOK_SECRET"]
    remnawave_keys = (
        "PANEL_API_URL",
        "PANEL_API_KEY",
        "PANEL_API_TOTAL_TIMEOUT_SECONDS",
        "PANEL_API_CONNECT_TIMEOUT_SECONDS",
        "PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS",
        "PANEL_API_SOCK_READ_TIMEOUT_SECONDS",
        "PANEL_WEBHOOK_SECRET",
        "USER_SQUAD_UUIDS",
        "USER_EXTERNAL_SQUAD_UUID",
    )
    timeout_keys = remnawave_keys[2:6]

    assert field["webhook_path"] == "/webhook/panel"
    assert field["webhook_requires_base_url"] is True
    assert field["provider_id"] == "remnawave"
    assert field["webhook_hint_i18n_key"] == "admin_settings_panel_webhook_url_hint"
    for setting_key in remnawave_keys:
        assert manifest[setting_key]["section"] == "remnawave"
        assert manifest[setting_key]["section_order"] == 3
        assert manifest[setting_key]["subsection"] is None

    for setting_key in timeout_keys:
        assert manifest[setting_key]["type"] == "float"
        assert manifest[setting_key]["optional"] is False
        assert manifest[setting_key]["min"] == 1

    for language in ("ru", "en"):
        messages = _locale(language)
        assert "admin_settings_section_remnawave" in messages
        assert field["webhook_hint_i18n_key"] in messages
        for setting_key in timeout_keys:
            assert manifest[setting_key]["i18n_label_key"] in messages
            assert manifest[setting_key]["i18n_description_key"] in messages


def test_payment_provider_admin_only_toggles_are_mutually_exclusive():
    manifest = _manifest_by_key()

    assert manifest["WATA_ADMIN_ONLY_ENABLED"]["mutually_exclusive_key"] == "WATA_ENABLED"
    assert manifest["WATA_ENABLED"]["mutually_exclusive_key"] == "WATA_ADMIN_ONLY_ENABLED"
    assert (
        manifest["PLATEGA_CRYPTO_ADMIN_ONLY_ENABLED"]["mutually_exclusive_key"]
        == "PLATEGA_CRYPTO_ENABLED"
    )
    assert manifest["STARS_ADMIN_ONLY_ENABLED"]["mutually_exclusive_key"] == "STARS_ENABLED"


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
    assert manifest["TRIAL_WITHOUT_TELEGRAM_ENABLED"]["section"] == "pricing"
    assert manifest["TRIAL_WITHOUT_TELEGRAM_ENABLED"]["subsection"] == "trial"
    assert manifest["TRIAL_SQUAD_UUIDS"]["section"] == "pricing"
    assert manifest["TRIAL_SQUAD_UUIDS"]["subsection"] == "trial"
    assert manifest["REFERRAL_WELCOME_BONUS_DAYS"]["section"] == "pricing"
    assert manifest["REFERRAL_WELCOME_BONUS_DAYS"]["subsection"] == "referral"
    assert manifest["REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED"]["section"] == "pricing"
    assert manifest["REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED"]["subsection"] == "referral"
    assert manifest["REFERRAL_ONE_BONUS_PER_REFEREE"]["section"] == "pricing"
    assert manifest["REFERRAL_ONE_BONUS_PER_REFEREE"]["subsection"] == "referral"
    assert manifest["LEGACY_REFS"]["section"] == "pricing"
    assert manifest["LEGACY_REFS"]["subsection"] == "referral"
    assert manifest["DISPOSABLE_EMAIL_DOMAINS"]["section"] == "pricing"
    assert manifest["DISPOSABLE_EMAIL_DOMAINS"]["subsection"] == "referral"


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
        missing = {
            key for key in ADMIN_TARIFF_SETTINGS_PAGE_KEYS if not _has_locale_key(messages, key)
        }
        assert missing == set()


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
            if _has_locale_key(messages, locale_key):
                continue
            has_latin = any("A" <= char <= "Z" or "a" <= char <= "z" for char in fallback)
            has_cyrillic = any("А" <= char <= "я" or char in "Ёё" for char in fallback)
            if has_latin and not has_cyrillic:
                missing_latin_fallbacks.append((locale_key, fallback, str(file_path)))

    assert missing_latin_fallbacks == []
