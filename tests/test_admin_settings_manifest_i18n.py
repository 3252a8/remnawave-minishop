import json
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


def _manifest_by_key() -> dict[str, dict]:
    return {item["key"]: item for item in manifest_payload()}


def _locale(language: str) -> dict[str, str]:
    return json.loads((REPO_ROOT / "locales" / f"{language}.json").read_text(encoding="utf-8"))


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
