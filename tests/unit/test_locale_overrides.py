import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.webapp import common as webapp_common
from bot.app.web.webapp.common import _normalize_language
from bot.keyboards.inline.user_keyboards import get_language_selection_keyboard
from bot.middlewares.i18n import (
    LOCALE_KEY_ALIASES,
    JsonI18n,
    normalize_locale_overrides_payload,
    resolve_locale_key,
)
from bot.services import locale_override_service
from bot.services.email_templates import render_login_code
from bot.services.locale_override_service import audience_for_locale_key, group_id_for_locale_key

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCALE_CALL_RE = re.compile(
    r"""(?P<fn>\bat\b|\bt\b|\bgettext\b|\bget_text\b|\btranslator\b|(?<![\w.])_)"""
    r"""\(\s*(?:key\s*=\s*)?["'](?P<key>[^"']+)["']"""
)


class _Begin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Session:
    def begin(self):
        return _Begin()

    async def commit(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SessionFactory:
    def __call__(self):
        return _Session()


def _write_locale(path: Path, lang: str, messages: dict[str, str]) -> None:
    (path / f"{lang}.json").write_text(
        json.dumps(messages, ensure_ascii=False),
        encoding="utf-8",
    )


def _source_files(*roots: str) -> list[Path]:
    result: list[Path] = []
    for root in roots:
        path = REPO_ROOT / root
        if path.is_file():
            result.append(path)
        else:
            result.extend(
                child for child in path.rglob("*") if child.suffix in {".py", ".js", ".svelte"}
            )
    return result


def _collect_locale_usage(
    paths: list[Path],
    locale_keys: set[str],
    *,
    frontend_admin: bool = False,
    exclude_admin_frontend: bool = False,
) -> dict[str, set[str]]:
    usage: dict[str, set[str]] = {}
    for path in paths:
        relative = path.relative_to(REPO_ROOT).as_posix()
        if exclude_admin_frontend and (
            relative.startswith(("frontend/src/admin/", "frontend/src/lib/admin/"))
            or relative == "frontend/src/adminEntry.ts"
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in LOCALE_CALL_RE.finditer(text):
            key = match.group("key")
            actual_key = f"admin_{key}" if frontend_admin and match.group("fn") == "at" else key
            resolved_key = resolve_locale_key(actual_key)
            if resolved_key in locale_keys:
                usage.setdefault(resolved_key, set()).add(relative)
    return usage


def test_webapp_duration_and_month_formatters_use_locale_catalog(monkeypatch) -> None:
    i18n = JsonI18n(path=str(REPO_ROOT / "locales"), default="en")
    monkeypatch.setattr(webapp_common, "get_i18n_instance", lambda: i18n)

    assert webapp_common._format_remaining(0, "en") == "Subscription inactive"
    assert webapp_common._format_remaining(0, "ru") == "Подписка не активна"
    assert webapp_common._format_remaining(90061, "en") == "1 d. 1 h."
    assert webapp_common._format_remaining(90061, "ru") == "1 д. 1 ч."
    assert webapp_common._format_remaining(3661, "en") == "1 h. 1 min."
    assert webapp_common._format_remaining(3661, "ru") == "1 ч. 1 мин."
    assert webapp_common._format_remaining(30, "en") == "1 min."
    assert webapp_common._format_remaining(30, "ru") == "1 мин."
    assert webapp_common._format_months_title(1, "en") == "1 month"
    assert webapp_common._format_months_title(3, "ru") == "3 месяца"
    assert webapp_common._format_months_title(12, "ru") == "12 месяцев"


def test_json_i18n_applies_locale_overrides(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет, {name}!", "plain": "База"})
    _write_locale(locales, "en", {"welcome": "Hello, {name}!", "plain": "Base"})

    i18n = JsonI18n(str(locales), default="ru")
    i18n.set_locale_overrides({"ru": {"welcome": "Добрый день, {name}!"}})

    assert i18n.gettext("ru", "welcome", name="Анна") == "Добрый день, Анна!"
    assert i18n.gettext("ru", "plain") == "База"
    assert i18n.base_locales_data["ru"]["welcome"] == "Привет, {name}!"


def test_json_i18n_resolves_locale_key_aliases(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"wa_back": "Назад"})
    _write_locale(locales, "en", {"wa_back": "Back"})

    i18n = JsonI18n(str(locales), default="ru")

    assert resolve_locale_key("admin_back") == "wa_back"
    assert i18n.gettext("ru", "admin_back") == "Назад"
    assert i18n.gettext("en", "admin_back") == "Back"


def test_json_i18n_applies_override_only_language_with_default_fallback(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет", "plain": "База"})
    _write_locale(locales, "en", {"welcome": "Hello", "plain": "Base"})

    i18n = JsonI18n(str(locales), default="ru")
    i18n.set_locale_overrides({"de": {"welcome": "Hallo"}})

    assert i18n.gettext("de", "welcome") == "Hallo"
    assert i18n.gettext("de-DE", "welcome") == "Hallo"
    assert i18n.gettext("de", "plain") == "База"
    assert i18n.locales_data["de"]["welcome"] == "Hallo"


def test_language_options_include_override_only_languages(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})

    i18n = JsonI18n(str(locales), default="ru")
    i18n.set_locale_overrides({"uk": {"welcome": "Вітаю"}, "pt-br": {"welcome": "Olá"}})

    options = i18n.language_options()

    assert [item["code"] for item in options] == ["ru", "en", "pt-br", "uk"]
    assert options[-1]["label"] == "Ukrainian"
    assert options[-1]["base"] is False


def test_language_keyboard_includes_override_only_languages(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"back_to_main_menu_button": "Назад"})
    _write_locale(locales, "en", {"back_to_main_menu_button": "Back"})

    i18n = JsonI18n(str(locales), default="ru")
    i18n.set_locale_overrides({"uk": {"back_to_main_menu_button": "Назад"}})

    keyboard = get_language_selection_keyboard(i18n, "uk")
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert any(button.callback_data == "set_lang_uk" for button in buttons)
    assert any("Ukrainian" in button.text and "✅" in button.text for button in buttons)


def test_webapp_language_normalizer_accepts_valid_extra_languages():
    assert _normalize_language("uk") == "uk"
    assert _normalize_language("pt-BR") == "pt-br"
    assert _normalize_language("bad code") == "ru"


def test_email_templates_use_override_only_language_without_base_locale_file(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    base_messages = {
        "email_login_code_subject": "Code {code}",
        "email_login_code_preheader": "Expires in {minutes}",
        "email_login_code_heading": "Login",
        "email_login_code_intro": "Intro",
        "email_login_code_expiry_html": "Expires in <strong>{minutes}</strong>",
        "email_login_code_security": "Ignore this email.",
        "email_footer_auto": "{brand}",
        "email_login_code_text": "Code {code}; {minutes}",
    }
    _write_locale(locales, "ru", base_messages)
    _write_locale(locales, "en", base_messages)

    i18n = JsonI18n(str(locales), default="ru")
    i18n.set_locale_overrides(
        {
            "pt-br": {
                "email_login_code_subject": "Código {code}",
                "email_login_code_text": "Seu código é {code}",
            }
        }
    )
    settings = SimpleNamespace(
        DEFAULT_LANGUAGE="ru",
        EMAIL_CODE_TTL_SECONDS=600,
        WEBAPP_LOGO_URL="",
        WEBAPP_PRIMARY_COLOR="#00fe7a",
        WEBAPP_TITLE="Remnawave",
    )

    content = render_login_code(
        settings,
        code="123456",
        language_code="pt-BR",
        purpose="login",
        i18n=i18n,
    )

    assert content.subject == "Código 123456"
    assert content.text == "Seu código é 123456"


def test_locale_override_file_reload_replaces_effective_messages(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    overrides_path = tmp_path / "locales-overrides.json"
    overrides_path.write_text('{"ru":{"welcome":"Первый"}}', encoding="utf-8")

    i18n = JsonI18n(str(locales), default="ru", overrides_path=str(overrides_path))
    assert i18n.gettext("ru", "welcome") == "Первый"

    overrides_path.write_text('{"ru":{"welcome":"Второй"}}', encoding="utf-8")
    i18n._overrides_file_next_check = 0

    assert i18n.gettext("ru", "welcome") == "Второй"


def test_locale_override_file_removal_keeps_current_overrides(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    overrides_path = tmp_path / "locales-overrides.json"
    overrides_path.write_text('{"ru":{"welcome":"Из файла"}}', encoding="utf-8")

    i18n = JsonI18n(str(locales), default="ru", overrides_path=str(overrides_path))
    assert i18n.gettext("ru", "welcome") == "Из файла"

    overrides_path.unlink()
    i18n._overrides_file_next_check = 0

    assert i18n.gettext("ru", "welcome") == "Из файла"


def test_normalize_locale_overrides_rejects_unknown_keys():
    overrides, errors = normalize_locale_overrides_payload(
        {"ru": {"known": "ok", "missing": "bad"}},
        valid_languages={"ru"},
        valid_keys_by_language={"ru": {"known"}},
    )

    assert overrides == {"ru": {"known": "ok"}}
    assert errors == {"ru.missing": "unknown_key"}


def test_normalize_locale_overrides_allows_extra_languages_when_enabled():
    overrides, errors = normalize_locale_overrides_payload(
        {"pt-BR": {"known": "ok"}, "bad code": {"known": "bad"}},
        valid_languages={"ru", "en"},
        valid_keys_by_language={"ru": {"known"}, "en": {"known"}},
        allow_extra_languages=True,
    )

    assert overrides == {"pt-br": {"known": "ok"}}
    assert errors == {"bad code": "invalid_language"}


def test_normalize_locale_overrides_canonicalizes_alias_keys():
    overrides, errors = normalize_locale_overrides_payload(
        {"ru": {"admin_back": "Назад", "wa_back": "Назад!"}},
        valid_languages={"ru", "en"},
        valid_keys_by_language={"ru": {"wa_back"}, "en": {"wa_back"}},
    )

    assert errors == {}
    assert overrides == {"ru": {"wa_back": "Назад!"}}


def test_base_locale_files_do_not_store_alias_keys():
    for lang in ("en", "ru"):
        messages = json.loads((REPO_ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        assert sorted(set(messages) & set(LOCALE_KEY_ALIASES)) == []


def test_admin_locale_keys_are_split_into_smaller_internal_groups():
    expected_groups = {
        "admin_nav_support": "admin_navigation",
        "admin_stats_revenue_title": "admin_dashboard",
        "error_displaying_statistics": "admin_dashboard",
        "inline_admin_user_stats_title": "admin_dashboard",
        "inline_user_stats_message": "admin_dashboard",
        "inline_financial_description": "admin_dashboard",
        "inline_system_stats_message": "admin_dashboard",
        "admin_user_card_title": "admin_users",
        "admin_hwid_limit_title": "admin_users",
        "user_card_open_profile_button": "admin_users",
        "user_hwid_limit_card_title": "admin_users",
        "user_premium_override_card_title": "admin_users",
        "traffic_grant_regular_done": "admin_users",
        "admin_payment_detail_title": "admin_payments",
        "admin_promo_management_title": "admin_promos_marketing",
        "broadcast_target_all_button": "admin_promos_marketing",
        "confirm_broadcast_send_button": "admin_promos_marketing",
        "admin_tariffs_trial_title": "admin_tariffs",
        "admin_support_ticket_dialog": "admin_support",
        "admin_themes_catalog_title": "admin_appearance",
        "appearance_logo_uploaded_pending": "admin_appearance",
        "admin_settings_field_yookassa_enabled_label": "admin_settings_payments",
        "admin_settings_field_subscription_guides_enabled_label": ("admin_settings_subscriptions"),
        "admin_settings_field_log_level_label": "admin_settings_notifications",
        "back_to_admin_panel_button": "admin_navigation",
        "admin_translations_languages_title": "admin_translations",
        "admin_logs_menu_title": "admin_logs",
        "csv_yes": "admin_logs",
        "error_displaying_logs_too_long": "admin_logs",
    }

    for key, group_id in expected_groups.items():
        assert group_id_for_locale_key(key) == group_id
        assert audience_for_locale_key(key) == "internal"


def test_email_locale_keys_have_dedicated_user_visible_group():
    expected_email_keys = [
        "email_footer_auto",
        "email_login_code_subject",
        "email_payment_success_subject",
        "email_subscription_expiring_subject_today",
    ]

    for key in expected_email_keys:
        assert group_id_for_locale_key(key) == "emails"
        assert audience_for_locale_key(key) == "user"


def test_admin_only_locale_keys_are_internal_by_actual_source_usage():
    locale_keys = set(json.loads((REPO_ROOT / "locales" / "en.json").read_text(encoding="utf-8")))
    frontend_admin_usage = _collect_locale_usage(
        _source_files("frontend/src/admin", "frontend/src/lib/admin"),
        locale_keys,
        frontend_admin=True,
    )
    backend_admin_usage = _collect_locale_usage(
        _source_files(
            "backend/bot/handlers/admin",
            "backend/bot/keyboards/inline/admin_keyboards.py",
        ),
        locale_keys,
    )
    inline_admin_usage = _collect_locale_usage(
        _source_files("backend/bot/handlers/inline_mode.py"),
        locale_keys,
    )
    admin_usage = dict(frontend_admin_usage)
    for key, paths in [*backend_admin_usage.items(), *inline_admin_usage.items()]:
        admin_usage.setdefault(key, set()).update(paths)

    user_usage = _collect_locale_usage(
        _source_files(
            "backend/bot/handlers/user",
            "backend/bot/keyboards/inline/user_keyboards.py",
            "backend/bot/payment_providers",
            "backend/bot/app/web/webapp",
            "frontend/src",
        ),
        locale_keys,
        exclude_admin_frontend=True,
    )
    for key in locale_keys:
        if key.startswith("email_"):
            user_usage.setdefault(key, set()).add("backend/bot/services/email_templates.py")
        if key.startswith("inline_referral_"):
            user_usage.setdefault(key, set()).add("backend/bot/handlers/inline_mode.py")
    for canonical_key in set(LOCALE_KEY_ALIASES.values()):
        if canonical_key in locale_keys and audience_for_locale_key(canonical_key) == "user":
            user_usage.setdefault(canonical_key, set()).add("locale-key-aliases")

    misplaced = {
        key: sorted(paths)
        for key, paths in admin_usage.items()
        if key not in user_usage and audience_for_locale_key(key) != "internal"
    }

    assert misplaced == {}


def test_load_locale_overrides_treats_file_as_source_of_truth(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет", "plain": "База"})
    _write_locale(locales, "en", {"welcome": "Hello", "plain": "Base"})
    overrides_path = tmp_path / "locales-overrides.json"
    overrides_path.write_text(
        json.dumps({"ru": {"welcome": "Из файла"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    i18n = JsonI18n(str(locales), default="ru")
    db_state = {"ru": {"welcome": "Из БД", "plain": "Только БД"}}

    async def bulk_apply(_session, *, updates, updated_by):
        assert updated_by is None
        for (lang, key), (set_flag, value) in updates.items():
            if set_flag:
                db_state.setdefault(lang, {})[key] = value
            else:
                db_state.get(lang, {}).pop(key, None)
        for lang in list(db_state):
            if not db_state[lang]:
                db_state.pop(lang)

    async def run():
        with (
            patch.object(
                locale_override_service.locale_overrides_dal,
                "get_all_overrides",
                AsyncMock(side_effect=lambda _session: db_state),
            ),
            patch.object(
                locale_override_service.locale_overrides_dal,
                "bulk_apply",
                AsyncMock(side_effect=bulk_apply),
            ) as bulk_mock,
        ):
            count = await locale_override_service.load_locale_overrides(
                i18n,
                _SessionFactory(),
                overrides_path=overrides_path,
            )
            bulk_mock.assert_awaited_once()
            return count

    count = asyncio.run(run())

    assert count == 1
    assert db_state == {"ru": {"welcome": "Из файла"}}
    assert i18n.gettext("ru", "welcome") == "Из файла"
    assert i18n.gettext("ru", "plain") == "База"


def test_load_locale_overrides_empty_file_clears_db_overrides(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    overrides_path = tmp_path / "locales-overrides.json"
    overrides_path.write_text("{}", encoding="utf-8")
    i18n = JsonI18n(str(locales), default="ru")
    db_state = {"ru": {"welcome": "Из БД"}}

    async def bulk_apply(_session, *, updates, updated_by):
        assert updated_by is None
        for (lang, key), (set_flag, value) in updates.items():
            if set_flag:
                db_state.setdefault(lang, {})[key] = value
            else:
                db_state.get(lang, {}).pop(key, None)
        for lang in list(db_state):
            if not db_state[lang]:
                db_state.pop(lang)

    async def run():
        with (
            patch.object(
                locale_override_service.locale_overrides_dal,
                "get_all_overrides",
                AsyncMock(side_effect=lambda _session: db_state),
            ),
            patch.object(
                locale_override_service.locale_overrides_dal,
                "bulk_apply",
                AsyncMock(side_effect=bulk_apply),
            ),
        ):
            return await locale_override_service.load_locale_overrides(
                i18n,
                _SessionFactory(),
                overrides_path=overrides_path,
            )

    count = asyncio.run(run())

    assert count == 0
    assert db_state == {}
    assert i18n.gettext("ru", "welcome") == "Привет"


def test_load_locale_overrides_uses_db_when_file_missing(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    overrides_path = tmp_path / "locales-overrides.json"
    i18n = JsonI18n(str(locales), default="ru")

    async def run():
        with (
            patch.object(
                locale_override_service.locale_overrides_dal,
                "get_all_overrides",
                AsyncMock(return_value={"ru": {"welcome": "Из БД"}}),
            ),
            patch.object(
                locale_override_service.locale_overrides_dal,
                "bulk_apply",
                AsyncMock(),
            ) as bulk_mock,
        ):
            count = await locale_override_service.load_locale_overrides(
                i18n,
                _SessionFactory(),
                overrides_path=overrides_path,
            )
            bulk_mock.assert_not_awaited()
            return count

    count = asyncio.run(run())

    assert count == 1
    assert i18n.gettext("ru", "welcome") == "Из БД"
    assert json.loads(overrides_path.read_text(encoding="utf-8")) == {"ru": {"welcome": "Из БД"}}


def test_load_locale_overrides_creates_empty_file_when_file_missing_and_db_empty(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    overrides_path = tmp_path / "locales-overrides.json"
    i18n = JsonI18n(str(locales), default="ru")

    async def run():
        with patch.object(
            locale_override_service.locale_overrides_dal,
            "get_all_overrides",
            AsyncMock(return_value={}),
        ):
            return await locale_override_service.load_locale_overrides(
                i18n,
                _SessionFactory(),
                overrides_path=overrides_path,
            )

    count = asyncio.run(run())

    assert count == 0
    assert i18n.gettext("ru", "welcome") == "Привет"
    assert json.loads(overrides_path.read_text(encoding="utf-8")) == {}


def test_load_locale_overrides_uses_db_when_file_is_invalid(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    overrides_path = tmp_path / "locales-overrides.json"
    overrides_path.write_text("{not-json", encoding="utf-8")
    i18n = JsonI18n(str(locales), default="ru")

    async def run():
        with (
            patch.object(
                locale_override_service.locale_overrides_dal,
                "get_all_overrides",
                AsyncMock(return_value={"ru": {"welcome": "Из БД"}}),
            ),
            patch.object(
                locale_override_service.locale_overrides_dal,
                "bulk_apply",
                AsyncMock(),
            ) as bulk_mock,
        ):
            count = await locale_override_service.load_locale_overrides(
                i18n,
                _SessionFactory(),
                overrides_path=overrides_path,
            )
            bulk_mock.assert_not_awaited()
            return count

    count = asyncio.run(run())

    assert count == 1
    assert i18n.gettext("ru", "welcome") == "Из БД"
    assert overrides_path.read_text(encoding="utf-8") == "{not-json"


def test_update_locale_overrides_persists_applies_and_writes_file(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    i18n = JsonI18n(str(locales), default="ru")
    overrides_path = tmp_path / "locales-overrides.json"
    db_state = {}

    async def get_all(_session):
        return db_state

    async def bulk_apply(_session, *, updates, updated_by):
        assert updated_by == 7
        for (lang, key), (set_flag, value) in updates.items():
            if set_flag:
                db_state.setdefault(lang, {})[key] = value
            else:
                db_state.get(lang, {}).pop(key, None)

    async def run():
        with (
            patch.object(
                locale_override_service.locale_overrides_dal,
                "get_all_overrides",
                AsyncMock(side_effect=get_all),
            ),
            patch.object(
                locale_override_service.locale_overrides_dal,
                "bulk_apply",
                AsyncMock(side_effect=bulk_apply),
            ) as bulk_mock,
        ):
            result = await locale_override_service.update_locale_overrides(
                i18n,
                _SessionFactory(),
                updates={"ru": {"welcome": "Здравствуйте"}},
                deletes=[],
                actor_id=7,
                overrides_path=overrides_path,
            )
            bulk_mock.assert_awaited_once()
            return result

    result = asyncio.run(run())

    assert result["ok"] is True
    assert result["file_written"] is True
    assert db_state == {"ru": {"welcome": "Здравствуйте"}}
    assert i18n.gettext("ru", "welcome") == "Здравствуйте"
    assert json.loads(overrides_path.read_text(encoding="utf-8")) == {
        "ru": {"welcome": "Здравствуйте"}
    }


def test_update_locale_overrides_accepts_extra_language(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет", "plain": "База"})
    _write_locale(locales, "en", {"welcome": "Hello", "plain": "Base"})
    i18n = JsonI18n(str(locales), default="ru")
    overrides_path = tmp_path / "locales-overrides.json"
    db_state = {}

    async def get_all(_session):
        return db_state

    async def bulk_apply(_session, *, updates, updated_by):
        assert updated_by == 7
        for (lang, key), (set_flag, value) in updates.items():
            if set_flag:
                db_state.setdefault(lang, {})[key] = value
            else:
                db_state.get(lang, {}).pop(key, None)

    async def run():
        with (
            patch.object(
                locale_override_service.locale_overrides_dal,
                "get_all_overrides",
                AsyncMock(side_effect=get_all),
            ),
            patch.object(
                locale_override_service.locale_overrides_dal,
                "bulk_apply",
                AsyncMock(side_effect=bulk_apply),
            ),
        ):
            return await locale_override_service.update_locale_overrides(
                i18n,
                _SessionFactory(),
                updates={"uk": {"welcome": "Вітаю"}},
                deletes=[],
                actor_id=7,
                overrides_path=overrides_path,
            )

    result = asyncio.run(run())

    assert result["ok"] is True
    assert db_state == {"uk": {"welcome": "Вітаю"}}
    assert i18n.gettext("uk", "welcome") == "Вітаю"
    assert i18n.gettext("uk", "plain") == "База"
    assert json.loads(overrides_path.read_text(encoding="utf-8")) == {"uk": {"welcome": "Вітаю"}}


def test_update_locale_overrides_fails_when_active_file_cannot_be_written(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    i18n = JsonI18n(str(locales), default="ru")
    overrides_path = tmp_path / "locales-overrides.json"
    overrides_path.write_text(
        json.dumps({"ru": {"welcome": "Из файла"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    async def run():
        with (
            patch.object(
                locale_override_service.locale_overrides_dal,
                "get_all_overrides",
                AsyncMock(return_value={"ru": {"welcome": "Из БД"}}),
            ),
            patch.object(
                locale_override_service.locale_overrides_dal,
                "bulk_apply",
                AsyncMock(),
            ) as bulk_mock,
            patch.object(
                locale_override_service,
                "write_locale_overrides_file",
                return_value=False,
            ),
        ):
            result = await locale_override_service.update_locale_overrides(
                i18n,
                _SessionFactory(),
                updates={"ru": {"welcome": "Новое"}},
                deletes=[],
                actor_id=7,
                overrides_path=overrides_path,
            )
            bulk_mock.assert_not_awaited()
            return result

    result = asyncio.run(run())

    assert result == {"ok": False, "errors": {"_file": "write_failed"}}
    assert i18n.gettext("ru", "welcome") == "Привет"


def test_update_locale_overrides_allows_db_only_when_file_is_missing_and_unwritable(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    _write_locale(locales, "ru", {"welcome": "Привет"})
    _write_locale(locales, "en", {"welcome": "Hello"})
    i18n = JsonI18n(str(locales), default="ru")
    overrides_path = tmp_path / "locales-overrides.json"
    db_state = {}

    async def get_all(_session):
        return db_state

    async def bulk_apply(_session, *, updates, updated_by):
        assert updated_by == 7
        for (lang, key), (set_flag, value) in updates.items():
            if set_flag:
                db_state.setdefault(lang, {})[key] = value
            else:
                db_state.get(lang, {}).pop(key, None)

    async def run():
        with (
            patch.object(
                locale_override_service.locale_overrides_dal,
                "get_all_overrides",
                AsyncMock(side_effect=get_all),
            ),
            patch.object(
                locale_override_service.locale_overrides_dal,
                "bulk_apply",
                AsyncMock(side_effect=bulk_apply),
            ),
            patch.object(
                locale_override_service,
                "write_locale_overrides_file",
                return_value=False,
            ),
        ):
            return await locale_override_service.update_locale_overrides(
                i18n,
                _SessionFactory(),
                updates={"ru": {"welcome": "Только БД"}},
                deletes=[],
                actor_id=7,
                overrides_path=overrides_path,
            )

    result = asyncio.run(run())

    assert result["ok"] is True
    assert result["file_written"] is False
    assert db_state == {"ru": {"welcome": "Только БД"}}
    assert i18n.gettext("ru", "welcome") == "Только БД"
