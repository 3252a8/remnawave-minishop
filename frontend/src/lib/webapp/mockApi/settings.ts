import SETTINGS_MANIFEST_SECTIONS from "../settingsManifest.generated.json";
import { DEV_MOCK } from "../previewMock.js";
import { DATASET, type CloneFn, type DemoRecord, type DemoSettingsField } from "./dataset";
import { demoSettingsChanges } from "./state";

type ManifestSection = DemoRecord & { fields?: (DemoRecord & { key: string })[] };

const DEMO_REFERRAL_WEBAPP_LINK = "https://minishop.app/ref/ABCD1234";
const DEMO_REFERRAL_TELEGRAM_LINK = "https://t.me/preview_bot?start=ref_uABCD1234";

function demoSettingsValuesByKey(): Map<string, DemoSettingsField> {
  const map = new Map<string, DemoSettingsField>();
  for (const section of DATASET.settingsSections || []) {
    for (const field of section.fields || []) {
      map.set(field.key, field);
    }
  }
  return map;
}

function demoRuntimeSettingValue(key: string): unknown {
  const values: DemoRecord = {
    TRIAL_WITHOUT_TELEGRAM_ENABLED: DEV_MOCK.config.trialWithoutTelegramEnabled ?? true,
    REFERRAL_WELCOME_BONUS_DAYS:
      DEV_MOCK.config.referralWelcomeBonusDays ?? DEV_MOCK.data.referral?.welcome_bonus_days ?? 3,
    REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED:
      DEV_MOCK.config.referralWelcomeWithoutTelegramEnabled ?? true,
    REFERRAL_ONE_BONUS_PER_REFEREE:
      DEV_MOCK.config.referralOneBonusPerReferee ??
      DEV_MOCK.data.referral?.one_bonus_per_referee ??
      false,
    REFERRAL_WEBAPP_LINK_ENABLED: DEV_MOCK.config.referralWebappLinkEnabled ?? true,
    REFERRAL_TELEGRAM_LINK_ENABLED: DEV_MOCK.config.referralTelegramLinkEnabled ?? true,
    LEGACY_REFS: DEV_MOCK.config.legacyRefs ?? true,
    DISPOSABLE_EMAIL_DOMAINS: DEV_MOCK.config.disposableEmailDomains || "",
  };
  return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : undefined;
}

export function demoSettingsSections(clone: CloneFn): ManifestSection[] {
  // Section/field structure comes from the manifest snapshot generated off the
  // Python source of truth (scripts/export_settings_manifest.py), so the demo
  // stays in sync with the real admin. Realistic values are overlaid per field
  // key from the dump-based dataset; fields absent there (e.g. a freshly added
  // section) simply show their placeholders.
  const demoValues = demoSettingsValuesByKey();
  const sections = clone(SETTINGS_MANIFEST_SECTIONS) as unknown as ManifestSection[];
  for (const section of sections) {
    for (const field of section.fields || []) {
      const demoField = demoValues.get(field.key);
      if (demoField) {
        if ("value" in demoField) field.value = demoField.value;
        if ("overridden" in demoField) field.overridden = demoField.overridden;
        if ("updated_at" in demoField) field.updated_at = demoField.updated_at;
        if ("source" in demoField) field.source = demoField.source;
        if (field.secret && "has_value" in demoField) field.has_value = demoField.has_value;
      } else {
        const runtimeValue = demoRuntimeSettingValue(field.key);
        if (typeof runtimeValue !== "undefined") field.value = runtimeValue;
      }
      if (demoSettingsChanges.has(field.key)) {
        const change = demoSettingsChanges.get(field.key);
        if (change?.deleted) {
          field.value = field.default ?? "";
          field.overridden = false;
        } else {
          field.value = change?.value;
          field.overridden = true;
        }
      }
    }
  }
  return sections;
}

function applyDemoSettingToMock(key: string, value: unknown): void {
  if (key === "WEBAPP_TITLE") DEV_MOCK.config.title = value || "";
  if (key === "WEBAPP_LOGO_URL") DEV_MOCK.config.logoUrl = value || "";
  if (key === "WEBAPP_FAVICON_URL" || key === "WEBAPP_LOGO_FAVICON_URL") {
    DEV_MOCK.config.faviconUrl = value || DEV_MOCK.config.faviconUrl || "";
  }
  if (key === "WEBAPP_FAVICON_USE_CUSTOM") DEV_MOCK.config.faviconUseCustom = Boolean(value);
  if (key === "TRIAL_ENABLED") {
    DEV_MOCK.config.trialEnabled = Boolean(value);
    DEV_MOCK.data.settings.trial_enabled = Boolean(value);
  }
  if (key === "TRIAL_DURATION_DAYS") {
    DEV_MOCK.config.trialDurationDays = value;
    DEV_MOCK.data.settings.trial_duration_days = Number(value || 0);
  }
  if (key === "TRIAL_TRAFFIC_LIMIT_GB") {
    DEV_MOCK.config.trialTrafficLimitGb = value;
    DEV_MOCK.data.settings.trial_traffic_limit_gb = Number(value || 0);
  }
  if (key === "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB") {
    DEV_MOCK.config.trialPremiumTrafficLimitGb = value;
  }
  if (key === "TRIAL_HWID_DEVICE_LIMIT") {
    DEV_MOCK.config.trialHwidDeviceLimit = value;
  }
  if (key === "TRIAL_TRAFFIC_STRATEGY") {
    DEV_MOCK.config.trialTrafficStrategy = value || "NO_RESET";
    DEV_MOCK.data.settings.trial_traffic_strategy = value || "NO_RESET";
  }
  if (key === "TRIAL_WITHOUT_TELEGRAM_ENABLED") {
    DEV_MOCK.config.trialWithoutTelegramEnabled = Boolean(value);
    DEV_MOCK.data.settings.trial_without_telegram_enabled = Boolean(value);
  }
  if (key === "TRIAL_SQUAD_UUIDS") DEV_MOCK.config.trialSquadUuids = value || "";
  if (key === "TRIAL_PREMIUM_SQUAD_UUIDS") {
    DEV_MOCK.config.trialPremiumSquadUuids = value || "";
  }
  if (key === "REFERRAL_WELCOME_BONUS_DAYS") {
    DEV_MOCK.config.referralWelcomeBonusDays = Number(value || 0);
    DEV_MOCK.data.referral.welcome_bonus_days = Number(value || 0);
  }
  if (key === "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED") {
    DEV_MOCK.config.referralWelcomeWithoutTelegramEnabled = Boolean(value);
    DEV_MOCK.data.referral.welcome_bonus_without_telegram_enabled = Boolean(value);
  }
  if (key === "REFERRAL_ONE_BONUS_PER_REFEREE") {
    DEV_MOCK.config.referralOneBonusPerReferee = Boolean(value);
    DEV_MOCK.data.referral.one_bonus_per_referee = Boolean(value);
  }
  if (key === "REFERRAL_WEBAPP_LINK_ENABLED") {
    const enabled = Boolean(value);
    DEV_MOCK.config.referralWebappLinkEnabled = enabled;
    DEV_MOCK.data.referral.webapp_link = enabled ? DEMO_REFERRAL_WEBAPP_LINK : null;
  }
  if (key === "REFERRAL_TELEGRAM_LINK_ENABLED") {
    const enabled = Boolean(value);
    DEV_MOCK.config.referralTelegramLinkEnabled = enabled;
    DEV_MOCK.data.referral.bot_link = enabled ? DEMO_REFERRAL_TELEGRAM_LINK : null;
  }
  if (key === "LEGACY_REFS") DEV_MOCK.config.legacyRefs = Boolean(value);
  if (key === "DISPOSABLE_EMAIL_DOMAINS") {
    DEV_MOCK.config.disposableEmailDomains = value || "";
  }
}

export function persistDemoSetting(key: string, value: unknown): void {
  demoSettingsChanges.set(key, { value, deleted: false });
  applyDemoSettingToMock(key, value);
}

export function persistDemoSettings(updates: DemoRecord | null | undefined): void {
  for (const [key, value] of Object.entries(updates || {})) {
    persistDemoSetting(key, value);
  }
}
