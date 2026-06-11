"""Load, persist and apply runtime overrides for localization strings."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import (
    JsonI18n,
    LocaleOverrides,
    is_valid_locale_language_code,
    normalize_locale_language_code,
    normalize_locale_overrides_payload,
    resolve_locale_key,
)
from db.dal import locale_overrides_dal

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[3]
LOCALE_OVERRIDES_PATH = APP_ROOT / "data" / "locales-overrides.json"

LOCALE_GROUPS = [
    {
        "id": "admin_navigation",
        "title": "Admin navigation and shared UI",
        "description": "Sidebar, section headers, toolbar actions, filters, and shared controls.",
        "audience": "internal",
        "prefixes": (
            "admin_nav_",
            "admin_section_",
            "admin_panel_title",
            "admin_back_to_panel",
            "admin_sidebar_",
            "admin_exit",
            "admin_menu",
            "admin_language",
            "admin_page_",
            "admin_close",
            "admin_collapse",
            "admin_expand",
            "admin_show",
            "admin_hide",
            "admin_loading",
            "admin_btn_",
            "admin_filter_",
            "admin_sort_",
            "admin_status_",
            "admin_badge_",
            "admin_backups_",
            "admin_aria_",
            "admin_search",
            "admin_clear",
            "admin_save",
            "admin_saving",
            "admin_add",
            "admin_apply",
            "admin_reset",
            "admin_copy",
            "admin_copied",
            "admin_error",
            "admin_unknown_action",
            "back_to_admin_panel_button",
            "back_to_ads_list_button",
            "back_to_stats_monitoring_button",
            "back_to_user_management_button",
            "prev_page_button",
            "next_page_button",
        ),
    },
    {
        "id": "admin_dashboard",
        "title": "Admin dashboard and stats",
        "description": "Dashboard cards, revenue charts, panel sync status, and monitoring copy.",
        "audience": "internal",
        "prefixes": (
            "admin_stats_",
            "admin_financial_",
            "admin_enhanced_",
            "admin_panel_stats_",
            "admin_panel_traffic_",
            "admin_queue_",
            "admin_sync_status_",
            "admin_stats_button",
            "admin_sync_panel_button",
            "admin_sync_initiated_from_panel",
            "admin_total",
            "error_displaying_statistics",
            "inline_admin_",
            "inline_user_stats_",
            "inline_financial_",
            "inline_system_",
        ),
    },
    {
        "id": "admin_users",
        "title": "Admin users",
        "description": (
            "User lists, user cards, bans, grants, premium overrides, and direct messages."
        ),
        "audience": "internal",
        "prefixes": (
            "admin_user_",
            "admin_users_",
            "admin_hwid_",
            "admin_ban_",
            "admin_unban_",
            "admin_banned_",
            "admin_premium_override_",
            "admin_traffic_grant_",
            "admin_view_banned_",
            "user_card_",
            "user_hwid_",
            "user_premium_",
            "user_regular_",
            "user_traffic_",
            "user_override_",
            "premium_override_",
            "regular_override_",
            "traffic_grant_",
        ),
    },
    {
        "id": "admin_payments",
        "title": "Admin payments",
        "description": (
            "Payment tables, payment details, exports, provider labels, and payment stats."
        ),
        "audience": "internal",
        "prefixes": (
            "admin_payment_",
            "admin_payments_",
            "admin_no_payments",
            "admin_view_payments",
            "admin_refresh_payments",
            "admin_export_payments",
            "admin_export_sent",
            "admin_amount",
            "admin_provider",
            "admin_description",
            "admin_date",
            "admin_csv_payment_",
            "admin_csv_amount",
            "admin_csv_currency",
            "admin_csv_provider",
            "admin_csv_status",
            "admin_csv_description",
            "admin_csv_units",
            "admin_csv_months",
            "admin_csv_created_at",
        ),
    },
    {
        "id": "admin_promos_marketing",
        "title": "Admin promos, ads, and broadcasts",
        "description": "Promo management, ad campaigns, marketing tools, and broadcast workflows.",
        "audience": "internal",
        "prefixes": (
            "admin_promo_",
            "admin_promos_",
            "admin_bulk_promo_",
            "admin_ads_",
            "admin_ad_",
            "admin_broadcast_",
            "admin_create_promo_",
            "admin_create_bulk_promo_",
            "admin_active_promos_",
            "broadcast_",
            "confirm_broadcast_",
            "cancel_broadcast_",
        ),
    },
    {
        "id": "admin_tariffs",
        "title": "Admin tariffs",
        "description": (
            "Tariff catalog, tariff dialogs, legacy tariff rows, and trial tariff widgets."
        ),
        "audience": "internal",
        "prefixes": ("admin_tariff_", "admin_tariffs_", "admin_trial"),
    },
    {
        "id": "admin_support",
        "title": "Admin support inbox",
        "description": "Support ticket inbox, ticket filters, admin replies, and support statuses.",
        "audience": "internal",
        "prefixes": ("admin_support_",),
    },
    {
        "id": "admin_appearance",
        "title": "Admin appearance",
        "description": "Theme catalog, branding, logo, favicon, and public page links.",
        "audience": "internal",
        "prefixes": (
            "admin_themes_",
            "admin_appearance",
            "admin_settings_icon_",
            "admin_settings_field_webapp_",
            "admin_settings_field_subscription_mini_app_url",
            "admin_settings_field_support_link",
            "admin_settings_field_server_status_url",
            "admin_settings_field_privacy_",
            "admin_settings_field_user_agreement_",
            "appearance_",
        ),
    },
    {
        "id": "admin_settings_payments",
        "title": "Admin payment settings",
        "description": (
            "Payment method toggles, prices, provider credentials, and webhook settings."
        ),
        "audience": "internal",
        "prefixes": (
            "admin_settings_field_default_currency_",
            "admin_settings_field_month_",
            "admin_settings_field_rub_",
            "admin_settings_field_stars_",
            "admin_settings_field_traffic_packages_",
            "admin_settings_field_payment_methods_",
            "admin_settings_field_subscription_purchase_",
            "admin_settings_field_yookassa_",
            "admin_settings_field_freekassa_",
            "admin_settings_field_platega_",
            "admin_settings_field_severpay_",
            "admin_settings_field_cryptopay_",
            "admin_settings_field_wata_",
            "admin_settings_field_heleket_",
            "admin_settings_field_lava_",
        ),
    },
    {
        "id": "admin_settings_subscriptions",
        "title": "Admin subscription settings",
        "description": (
            "Panel connection, default squads, trials, referrals, device limits, and guides."
        ),
        "audience": "internal",
        "prefixes": (
            "admin_settings_field_panel_",
            "admin_settings_field_user_",
            "admin_settings_field_trial_",
            "admin_settings_field_referral_",
            "admin_settings_field_legacy_refs",
            "admin_settings_field_my_devices_",
            "admin_settings_field_subscription_guides_",
            "admin_settings_field_subscription_page_",
        ),
    },
    {
        "id": "admin_settings_notifications",
        "title": "Admin notifications and logs",
        "description": "Logging, required channel, subscription notifications, and support limits.",
        "audience": "internal",
        "prefixes": (
            "admin_settings_field_log_",
            "admin_settings_field_backup_",
            "admin_settings_field_support_",
            "admin_settings_field_subscription_notifications_",
            "admin_settings_field_subscription_notify_",
            "admin_settings_field_required_",
            "admin_settings_field_disable_welcome_",
            "admin_settings_field_start_command_",
            "admin_settings_field_default_language_",
        ),
    },
    {
        "id": "admin_settings",
        "title": "Admin settings",
        "description": (
            "Settings screen groups, subsections, helper text, and uncategorized settings."
        ),
        "audience": "internal",
        "prefixes": ("admin_settings_",),
    },
    {
        "id": "admin_translations",
        "title": "Admin translations",
        "description": "Translation override screen, language controls, and locale group labels.",
        "audience": "internal",
        "prefixes": ("admin_translations_",),
    },
    {
        "id": "admin_logs",
        "title": "Admin logs and exports",
        "description": "Activity logs, log exports, CSV headers, and event detail labels.",
        "audience": "internal",
        "prefixes": (
            "admin_logs_",
            "admin_log_",
            "admin_all_logs_",
            "admin_view_logs_",
            "admin_export_logs_",
            "admin_no_logs",
            "admin_csv_header_",
            "admin_event",
            "admin_content",
            "csv_yes",
            "csv_no",
            "error_displaying_logs_",
        ),
    },
    {
        "id": "admin_misc",
        "title": "Admin miscellaneous",
        "description": (
            "Older bot-admin labels and admin-only strings that do not fit another section."
        ),
        "audience": "internal",
        "prefixes": ("admin_",),
    },
    {
        "id": "webapp",
        "title": "Mini App",
        "description": "User-facing Mini App screens, navigation, settings, and toasts.",
        "audience": "user",
        "prefixes": ("wa_",),
    },
    {
        "id": "bot_menu",
        "title": "Telegram bot menu",
        "description": "Start menu, inline buttons, language selector, and bot-only flows.",
        "audience": "user",
        "prefixes": (
            "main_menu_",
            "menu_",
            "bot_interface_",
            "choose_language",
            "language_",
            "back_",
            "cancel_",
            "connect_",
        ),
    },
    {
        "id": "subscriptions",
        "title": "Subscriptions and devices",
        "description": (
            "Subscription status, install guides, traffic packages, trials, and devices."
        ),
        "audience": "user",
        "prefixes": (
            "subscription_",
            "trial_",
            "tariff_",
            "traffic_",
            "device_",
            "devices_",
            "my_devices_",
            "install_",
            "config_",
        ),
    },
    {
        "id": "payments",
        "title": "Payments",
        "description": "Payment provider flows, invoices, payment methods, and checkout messages.",
        "audience": "user",
        "prefixes": (
            "payment_",
            "pay_",
            "yookassa_",
            "free_kassa_",
            "freekassa_",
            "wata_",
            "heleket_",
            "cryptopay_",
            "platega_",
            "stars_",
            "autorenew_",
        ),
    },
    {
        "id": "support",
        "title": "Support",
        "description": "Support links, ticket inbox copy, ticket statuses, and notifications.",
        "audience": "user",
        "prefixes": ("support_", "ticket_"),
    },
    {
        "id": "referrals_promos",
        "title": "Referrals and promos",
        "description": "Referral program, invite copy, promo codes, and bonuses.",
        "audience": "user",
        "prefixes": ("referral_", "promo_", "invite_", "inline_referral_"),
    },
    {
        "id": "auth_security",
        "title": "Auth and security",
        "description": "Login, email verification, account linking, and security messages.",
        "audience": "user",
        "prefixes": (
            "auth_",
            "login_",
            "password_",
            "security_",
            "webapp_auth_",
            "channel_subscription_",
        ),
    },
    {
        "id": "emails",
        "title": "Emails",
        "description": "Transactional emails sent to users: login codes, payments, and reminders.",
        "audience": "user",
        "prefixes": ("email_",),
    },
    {
        "id": "notifications_sync",
        "title": "Notifications and sync",
        "description": "Admin notifications, panel sync, logs, and background status messages.",
        "audience": "internal",
        "prefixes": ("notification_", "notifications_", "sync_", "log_", "panel_"),
    },
]

DEFAULT_LOCALE_GROUP = {
    "id": "common",
    "title": "Common",
    "description": "Shared buttons, statuses, validation errors, and uncategorized strings.",
    "audience": "user",
    "prefixes": (),
}

INTERNAL_LOCALE_KEY_PREFIXES = (
    "admin_",
    "log_",
    "notification_",
    "notifications_",
    "panel_",
    "sync_",
)


@dataclass(frozen=True)
class LocaleOverridesFileState:
    exists: bool
    readable: bool
    overrides: LocaleOverrides


def _valid_languages(i18n: JsonI18n) -> set[str]:
    return set((i18n.base_locales_data or i18n.locales_data or {}).keys())


def _valid_keys_by_language(i18n: JsonI18n) -> Dict[str, set[str]]:
    source = i18n.base_locales_data or i18n.locales_data or {}
    return {
        lang: {str(key) for key in messages}
        for lang, messages in source.items()
        if isinstance(messages, dict)
    }


def _normalize_for_i18n(i18n: JsonI18n, payload: object) -> tuple[LocaleOverrides, Dict[str, str]]:
    return normalize_locale_overrides_payload(
        payload,
        valid_languages=_valid_languages(i18n),
        valid_keys_by_language=_valid_keys_by_language(i18n),
        allow_extra_languages=True,
    )


def _flatten(overrides: LocaleOverrides) -> Iterable[Tuple[str, str, str]]:
    for lang, messages in overrides.items():
        for key, value in messages.items():
            yield lang, key, value


def _flat_map(overrides: LocaleOverrides) -> Dict[Tuple[str, str], str]:
    return {(lang, key): value for lang, key, value in _flatten(overrides)}


def _count_overrides(overrides: LocaleOverrides) -> int:
    return sum(len(messages) for messages in overrides.values())


def _read_locale_overrides_file_state(
    i18n: JsonI18n,
    *,
    path: Path = LOCALE_OVERRIDES_PATH,
) -> LocaleOverridesFileState:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return LocaleOverridesFileState(exists=False, readable=False, overrides={})
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read locale overrides from %s: %s", path, exc)
        return LocaleOverridesFileState(exists=True, readable=False, overrides={})

    overrides, errors = _normalize_for_i18n(i18n, payload)
    if errors:
        logger.warning("Skipping invalid locale override entries from %s: %s", path, errors)
    return LocaleOverridesFileState(exists=True, readable=True, overrides=overrides)


def read_locale_overrides_file(
    i18n: JsonI18n,
    *,
    path: Path = LOCALE_OVERRIDES_PATH,
) -> LocaleOverrides:
    return _read_locale_overrides_file_state(i18n, path=path).overrides


def write_locale_overrides_file(
    overrides: LocaleOverrides,
    *,
    path: Path = LOCALE_OVERRIDES_PATH,
) -> bool:
    payload = {
        lang: dict(sorted(messages.items()))
        for lang, messages in sorted(overrides.items())
        if messages
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return True
    except OSError as exc:
        logger.warning("Failed to write locale overrides to %s: %s", path, exc)
        return False


async def _replace_db_overrides(
    session: AsyncSession,
    desired_overrides: LocaleOverrides,
    *,
    updated_by: Optional[int] = None,
) -> int:
    current = _flat_map(await locale_overrides_dal.get_all_overrides(session))
    desired = _flat_map(desired_overrides)
    changes: Dict[Tuple[str, str], Tuple[bool, str]] = {}

    for identity, value in desired.items():
        if current.get(identity) != value:
            changes[identity] = (True, value)
    for identity in current:
        if identity not in desired:
            changes[identity] = (False, "")

    if changes:
        await locale_overrides_dal.bulk_apply(session, updates=changes, updated_by=updated_by)
    return len(changes)


async def load_locale_overrides(
    i18n: JsonI18n,
    async_session_factory: sessionmaker,
    *,
    overrides_path: Path = LOCALE_OVERRIDES_PATH,
) -> int:
    """Load locale overrides and keep the DB mirror in sync.

    A valid JSON file is the source of truth. The DB is used as a fallback only
    when the file is missing or cannot be read/parsed.
    """

    i18n.configure_overrides_file(overrides_path)
    file_state = _read_locale_overrides_file_state(i18n, path=overrides_path)
    try:
        async with async_session_factory() as session:
            if file_state.readable:
                async with session.begin():
                    changed = await _replace_db_overrides(
                        session,
                        file_state.overrides,
                        updated_by=None,
                    )
                i18n.set_locale_overrides(file_state.overrides)
                i18n.configure_overrides_file(overrides_path)
                logger.info(
                    "Applied %s locale overrides from %s and synced %s DB rows",
                    _count_overrides(file_state.overrides),
                    overrides_path,
                    changed,
                )
                return _count_overrides(file_state.overrides)

            db_overrides = await locale_overrides_dal.get_all_overrides(session)
    except Exception as exc:
        logger.warning("Could not load locale overrides from DB: %s", exc)
        if file_state.readable:
            i18n.set_locale_overrides(file_state.overrides)
            return _count_overrides(file_state.overrides)
        i18n.set_locale_overrides({})
        return 0

    normalized, errors = _normalize_for_i18n(i18n, db_overrides)
    if errors:
        logger.warning("Skipping invalid DB locale override entries: %s", errors)
    try:
        async with async_session_factory() as session:
            async with session.begin():
                changed = await _replace_db_overrides(session, normalized, updated_by=None)
        if changed:
            logger.info("Canonicalized %s DB locale override rows", changed)
    except Exception as exc:
        logger.warning("Could not canonicalize DB locale overrides: %s", exc)
    i18n.set_locale_overrides(normalized)
    if not file_state.exists:
        logger.info(
            "Locale overrides file %s is missing; trying to bootstrap it from DB state",
            overrides_path,
        )
        file_written = write_locale_overrides_file(normalized, path=overrides_path)
        if file_written:
            i18n.configure_overrides_file(overrides_path)
            logger.info("Created locale overrides file %s from DB state", overrides_path)
    logger.info("Applied %s locale overrides from DB fallback", _count_overrides(normalized))
    return _count_overrides(normalized)


async def update_locale_overrides(
    i18n: JsonI18n,
    async_session_factory: sessionmaker,
    *,
    updates: Dict[str, Dict[str, Any]],
    deletes: Optional[List[Dict[str, str]]] = None,
    actor_id: Optional[int] = None,
    overrides_path: Path = LOCALE_OVERRIDES_PATH,
) -> Dict[str, Any]:
    deletes = list(deletes or [])
    normalized_updates, errors = _normalize_for_i18n(i18n, updates)

    normalized_deletes: List[Tuple[str, str]] = []
    valid_languages = _valid_languages(i18n)
    valid_keys = {key for keys in _valid_keys_by_language(i18n).values() for key in keys}
    for item in deletes:
        if not isinstance(item, dict):
            errors.setdefault("_deletes", "invalid_delete")
            continue
        lang = normalize_locale_language_code(
            item.get("lang"),
            valid_languages=None,
            prefer_known_base=False,
        )
        key = resolve_locale_key(item.get("key"))
        error_key = f"{lang or '_language'}.{key or '_key'}"
        if lang not in valid_languages and not is_valid_locale_language_code(lang):
            errors.setdefault(error_key, "invalid_language")
            continue
        if key not in valid_keys:
            errors.setdefault(error_key, "unknown_key")
            continue
        normalized_deletes.append((lang, key))

    if errors:
        return {"ok": False, "errors": errors}

    async with async_session_factory() as session:
        db_overrides = await locale_overrides_dal.get_all_overrides(session)

    file_state = _read_locale_overrides_file_state(i18n, path=overrides_path)
    source_overrides = file_state.overrides if file_state.readable else db_overrides
    desired, source_errors = _normalize_for_i18n(i18n, source_overrides)
    if source_errors:
        logger.warning("Skipping invalid locale override entries before update: %s", source_errors)

    for lang, messages in normalized_updates.items():
        desired.setdefault(lang, {}).update(messages)
    for lang, key in normalized_deletes:
        if lang in desired:
            desired[lang].pop(key, None)
            if not desired[lang]:
                desired.pop(lang, None)
    desired = {
        lang: dict(sorted(messages.items()))
        for lang, messages in sorted(desired.items())
        if messages
    }

    file_written = write_locale_overrides_file(desired, path=overrides_path)
    if not file_written and file_state.exists and file_state.readable:
        return {"ok": False, "errors": {"_file": "write_failed"}}

    async with async_session_factory() as session:
        async with session.begin():
            await _replace_db_overrides(session, desired, updated_by=actor_id)

    i18n.set_locale_overrides(desired)
    if file_written:
        i18n.configure_overrides_file(overrides_path)

    return {
        "ok": True,
        "applied": sum(len(messages) for messages in normalized_updates.values()),
        "reverted": len(normalized_deletes),
        "file_written": file_written,
    }


def group_id_for_locale_key(key: str) -> str:
    for group in LOCALE_GROUPS:
        if any(key.startswith(prefix) or key == prefix for prefix in group["prefixes"]):
            return str(group["id"])
    return str(DEFAULT_LOCALE_GROUP["id"])


def audience_for_locale_key(key: str) -> str:
    if key.startswith(INTERNAL_LOCALE_KEY_PREFIXES):
        return "internal"
    group_id = group_id_for_locale_key(key)
    for group in [*LOCALE_GROUPS, DEFAULT_LOCALE_GROUP]:
        if group["id"] == group_id:
            return str(group.get("audience") or "user")
    return "user"


def locale_group_catalog() -> List[Dict[str, Any]]:
    catalog: List[Dict[str, Any]] = []
    for group in [*LOCALE_GROUPS, DEFAULT_LOCALE_GROUP]:
        item = {key: value for key, value in group.items() if key != "prefixes"}
        item["title_key"] = f"translations_group_{item['id']}"
        item["description_key"] = f"translations_group_{item['id']}_hint"
        catalog.append(item)
    return catalog
