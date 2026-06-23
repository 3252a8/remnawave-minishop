import type { ProviderCurrencySupport } from "./stores/tariffsStore";
import type { SettingField, SettingsDirtyEntry } from "./stores/settingsStore";

export type SettingsDirtyState = Record<string, SettingsDirtyEntry>;
export type SelectOption = { value: string; label: string };
export type ProviderSupportSummary = {
  total: number;
  enabled: number;
  configured: number;
  available: number;
  blocked: number;
};

type ProviderKey = keyof typeof PROVIDER_FALLBACK_LABELS;

export const TRIAL_SETTING_KEYS = [
  "TRIAL_ENABLED",
  "TRIAL_DURATION_DAYS",
  "TRIAL_TRAFFIC_LIMIT_GB",
  "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB",
  "TRIAL_TRAFFIC_STRATEGY",
  "TRIAL_WITHOUT_TELEGRAM_ENABLED",
  "TRIAL_SQUAD_UUIDS",
  "TRIAL_PREMIUM_SQUAD_UUIDS",
];
export const TRIAL_SWITCH_KEYS = ["TRIAL_ENABLED", "TRIAL_WITHOUT_TELEGRAM_ENABLED"];
export const TRIAL_GENERAL_KEYS = [
  "TRIAL_DURATION_DAYS",
  "TRIAL_TRAFFIC_LIMIT_GB",
  "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB",
];
export const TRIAL_RESET_KEYS = ["TRIAL_TRAFFIC_STRATEGY"];
export const TRIAL_SQUAD_KEYS = ["TRIAL_SQUAD_UUIDS", "TRIAL_PREMIUM_SQUAD_UUIDS"];
export const REFERRAL_SETTING_KEYS = [
  "REFERRAL_WELCOME_BONUS_DAYS",
  "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
  "REFERRAL_ONE_BONUS_PER_REFEREE",
  "LEGACY_REFS",
  "DISPOSABLE_EMAIL_DOMAINS",
];
export const REFERRAL_WELCOME_KEYS = [
  "REFERRAL_WELCOME_BONUS_DAYS",
  "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
];
export const REFERRAL_RULE_KEYS = [
  "REFERRAL_ONE_BONUS_PER_REFEREE",
  "LEGACY_REFS",
  "DISPOSABLE_EMAIL_DOMAINS",
];
export const DISPOSABLE_EMAIL_DOMAINS_PLACEHOLDER = "mailinator.com\ntemp-mail.org\nyopmail.com";
export const LEGACY_PERIODS = [
  [
    "1",
    "MONTH_1_ENABLED",
    "RUB_PRICE_1_MONTH",
    "STARS_PRICE_1_MONTH",
    "REFERRAL_BONUS_DAYS_INVITER_1_MONTH",
    "REFERRAL_BONUS_DAYS_REFEREE_1_MONTH",
  ],
  [
    "3",
    "MONTH_3_ENABLED",
    "RUB_PRICE_3_MONTHS",
    "STARS_PRICE_3_MONTHS",
    "REFERRAL_BONUS_DAYS_INVITER_3_MONTHS",
    "REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS",
  ],
  [
    "6",
    "MONTH_6_ENABLED",
    "RUB_PRICE_6_MONTHS",
    "STARS_PRICE_6_MONTHS",
    "REFERRAL_BONUS_DAYS_INVITER_6_MONTHS",
    "REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS",
  ],
  [
    "12",
    "MONTH_12_ENABLED",
    "RUB_PRICE_12_MONTHS",
    "STARS_PRICE_12_MONTHS",
    "REFERRAL_BONUS_DAYS_INVITER_12_MONTHS",
    "REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS",
  ],
] as const;
export const LEGACY_TARIFF_SETTING_KEYS = [
  ...LEGACY_PERIODS.flatMap((row) => row.slice(1)),
  "TRAFFIC_PACKAGES",
  "STARS_TRAFFIC_PACKAGES",
];
export const TRAFFIC_STRATEGY_OPTIONS = [
  { value: "NO_RESET", label: "NO_RESET" },
  { value: "DAY", label: "DAY" },
  { value: "WEEK", label: "WEEK" },
  { value: "MONTH", label: "MONTH" },
  { value: "MONTH_ROLLING", label: "MONTH_ROLLING" },
];

const PROVIDER_FALLBACK_LABELS = {
  cryptopay: "CryptoPay",
  freekassa: "FreeKassa",
  heleket: "Heleket",
  lava: "LAVA",
  paykilla: "PayKilla",
  platega: "Platega",
  platega_crypto: "Platega Crypto",
  platega_sbp: "Platega SBP/card",
  severpay: "SeverPay",
  stars: "Telegram Stars",
  telegram_stars: "Telegram Stars",
  wata: "Wata",
  yookassa: "YooKassa",
} as const;

const PROVIDER_SETTINGS_PATHS: Partial<Record<ProviderKey, string[]>> = {
  cryptopay: ["payments", "cryptopay"],
  freekassa: ["payments", "freekassa"],
  heleket: ["payments", "heleket"],
  lava: ["payments", "lava"],
  paykilla: ["payments", "paykilla"],
  platega: ["payments", "platega"],
  platega_crypto: ["payments", "platega", "crypto"],
  platega_sbp: ["payments", "platega", "sbp"],
  severpay: ["payments", "severpay"],
  stars: ["payments", "telegram-stars"],
  telegram_stars: ["payments", "telegram-stars"],
  wata: ["payments", "wata"],
  yookassa: ["payments", "yookassa"],
};

export function fieldFor(key: string, fieldMap: Map<string, SettingField>): SettingField {
  return fieldMap.get(key) || { key, label: key, value: "" };
}

export function valueForKey(
  key: string,
  dirty: SettingsDirtyState,
  fieldMap: Map<string, SettingField>
): unknown {
  if (dirty[key]?.deleted) return "";
  if (Object.prototype.hasOwnProperty.call(dirty, key)) {
    return dirty[key].value;
  }
  return fieldFor(key, fieldMap).value ?? "";
}

export function boolValue(
  key: string,
  dirty: SettingsDirtyState,
  fieldMap: Map<string, SettingField>
): boolean {
  const value = valueForKey(key, dirty, fieldMap);
  if (typeof value === "string") {
    return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
  }
  return Boolean(value);
}

export function inputValueForKey(
  key: string,
  dirty: SettingsDirtyState,
  fieldMap: Map<string, SettingField>
): string | number {
  const value = valueForKey(key, dirty, fieldMap);
  return typeof value === "string" || typeof value === "number" ? value : "";
}

export function textValueForKey(
  key: string,
  dirty: SettingsDirtyState,
  fieldMap: Map<string, SettingField>
): string {
  const value = valueForKey(key, dirty, fieldMap);
  return value == null ? "" : String(value);
}

export function isSettingDirty(key: string, dirty: SettingsDirtyState): boolean {
  return Boolean(dirty[key]);
}

export function dirtyCount(keys: readonly string[], dirty: SettingsDirtyState): number {
  return (keys || []).filter((key) => isSettingDirty(key, dirty)).length;
}

export function csvList(
  key: string,
  dirty: SettingsDirtyState,
  fieldMap: Map<string, SettingField>
): string[] {
  return String(valueForKey(key, dirty, fieldMap) || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function summarizeProviderSupport(
  providers: ProviderCurrencySupport[] | null | undefined
): ProviderSupportSummary {
  return (providers || []).reduce(
    (summary, provider) => {
      const enabled = Boolean(provider.enabled);
      const configured = Boolean(provider.configured);
      const supportsDefault = Boolean(provider.supports_default_currency);
      summary.total += 1;
      if (enabled) summary.enabled += 1;
      if (enabled && configured) summary.configured += 1;
      if (enabled && configured && supportsDefault) summary.available += 1;
      if (enabled && configured && !supportsDefault) summary.blocked += 1;
      return summary;
    },
    { total: 0, enabled: 0, configured: 0, available: 0, blocked: 0 }
  );
}

export function providerKey(provider: ProviderCurrencySupport): string {
  return String(provider?.id || provider?.provider_key || provider?.key || "")
    .trim()
    .toLowerCase();
}

export function providerDisplayName(provider: ProviderCurrencySupport): string {
  const key = providerKey(provider);
  return (
    provider?.provider_label ||
    provider?.provider_name ||
    PROVIDER_FALLBACK_LABELS[key as ProviderKey] ||
    PROVIDER_FALLBACK_LABELS[
      String(provider?.provider_key || "")
        .trim()
        .toLowerCase() as ProviderKey
    ] ||
    provider?.label ||
    provider?.id ||
    "—"
  );
}

export function providerSettingsPath(provider: ProviderCurrencySupport): string[] {
  if (Array.isArray(provider?.settings_path) && provider.settings_path.length) {
    return provider.settings_path.map((segment) => String(segment || "").trim()).filter(Boolean);
  }
  const key = providerKey(provider);
  const providerRouteKey = String(provider?.provider_key || "")
    .trim()
    .toLowerCase();
  const mapped =
    PROVIDER_SETTINGS_PATHS[key as ProviderKey] ||
    PROVIDER_SETTINGS_PATHS[providerRouteKey as ProviderKey];
  if (mapped) return mapped;
  const fallback = providerRouteKey || key;
  return fallback ? ["payments", fallback.replace(/_/g, "-")] : ["payments"];
}
