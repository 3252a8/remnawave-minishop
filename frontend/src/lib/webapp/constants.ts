export const MANUAL_LOGOUT_FLAG_KEY = "rw_webapp_manual_logout";
export const LANGUAGE_LABELS = {
  en: "English",
  de: "Deutsch",
  es: "Español",
  fr: "Français",
  "pt-br": "Português (BR)",
  ru: "Russian",
  tr: "Türkçe",
  uk: "Ukrainian",
};
export const LANGUAGE_FLAGS = {
  en: "🇬🇧",
  de: "🇩🇪",
  es: "🇪🇸",
  fr: "🇫🇷",
  "pt-br": "🇧🇷",
  ru: "🇷🇺",
  tr: "🇹🇷",
  uk: "🇺🇦",
};
export const WEBAPP_LANGUAGE_ORDER = ["ru", "en"];
export const LOCALE_KEY_ALIASES = {
  admin_apply: "wa_apply",
  admin_ads_col_status: "admin_status",
  admin_ad_label_source: "admin_ads_col_source",
  admin_back: "wa_back",
  admin_btn_refresh: "admin_refresh",
  admin_btn_save: "admin_save",
  admin_btn_saving: "admin_saving",
  admin_close: "wa_close",
  admin_copied: "wa_copied",
  admin_copy: "wa_copy",
  admin_csv_amount: "admin_amount",
  admin_csv_description: "admin_description",
  admin_csv_payment_id: "admin_id",
  admin_csv_status: "admin_status",
  admin_link_copied: "wa_link_copied",
  admin_next: "wa_next",
  admin_payment_detail_copied: "wa_copied",
  admin_payment_detail_provider: "admin_provider",
  admin_payment_detail_provider_section: "admin_provider",
  admin_payment_detail_user_section: "admin_user",
  admin_payments_col_user_id: "admin_id",
  admin_promo_col_code: "admin_promo_csv_code",
  admin_promo_col_status: "admin_status",
  admin_promo_csv_is_active: "admin_badge_active",
  admin_promo_csv_status: "admin_status",
  admin_promo_label_code: "admin_promo_csv_code",
  admin_promo_unlimited_validity: "admin_promo_unlimited",
  admin_stats_revenue_custom_range_apply: "wa_apply",
  admin_stats_revenue_tooltip_amount: "admin_amount",
  admin_stats_sync_status: "admin_status",
  admin_status_active: "admin_badge_active",
  admin_support_category: "wa_support_category",
  admin_support_category_account: "wa_support_category_account",
  admin_support_category_billing: "wa_support_category_billing",
  admin_support_category_other: "wa_support_category_other",
  admin_support_category_technical: "wa_support_category_technical",
  admin_support_close_ticket: "wa_close",
  admin_support_empty: "wa_support_empty",
  admin_support_filter_active: "wa_support_filter_active",
  admin_support_filter_all: "wa_support_filter_all",
  admin_support_internal_note: "wa_support_internal_note",
  admin_support_no_messages: "wa_support_no_messages",
  admin_support_priority: "wa_support_priority",
  admin_support_priority_high: "wa_support_priority_high",
  admin_support_priority_low: "wa_support_priority_low",
  admin_support_priority_normal: "wa_support_priority_normal",
  admin_support_priority_urgent: "wa_support_priority_urgent",
  admin_support_role_system: "wa_support_role_system",
  admin_support_role_user: "admin_user",
  admin_support_search: "admin_search",
  admin_support_status: "admin_status",
  admin_support_status_awaiting_admin: "wa_support_status_awaiting_admin",
  admin_support_status_awaiting_user: "wa_support_status_awaiting_user",
  admin_support_status_closed: "wa_support_status_closed",
  admin_support_status_open: "wa_support_status_open",
  admin_support_status_resolved: "wa_support_status_resolved",
  admin_support_ticket_number: "wa_support_ticket_number",
  admin_support_user_context: "admin_user",
  admin_tariffs_stat_enabled: "admin_enabled",
  admin_user_btn_cancel: "wa_cancel",
  admin_user_history_until: "wa_until_date",
  admin_user_label_provider: "admin_provider",
  admin_user_short: "admin_user",
  admin_user_stats_total_label: "admin_total",
  back_to_autopay_method_choice_button: "back_to_main_menu_button",
  back_to_payment_methods_button: "back_to_main_menu_button",
  cancel_broadcast_button: "cancel_button",
  csv_no: "no_button",
  csv_yes: "yes_button",
  user_premium_override_status_unlimited: "user_regular_override_status_unlimited",
  user_regular_override_save: "admin_save",
  wa_devices_disconnect_title: "wa_devices_disconnect",
  wa_install_link_copied: "wa_link_copied",
  wa_link_email_modal_title: "wa_settings_link_email_action",
};

type LocaleAliasKey = keyof typeof LOCALE_KEY_ALIASES;

function languageCodeFromItem(item: unknown): string {
  if (typeof item === "string") return item;
  if (!item || typeof item !== "object" || !("code" in item)) return "";
  return String(item.code || "");
}

export function resolveLocaleKey(key: unknown): string {
  let value = String(key || "").trim();
  const seen = new Set<string>();
  while (value in LOCALE_KEY_ALIASES && !seen.has(value)) {
    seen.add(value);
    value = LOCALE_KEY_ALIASES[value as LocaleAliasKey];
  }
  return value;
}

export function normalizeLanguageCode(value: unknown): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/_/g, "-");
}

export function uniqueLanguageCodes(...sources: Array<unknown[] | null | undefined>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const source of sources) {
    for (const item of source || []) {
      const code = normalizeLanguageCode(languageCodeFromItem(item));
      if (!code || seen.has(code)) continue;
      seen.add(code);
      result.push(code);
    }
  }
  return result;
}

export const APP_SECTION_PATHS = {
  home: "/home",
  install: "/install",
  trial: "/trial",
  invite: "/invite",
  devices: "/devices",
  support: "/support",
  settings: "/settings",
  admin: "/admin",
};
export const ADMIN_SECTIONS = new Set([
  "stats",
  "users",
  "payments",
  "promos",
  "ads",
  "broadcast",
  "logs",
  "support",
  "tariffs",
  "appearance",
  "translations",
  "backups",
  "settings",
]);
export const TELEGRAM_WEBAPP_SCRIPT_URL = "https://telegram.org/js/telegram-web-app.js";
export const TELEGRAM_SDK_BOOT_TIMEOUT_MS = 900;
export const TELEGRAM_SDK_ACTION_TIMEOUT_MS = 1800;
export const TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS = 15000;
