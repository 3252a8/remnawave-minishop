import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set, Tuple

from aiogram import BaseMiddleware
from aiogram.types import Update, User
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import user_dal

LocaleOverrides = Dict[str, Dict[str, str]]

_LOCALE_LANGUAGE_CODE_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
LANGUAGE_LABELS: Dict[str, str] = {
    "ru": "Русский",
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "pt-br": "Português (BR)",
    "tr": "Türkçe",
    "uk": "Українська",
}
LANGUAGE_FLAGS: Dict[str, str] = {
    "ru": "🇷🇺",
    "en": "🇬🇧",
    "de": "🇩🇪",
    "es": "🇪🇸",
    "fr": "🇫🇷",
    "pt-br": "🇧🇷",
    "tr": "🇹🇷",
    "uk": "🇺🇦",
}
DEFAULT_LANGUAGE_ORDER = ("ru", "en")
LOCALE_KEY_ALIASES: Dict[str, str] = {
    "admin_apply": "wa_apply",
    "admin_ads_col_status": "admin_status",
    "admin_ad_label_source": "admin_ads_col_source",
    "admin_back": "wa_back",
    "admin_btn_refresh": "admin_refresh",
    "admin_btn_save": "admin_save",
    "admin_btn_saving": "admin_saving",
    "admin_close": "wa_close",
    "admin_copied": "wa_copied",
    "admin_copy": "wa_copy",
    "admin_csv_amount": "admin_amount",
    "admin_csv_description": "admin_description",
    "admin_csv_payment_id": "admin_id",
    "admin_csv_status": "admin_status",
    "admin_link_copied": "wa_link_copied",
    "admin_next": "wa_next",
    "admin_payment_detail_copied": "wa_copied",
    "admin_payment_detail_provider": "admin_provider",
    "admin_payment_detail_provider_section": "admin_provider",
    "admin_payment_detail_user_section": "admin_user",
    "admin_payments_col_user_id": "admin_id",
    "admin_promo_col_code": "admin_promo_csv_code",
    "admin_promo_col_status": "admin_status",
    "admin_promo_csv_is_active": "admin_badge_active",
    "admin_promo_csv_status": "admin_status",
    "admin_promo_label_code": "admin_promo_csv_code",
    "admin_promo_unlimited_validity": "admin_promo_unlimited",
    "admin_stats_revenue_custom_range_apply": "wa_apply",
    "admin_stats_revenue_tooltip_amount": "admin_amount",
    "admin_stats_sync_status": "admin_status",
    "admin_status_active": "admin_badge_active",
    "admin_support_category": "wa_support_category",
    "admin_support_category_account": "wa_support_category_account",
    "admin_support_category_billing": "wa_support_category_billing",
    "admin_support_category_other": "wa_support_category_other",
    "admin_support_category_technical": "wa_support_category_technical",
    "admin_support_close_ticket": "wa_close",
    "admin_support_empty": "wa_support_empty",
    "admin_support_filter_active": "wa_support_filter_active",
    "admin_support_filter_all": "wa_support_filter_all",
    "admin_support_internal_note": "wa_support_internal_note",
    "admin_support_no_messages": "wa_support_no_messages",
    "admin_support_priority": "wa_support_priority",
    "admin_support_priority_high": "wa_support_priority_high",
    "admin_support_priority_low": "wa_support_priority_low",
    "admin_support_priority_normal": "wa_support_priority_normal",
    "admin_support_priority_urgent": "wa_support_priority_urgent",
    "admin_support_role_system": "wa_support_role_system",
    "admin_support_role_user": "admin_user",
    "admin_support_search": "admin_search",
    "admin_support_status": "admin_status",
    "admin_support_status_awaiting_admin": "wa_support_status_awaiting_admin",
    "admin_support_status_awaiting_user": "wa_support_status_awaiting_user",
    "admin_support_status_closed": "wa_support_status_closed",
    "admin_support_status_open": "wa_support_status_open",
    "admin_support_status_resolved": "wa_support_status_resolved",
    "admin_support_ticket_number": "wa_support_ticket_number",
    "admin_support_user_context": "admin_user",
    "admin_tariffs_legacy_traffic_packages": "admin_tariff_traffic_packages",
    "admin_tariffs_stat_enabled": "admin_enabled",
    "admin_user_btn_cancel": "wa_cancel",
    "admin_user_history_until": "wa_until_date",
    "admin_user_label_provider": "admin_provider",
    "admin_user_short": "admin_user",
    "admin_user_stats_total_label": "admin_total",
    "back_to_autopay_method_choice_button": "back_to_main_menu_button",
    "back_to_payment_methods_button": "back_to_main_menu_button",
    "cancel_broadcast_button": "cancel_button",
    "csv_no": "no_button",
    "csv_yes": "yes_button",
    "user_premium_override_status_unlimited": "user_regular_override_status_unlimited",
    "user_regular_override_save": "admin_save",
    "wa_devices_disconnect_title": "wa_devices_disconnect",
    "wa_install_link_copied": "wa_link_copied",
    "wa_link_email_modal_title": "wa_settings_link_email_action",
}


def resolve_locale_key(key: object) -> str:
    value = str(key or "").strip()
    seen: Set[str] = set()
    while value in LOCALE_KEY_ALIASES and value not in seen:
        seen.add(value)
        value = LOCALE_KEY_ALIASES[value]
    return value


def is_valid_locale_language_code(value: str) -> bool:
    return 2 <= len(value) <= 16 and bool(_LOCALE_LANGUAGE_CODE_RE.fullmatch(value))


def normalize_locale_language_code(
    raw: object,
    valid_languages: Optional[Set[str]] = None,
    *,
    prefer_known_base: bool = True,
) -> str:
    value = str(raw or "").strip().lower().replace("_", "-")
    if not value:
        return ""
    if prefer_known_base and valid_languages and value not in valid_languages:
        base = value.split("-", 1)[0]
        if base in valid_languages:
            return base
    return value


def _normalize_language_code(raw: object, valid_languages: Optional[Set[str]] = None) -> str:
    return normalize_locale_language_code(raw, valid_languages)


def locale_language_label(code: object) -> str:
    value = normalize_locale_language_code(code, prefer_known_base=False)
    return LANGUAGE_LABELS.get(value, value.upper())


def locale_language_flag(code: object) -> str:
    value = normalize_locale_language_code(code, prefer_known_base=False)
    return LANGUAGE_FLAGS.get(value, "🏳️")


def sort_locale_language_codes(codes: Iterable[object]) -> List[str]:
    normalized = {normalize_locale_language_code(code, prefer_known_base=False) for code in codes}
    normalized = {code for code in normalized if code and is_valid_locale_language_code(code)}
    preferred = [code for code in DEFAULT_LANGUAGE_ORDER if code in normalized]
    rest = sorted(code for code in normalized if code not in DEFAULT_LANGUAGE_ORDER)
    return [*preferred, *rest]


def locale_language_options(
    codes: Iterable[object],
    *,
    base_languages: Iterable[object] = (),
) -> List[Dict[str, Any]]:
    base_set = set(sort_locale_language_codes(base_languages))
    return [
        {
            "code": code,
            "label": locale_language_label(code),
            "flag": locale_language_flag(code),
            "base": code in base_set,
        }
        for code in sort_locale_language_codes(codes)
    ]


def _valid_locale_keys_by_language(
    locales_data: Dict[str, Dict[str, str]],
) -> Dict[str, Set[str]]:
    return {
        lang: {str(key) for key in messages.keys()}
        for lang, messages in locales_data.items()
        if isinstance(messages, dict)
    }


def normalize_locale_overrides_payload(
    payload: object,
    *,
    valid_languages: Optional[Iterable[str]] = None,
    valid_keys_by_language: Optional[Dict[str, Set[str]]] = None,
    allow_extra_languages: bool = False,
    key_aliases: Optional[Dict[str, str]] = None,
) -> Tuple[LocaleOverrides, Dict[str, str]]:
    """Normalize a user/admin supplied locale override JSON payload.

    The canonical shape is ``{"ru": {"welcome": "..."}, "en": {...}}``.
    For convenience, files may also wrap it as ``{"overrides": {...}}`` or
    ``{"locales": {...}}``.
    """

    if not isinstance(payload, dict):
        return {}, {"_payload": "invalid_payload"}

    raw_payload = payload
    for wrapper_key in ("overrides", "locales"):
        wrapped = raw_payload.get(wrapper_key)
        if isinstance(wrapped, dict):
            raw_payload = wrapped
            break

    valid_lang_set = {str(lang).lower() for lang in valid_languages or []}
    aliases = key_aliases or LOCALE_KEY_ALIASES

    def resolve_payload_key(raw_key: str) -> str:
        value = raw_key
        seen: Set[str] = set()
        while value in aliases and value not in seen:
            seen.add(value)
            value = aliases[value]
        return value

    all_valid_keys: Set[str] = set()
    if valid_keys_by_language:
        for keys in valid_keys_by_language.values():
            all_valid_keys.update(str(key) for key in keys)

    overrides: LocaleOverrides = {}
    errors: Dict[str, str] = {}

    for raw_lang, raw_messages in raw_payload.items():
        lang = normalize_locale_language_code(
            raw_lang,
            valid_lang_set or None,
            prefer_known_base=not allow_extra_languages,
        )
        error_key = str(raw_lang or "_language")
        if not lang:
            errors[error_key] = "invalid_language"
            continue
        if valid_lang_set and lang not in valid_lang_set:
            if not allow_extra_languages:
                errors[error_key] = "unknown_language"
                continue
            if not is_valid_locale_language_code(lang):
                errors[error_key] = "invalid_language"
                continue
        elif allow_extra_languages and not is_valid_locale_language_code(lang):
            errors[error_key] = "invalid_language"
            continue
        if not isinstance(raw_messages, dict):
            errors[lang] = "invalid_language_bucket"
            continue

        lang_keys = valid_keys_by_language.get(lang, set()) if valid_keys_by_language else set()
        bucket: Dict[str, str] = {}
        for raw_key, raw_value in raw_messages.items():
            raw_key_text = str(raw_key or "").strip()
            key = resolve_payload_key(raw_key_text)
            item_error_key = f"{lang}.{raw_key_text or '_key'}"
            if not raw_key_text or not key:
                errors[item_error_key] = "invalid_key"
                continue
            if all_valid_keys and key not in all_valid_keys and key not in lang_keys:
                errors[item_error_key] = "unknown_key"
                continue
            if raw_value is None:
                continue
            if not isinstance(raw_value, str):
                errors[item_error_key] = "invalid_value"
                continue
            if len(raw_value) > 20000:
                errors[item_error_key] = "value_too_long"
                continue
            if raw_key_text in aliases and key in bucket:
                continue
            bucket[key] = raw_value
        if bucket:
            overrides[lang] = dict(sorted(bucket.items()))

    return dict(sorted(overrides.items())), errors


class JsonI18n:
    def __init__(
        self,
        path: str,
        default: str = "en",
        domain: str = "bot",
        overrides_path: Optional[str] = None,
    ):
        self.domain = domain
        self.path = path
        self.default_lang = default
        self.base_locales_data: Dict[str, Dict[str, str]] = {}
        self.locale_overrides: LocaleOverrides = {}
        self.locales_data: Dict[str, Dict[str, str]] = {}
        self._overrides_path: Optional[Path] = None
        self._overrides_file_mtime_ns: Optional[int] = None
        self._overrides_file_content: Optional[str] = None
        self._overrides_file_next_check = 0.0
        self._overrides_file_check_interval_seconds = 1.0
        self._load_locales()
        if overrides_path:
            self.configure_overrides_file(overrides_path)
            self.reload_overrides_from_file(force=True)
        logging.info(
            f"JsonI18n initialized. Loaded languages: {list(self.locales_data.keys())}. Default: {self.default_lang}"  # noqa: E501
        )

    def _load_locales(self):
        if not os.path.isdir(self.path):
            logging.error(f"Locales path not found or not a directory: {self.path}")
            return
        loaded: Dict[str, Dict[str, str]] = {}
        for item in os.listdir(self.path):
            if item.endswith(".json"):
                lang_code = item.split(".")[0]
                file_path = os.path.join(self.path, item)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        loaded[lang_code] = {
                            str(key): str(value)
                            for key, value in data.items()
                            if isinstance(value, str)
                        }
                    else:
                        logging.error(
                            "Locale %s from %s is not a JSON object",
                            lang_code,
                            file_path,
                        )
                except json.JSONDecodeError as e_json_load:
                    logging.error(
                        f"Error loading locale {lang_code} from {file_path} (JSON Decode Error): {e_json_load}"  # noqa: E501
                    )
                except Exception as e_load:
                    logging.error(
                        f"Error loading locale {lang_code} from {file_path}: {e_load}",
                        exc_info=True,
                    )
        self.base_locales_data = loaded
        self._rebuild_effective_locales()

    def _rebuild_effective_locales(self) -> None:
        effective: Dict[str, Dict[str, str]] = {}
        for lang, messages in self.base_locales_data.items():
            merged = dict(messages)
            merged.update(self.locale_overrides.get(lang, {}))
            effective[lang] = merged
        fallback_base = (
            self.base_locales_data.get(self.default_lang)
            or self.base_locales_data.get("en")
            or next(iter(self.base_locales_data.values()), {})
        )
        for lang, messages in self.locale_overrides.items():
            if lang in effective:
                continue
            merged = dict(fallback_base)
            merged.update(messages)
            effective[lang] = merged
        self.locales_data = effective

    def _valid_keys_by_language(self) -> Dict[str, Set[str]]:
        return _valid_locale_keys_by_language(self.base_locales_data)

    def language_options(self) -> List[Dict[str, Any]]:
        self.reload_overrides_from_file()
        return locale_language_options(
            self.locales_data.keys(),
            base_languages=self.base_locales_data.keys(),
        )

    def merge_base_locales(
        self,
        additions: Dict[str, Dict[str, str]],
        *,
        source: str = "plugin",
    ) -> List[str]:
        """Merge extra locale keys into the base catalog without overriding
        existing core keys. Returns the list of skipped ``lang.key`` entries.
        Runtime overrides stay layered on top via the usual rebuild."""
        added = 0
        skipped: List[str] = []
        for lang, messages in additions.items():
            if not isinstance(messages, dict):
                continue
            lang_code = normalize_locale_language_code(lang, prefer_known_base=False)
            if not lang_code or not is_valid_locale_language_code(lang_code):
                logging.warning("Locale language %r from %s is invalid; skipped", lang, source)
                continue
            bucket = self.base_locales_data.setdefault(lang_code, {})
            for key, value in messages.items():
                if not isinstance(value, str):
                    continue
                if key in bucket:
                    skipped.append(f"{lang_code}.{key}")
                    continue
                bucket[key] = value
                added += 1
        if skipped:
            logging.warning(
                "Locale keys from %s already defined by the core and were skipped: %s",
                source,
                ", ".join(sorted(skipped)),
            )
        if added:
            self._rebuild_effective_locales()
        return skipped

    def set_locale_overrides(self, overrides: object) -> Dict[str, str]:
        normalized, errors = normalize_locale_overrides_payload(
            overrides,
            valid_languages=set(self.base_locales_data.keys()),
            valid_keys_by_language=self._valid_keys_by_language(),
            allow_extra_languages=True,
        )
        if errors:
            logging.warning("Some locale overrides were skipped: %s", errors)
        self.locale_overrides = normalized
        self._rebuild_effective_locales()
        return errors

    def configure_overrides_file(self, path: str | Path) -> None:
        self._overrides_path = Path(path)
        try:
            self._overrides_file_mtime_ns = self._overrides_path.stat().st_mtime_ns
        except FileNotFoundError:
            self._overrides_file_mtime_ns = None
        except OSError as exc:
            logging.warning("Failed to stat locale overrides file %s: %s", path, exc)
            self._overrides_file_mtime_ns = None

    def reload_overrides_from_file(self, *, force: bool = False) -> bool:
        if self._overrides_path is None:
            return False
        now = time.monotonic()
        if not force and now < self._overrides_file_next_check:
            return False
        self._overrides_file_next_check = now + self._overrides_file_check_interval_seconds

        try:
            stat = self._overrides_path.stat()
        except FileNotFoundError:
            if self._overrides_file_mtime_ns is None:
                return False
            self._overrides_file_mtime_ns = None
            self._overrides_file_content = None
            logging.info(
                "Locale overrides file removed; keeping current in-memory overrides until "
                "the DB fallback is reloaded"
            )
            return False
        except OSError as exc:
            logging.warning(
                "Failed to stat locale overrides file %s: %s",
                self._overrides_path,
                exc,
            )
            return False

        try:
            content = self._overrides_path.read_text(encoding="utf-8")
        except OSError as exc:
            logging.warning(
                "Failed to read locale overrides file %s: %s",
                self._overrides_path,
                exc,
            )
            return False

        if (
            not force
            and stat.st_mtime_ns == self._overrides_file_mtime_ns
            and content == self._overrides_file_content
        ):
            return False

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            logging.warning(
                "Failed to parse locale overrides file %s: %s",
                self._overrides_path,
                exc,
            )
            self._overrides_file_mtime_ns = stat.st_mtime_ns
            self._overrides_file_content = content
            return False

        self._overrides_file_mtime_ns = stat.st_mtime_ns
        self._overrides_file_content = content
        self.set_locale_overrides(payload)
        logging.info("Locale overrides reloaded from %s", self._overrides_path)
        return True

    def gettext(self, lang_code: Optional[str], key: str, **kwargs) -> str:
        self.reload_overrides_from_file()
        lookup_key = resolve_locale_key(key)

        requested_lang_code = normalize_locale_language_code(
            lang_code,
            set(self.locales_data.keys()),
            prefer_known_base=False,
        )
        requested_base_lang_code = requested_lang_code.split("-", 1)[0]

        # Determine effective language with robust fallback
        if requested_lang_code and requested_lang_code in self.locales_data:
            effective_lang_code = requested_lang_code
        elif requested_base_lang_code and requested_base_lang_code in self.locales_data:
            effective_lang_code = requested_base_lang_code
        elif self.default_lang in self.locales_data:
            effective_lang_code = self.default_lang
        elif "en" in self.locales_data:
            effective_lang_code = "en"
        else:
            effective_lang_code = requested_lang_code or self.default_lang

        lang_data = self.locales_data.get(effective_lang_code)
        if lang_data is None:
            # Try explicit fallback to English if available
            fallback_data = self.locales_data.get("en")
            if fallback_data is not None:
                text = fallback_data.get(lookup_key)
                if text is not None:
                    try:
                        return text.format(**kwargs) if kwargs else text
                    except Exception:
                        return text
            logging.warning(
                f"No language data for '{effective_lang_code}' (default '{self.default_lang}' also missing). Key '{key}' will be returned as is."  # noqa: E501
            )
            return key.format(**kwargs) if kwargs else key

        text = lang_data.get(lookup_key)
        if text is None:
            if effective_lang_code != self.default_lang:
                default_lang_data = self.locales_data.get(self.default_lang, {})
                text = default_lang_data.get(lookup_key)

            if text is None:
                logging.warning(
                    f"Translation key '{key}' not found for lang '{effective_lang_code}' or default '{self.default_lang}'. Returning key."  # noqa: E501
                )
                return key.format(**kwargs) if kwargs else key
        try:
            return text.format(**kwargs) if kwargs else text
        except KeyError as e_format:
            logging.warning(
                f"Missing format key '{e_format}' for i18n key '{key}' (lang: {effective_lang_code}). Original text: '{text}'"  # noqa: E501
            )
            return text
        except Exception as e_general_format:
            logging.error(
                f"General error formatting i18n key '{key}' (lang: {effective_lang_code}): {e_general_format}. Original text: '{text}'",  # noqa: E501
                exc_info=True,
            )
            return text


_i18n_instance_singleton: Optional[JsonI18n] = None


def get_i18n_instance(path: str = "locales", default: str = "en", domain: str = "bot") -> JsonI18n:
    global _i18n_instance_singleton
    if _i18n_instance_singleton is None:
        if not os.path.exists(path) or not os.path.isdir(path):
            logging.error(
                f"CRITICAL: Locales directory '{path}' not found. i18n will not work correctly."
            )

            _i18n_instance_singleton = JsonI18n(path=path, default=default, domain=domain)
        else:
            _i18n_instance_singleton = JsonI18n(path=path, default=default, domain=domain)
    return _i18n_instance_singleton


class I18nMiddleware(BaseMiddleware):
    def __init__(self, i18n: JsonI18n, settings: Settings):
        super().__init__()
        self.i18n = i18n
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        event_user: Optional[User] = data.get("event_from_user")

        current_language = self.i18n.default_lang

        if event_user:
            try:
                user_db_model = await user_dal.get_user_by_id(session, event_user.id)
                if (
                    user_db_model
                    and user_db_model.language_code
                    and user_db_model.language_code in self.i18n.locales_data
                ):
                    current_language = user_db_model.language_code
                elif event_user.language_code:
                    lang_prefix = event_user.language_code.split("-")[0].lower()
                    if lang_prefix in self.i18n.locales_data:
                        current_language = lang_prefix
                    elif event_user.language_code.lower() in self.i18n.locales_data:
                        current_language = event_user.language_code.lower()
            except Exception as e_db_lang:
                logging.error(
                    f"I18nMiddleware: Error fetching user lang from DB for {event_user.id}: {e_db_lang}. Falling back.",  # noqa: E501
                    exc_info=True,
                )
                if event_user.language_code:
                    lang_prefix = event_user.language_code.split("-")[0].lower()
                    if lang_prefix in self.i18n.locales_data:
                        current_language = lang_prefix
                    elif event_user.language_code.lower() in self.i18n.locales_data:
                        current_language = event_user.language_code.lower()

        data["i18n_data"] = {"i18n_instance": self.i18n, "current_language": current_language}
        return await handler(event, data)
