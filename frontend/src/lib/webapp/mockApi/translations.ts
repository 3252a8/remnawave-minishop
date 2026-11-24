import { readJsonScript } from "../browser.js";
import { DATASET, defaultClone, type CloneFn, type DemoRecord } from "./dataset";

const DEMO_I18N_SCRIPT_ID = "i18n";
const DEMO_TRANSLATION_GROUP_RULES: [string, string][] = [
  ["admin_appearance_", "admin_appearance"],
  ["admin_translations_", "admin_translations"],
  ["admin_settings_field_payment_", "admin_settings_payments"],
  ["admin_settings_field_freekassa_", "admin_settings_payments"],
  ["admin_settings_field_cryptomus_", "admin_settings_payments"],
  ["admin_settings_field_yookassa_", "admin_settings_payments"],
  ["admin_settings_field_cloudpayments_", "admin_settings_payments"],
  ["admin_settings_field_stripe_", "admin_settings_payments"],
  ["admin_settings_field_platega_", "admin_settings_payments"],
  ["admin_settings_field_tbank_", "admin_settings_payments"],
  ["admin_settings_field_subscription_", "admin_settings_subscriptions"],
  ["admin_settings_field_autorenew_", "admin_settings_subscriptions"],
  ["admin_settings_field_trial_", "admin_settings_subscriptions"],
  ["admin_settings_field_stars_", "admin_settings_subscriptions"],
  ["admin_settings_field_", "admin_settings"],
  ["admin_settings_", "admin_settings"],
  ["admin_health_", "admin_settings_notifications"],
  ["admin_support_", "admin_support"],
  ["admin_tariff", "admin_tariffs"],
  ["admin_payment", "admin_payments"],
  ["admin_promo", "admin_promos_marketing"],
  ["admin_ads_", "admin_promos_marketing"],
  ["admin_broadcast_", "admin_promos_marketing"],
  ["admin_user", "admin_users"],
  ["admin_log", "admin_logs"],
  ["admin_export", "admin_logs"],
  ["admin_stats_", "admin_dashboard"],
  ["admin_nav_", "admin_navigation"],
  ["admin_section_", "admin_navigation"],
  ["admin_", "admin_misc"],
  ["wa_", "webapp"],
  ["telegram_", "bot_menu"],
  ["subscription_", "subscriptions"],
  ["trial_", "subscriptions"],
  ["autorenew_", "subscriptions"],
  ["payment_", "payments"],
  ["referral_", "referrals_promos"],
  ["email_", "emails"],
  ["user_", "auth_security"],
];

type DemoI18nMessages = Record<string, Record<string, unknown>>;

type TranslationValue = {
  base: string;
  fallback: string;
  effective: string;
  override: string;
  overridden: boolean;
  updated_at: string | null;
  updated_by: string | null;
};

type TranslationItem = {
  key: string;
  audience: string;
  values: Record<string, TranslationValue>;
};

type TranslationGroup = DemoRecord & {
  id?: string;
  items?: TranslationItem[];
};

type TranslationsPayload = DemoRecord & {
  groups?: TranslationGroup[];
  languages?: (DemoRecord & { code?: string })[];
};

function readDemoI18nMessages(): DemoI18nMessages {
  if (typeof document === "undefined") return {};
  const payload = readJsonScript(DEMO_I18N_SCRIPT_ID);
  return payload && typeof payload === "object" ? (payload as DemoI18nMessages) : {};
}

function translationValue(base: string, fallback: string): TranslationValue {
  const effective = base || fallback || "";
  return {
    base: base || "",
    fallback: fallback || "",
    effective,
    override: "",
    overridden: false,
    updated_at: null,
    updated_by: null,
  };
}

function messageFor(messages: DemoI18nMessages, lang: string, key: string): string {
  const value = messages?.[lang]?.[key];
  return typeof value === "string" ? value : "";
}

function createLocaleTranslationItem(
  key: string,
  messages: DemoI18nMessages,
  languages: (DemoRecord & { code?: string })[]
): TranslationItem {
  const fallback =
    messageFor(messages, "ru", key) ||
    Object.values(messages || {})
      .map((bucket) => (bucket && typeof bucket === "object" ? bucket[key] : ""))
      .find((value): value is string => typeof value === "string" && Boolean(value.length)) ||
    key;
  const values: Record<string, TranslationValue> = {};
  for (const language of languages || []) {
    const code = language?.code;
    if (!code) continue;
    values[code] = translationValue(messageFor(messages, code, key) || fallback, fallback);
  }
  if (!values.ru) values.ru = translationValue(fallback, fallback);
  if (!values.en)
    values.en = translationValue(messageFor(messages, "en", key) || fallback, fallback);
  return {
    key,
    audience: key.startsWith("admin_") ? "internal" : "user",
    values,
  };
}

function targetTranslationGroup(
  groups: TranslationGroup[],
  key: string
): TranslationGroup | undefined {
  const exact = DEMO_TRANSLATION_GROUP_RULES.find(([prefix]) => key.startsWith(prefix));
  const groupId = exact?.[1] || "common";
  return (
    (groups || []).find((group) => group.id === groupId) ||
    (groups || []).find((group) => group.id === "common") ||
    (groups || [])[0]
  );
}

export function withCurrentLocaleTranslations<T extends TranslationsPayload>(payload: T): T {
  const messages = readDemoI18nMessages();
  const groups = payload?.groups || [];
  if (!groups.length || !messages || !Object.keys(messages).length) return payload;

  const existingKeys = new Set(
    groups.flatMap((group) => (group.items || []).map((item) => item.key))
  );
  const localeKeys = new Set<string>();
  for (const bucket of Object.values(messages)) {
    if (!bucket || typeof bucket !== "object") continue;
    for (const key of Object.keys(bucket)) localeKeys.add(key);
  }

  for (const key of Array.from(localeKeys).sort()) {
    if (existingKeys.has(key)) continue;
    const group = targetTranslationGroup(groups, key);
    if (!group) continue;
    group.items = group.items || [];
    group.items.push(createLocaleTranslationItem(key, messages, payload.languages || []));
    existingKeys.add(key);
  }

  for (const group of groups) {
    group.items = (group.items || []).sort((a, b) => String(a.key).localeCompare(String(b.key)));
  }
  return payload;
}

export function demoTranslationsPayload(
  clone: CloneFn = defaultClone,
  query?: URLSearchParams
): TranslationsPayload {
  const payload = withCurrentLocaleTranslations(
    clone(DATASET.translations || {}) as TranslationsPayload
  );
  const groups = payload.groups || [];
  const groupId = query?.get("group_id");
  if (groupId) return { ...payload, groups: groups.filter((group) => group.id === groupId) };
  if (query?.get("view") !== "index") return payload;
  return {
    ...payload,
    groups: groups.map((group) => {
      const counts: Record<string, { keys: number; overrides: number }> = {};
      for (const item of group.items || []) {
        const audience = item.audience || String(group.audience || "user");
        const summary = (counts[audience] ??= { keys: 0, overrides: 0 });
        summary.keys++;
        summary.overrides += Object.values(item.values || {}).filter(
          (value) => value.overridden
        ).length;
      }
      return { ...group, items: [], counts };
    }),
  };
}
