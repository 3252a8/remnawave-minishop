import { describe, expect, it } from "vitest";

import {
  boolValue,
  csvList,
  inputValueForKey,
  providerDisplayName,
  providerSettingsPath,
  summarizeProviderSupport,
  valueForKey,
  type SettingsDirtyState,
} from "./tariffSettings";
import type { SettingField } from "./stores/settingsStore";
import type { ProviderCurrencySupport } from "./stores/tariffsStore";

const fields = new Map<string, SettingField>([
  ["ENABLED", { key: "ENABLED", label: "Enabled", value: "true" }],
  ["COUNT", { key: "COUNT", label: "Count", value: 3 }],
  ["CSV", { key: "CSV", label: "CSV", value: "a, b,,c" }],
]);

describe("tariffSettings", () => {
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

  it("derives provider display names and settings paths", () => {
    expect(providerDisplayName({ provider_key: "platega_sbp" } as ProviderCurrencySupport)).toBe(
      "Platega SBP/card"
    );
    expect(
      providerSettingsPath({ provider_key: "platega_crypto" } as ProviderCurrencySupport)
    ).toEqual(["payments", "platega", "crypto"]);
    expect(
      providerSettingsPath({ provider_key: "custom_gateway" } as ProviderCurrencySupport)
    ).toEqual(["payments", "custom-gateway"]);
  });
});
