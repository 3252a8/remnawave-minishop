import { describe, expect, it } from "vitest";

import {
  boolValue,
  csvList,
  inputValueForKey,
  isLastEnabledReferralLink,
  REFERRAL_SETTING_KEYS,
  REFERRAL_WELCOME_KEYS,
  TRIAL_SETTING_KEYS,
  providerDisplayName,
  providerSettingsPath,
  referralLinkResetViolatesRequirement,
  summarizeProviderSupport,
  trafficStrategyOptions,
  valueForKey,
  type SettingsDirtyState,
} from "./tariffSettings";
import type { SettingField } from "./stores/settingsStore";
import type { ProviderCurrencySupport } from "./stores/tariffsStore";
import SETTINGS_MANIFEST_SECTIONS from "../webapp/settingsManifest.generated.json";

const fields = new Map<string, SettingField>([
  ["ENABLED", { key: "ENABLED", label: "Enabled", value: "true" }],
  ["COUNT", { key: "COUNT", label: "Count", value: 3 }],
  ["CSV", { key: "CSV", label: "CSV", value: "a, b,,c" }],
]);

describe("tariffSettings", () => {
  it("keeps the referral program switch first in the settings section", () => {
    expect(REFERRAL_SETTING_KEYS[0]).toBe("REFERRAL_PROGRAM_ENABLED");
  });

  it("gives every referral and trial setting from the manifest an admin control", () => {
    // The pricing section is hidden from the generic settings list, so a field
    // missing from these lists has no control anywhere in the admin panel.
    const pricing = SETTINGS_MANIFEST_SECTIONS.find((section) => section.id === "pricing");
    const keysIn = (subsection: string): string[] =>
      (pricing?.fields || [])
        .filter((field) => field.subsection === subsection)
        .map((field) => field.key);

    expect(keysIn("referral")).toContain("REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL");
    expect(keysIn("referral").filter((key) => !REFERRAL_SETTING_KEYS.includes(key))).toEqual([]);
    expect(keysIn("trial").filter((key) => !TRIAL_SETTING_KEYS.includes(key))).toEqual([]);
    expect(REFERRAL_WELCOME_KEYS).toEqual([
      "REFERRAL_WELCOME_BONUS_DAYS",
      "REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL",
    ]);
  });

  it("resolves values through dirty state before saved fields", () => {
    const dirty: SettingsDirtyState = {
      ENABLED: { value: false, deleted: false },
      COUNT: { value: "7", deleted: false },
    };

    expect(valueForKey("ENABLED", dirty, fields)).toBe(false);
    expect(boolValue("ENABLED", dirty, fields)).toBe(false);
    expect(inputValueForKey("COUNT", dirty, fields)).toBe("7");
    expect(csvList("CSV", {}, fields)).toEqual(["a", "b", "c"]);
  });

  it("summarizes provider availability against the default currency", () => {
    const providers = [
      { enabled: true, configured: true, supports_default_currency: true },
      { enabled: true, configured: true, supports_default_currency: false },
      { enabled: false, configured: true, supports_default_currency: true },
    ] as ProviderCurrencySupport[];

    expect(summarizeProviderSupport(providers)).toEqual({
      total: 3,
      enabled: 2,
      configured: 2,
      available: 1,
      blocked: 1,
    });
  });

  it("locks only the last enabled referral link", () => {
    const referralFields = new Map<string, SettingField>([
      [
        "REFERRAL_WEBAPP_LINK_ENABLED",
        { key: "REFERRAL_WEBAPP_LINK_ENABLED", label: "Web", value: true },
      ],
      [
        "REFERRAL_TELEGRAM_LINK_ENABLED",
        { key: "REFERRAL_TELEGRAM_LINK_ENABLED", label: "Telegram", value: false },
      ],
    ]);

    expect(isLastEnabledReferralLink("REFERRAL_WEBAPP_LINK_ENABLED", {}, referralFields)).toBe(
      true
    );
    expect(isLastEnabledReferralLink("REFERRAL_TELEGRAM_LINK_ENABLED", {}, referralFields)).toBe(
      false
    );
    expect(
      isLastEnabledReferralLink(
        "REFERRAL_WEBAPP_LINK_ENABLED",
        { REFERRAL_TELEGRAM_LINK_ENABLED: { value: true, deleted: false } },
        referralFields
      )
    ).toBe(false);

    expect(
      referralLinkResetViolatesRequirement(
        "REFERRAL_TELEGRAM_LINK_ENABLED",
        {
          REFERRAL_WEBAPP_LINK_ENABLED: { value: false, deleted: false },
          REFERRAL_TELEGRAM_LINK_ENABLED: { value: true, deleted: false },
        },
        referralFields
      )
    ).toBe(true);
  });

  it("derives provider display names and settings paths", () => {
    expect(providerDisplayName({ provider_key: "platega_sbp" } as ProviderCurrencySupport)).toBe(
      "Platega SBP/card"
    );
    expect(
      providerSettingsPath({ provider_key: "platega_card" } as ProviderCurrencySupport)
    ).toEqual(["payments", "platega", "card"]);
    expect(
      providerSettingsPath({ provider_key: "platega_crypto" } as ProviderCurrencySupport)
    ).toEqual(["payments", "platega", "crypto"]);
    expect(
      providerSettingsPath({ provider_key: "platega_international" } as ProviderCurrencySupport)
    ).toEqual(["payments", "platega", "international"]);
    expect(
      providerSettingsPath({ provider_key: "platega_all_methods" } as ProviderCurrencySupport)
    ).toEqual(["payments", "platega", "all-methods"]);
    expect(
      providerSettingsPath({ provider_key: "custom_gateway" } as ProviderCurrencySupport)
    ).toEqual(["payments", "custom-gateway"]);
  });

  it("builds localized traffic strategy options shared by tariff, trial, and user forms", () => {
    const options = trafficStrategyOptions((key, _params, fallback) => `ru:${fallback || key}`);

    expect(options.map((option) => option.value)).toEqual([
      "NO_RESET",
      "DAY",
      "WEEK",
      "MONTH",
      "MONTH_ROLLING",
    ]);
    expect(options[0].label).toBe("ru:No automatic reset");
    expect(options[4].label).toBe("ru:Monthly from subscription start");
  });
});
