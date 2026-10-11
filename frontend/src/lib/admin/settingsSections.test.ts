import { describe, expect, it } from "vitest";
import settingsManifest from "../webapp/settingsManifest.generated.json";

import {
  groupSectionFields,
  normalizeSettingsPath,
  resolveSettingsPath,
  semanticFieldGroups,
  settingsFieldGroupAnchorKey,
  settingsPathAnchorKey,
  settingsPathKey,
  type AdminSettingField,
  type AdminSettingsSection,
} from "./settingsSections";

const field = (key: string, extra: Partial<AdminSettingField> = {}): AdminSettingField =>
  ({
    key,
    label: key,
    type: "str",
    value: "",
    ...extra,
  }) as AdminSettingField;

describe("settingsSections", () => {
  it("keeps balance as a payment provider card with the shared money emoji", () => {
    const groups = groupSectionFields({
      id: "payments",
      title: "Payments",
      fields: [field("USER_BALANCE_RECURRING_ENABLED", { subsection: "balance" })],
    } as AdminSettingsSection);
    expect(groups[0].providerInfo).toMatchObject({
      id: "user_balance",
      logoFallback: "💸",
      logoUrl: "",
    });
  });
  it("normalizes deep settings paths into stable route keys", () => {
    expect(normalizeSettingsPath("/Payments/Platega/Crypto/ignored")).toEqual([
      "Payments",
      "Platega",
      "Crypto",
    ]);
    expect(settingsPathKey(["Payments & Billing", "Wata Crypto"])).toBe(
      "payments-and-billing/wata-crypto"
    );
  });

  it("keeps hosted payment methods inside one card per provider", () => {
    const payments = settingsManifest.find((section) => section.id === "payments");
    const section: AdminSettingsSection = {
      id: "payments",
      title: "Payments",
      fields: (payments?.fields || []).filter((item) =>
        /^(PAYMENT_)?(CRYPTOMUS|CISPAY)_/.test(item.key)
      ) as AdminSettingField[],
    };
    const groups = groupSectionFields(section);
    expect(groups.map((group) => group.id)).toEqual(["Cryptomus", "CisPay"]);
    for (const group of groups) {
      const keys = group.fields.map((item) => item.key);
      expect(new Set(keys).size).toBe(keys.length);
      expect(group.providerInfo?.logoUrl).toBe(`/provider-logos/${group.id.toLowerCase()}.png`);
      const methods = semanticFieldGroups(section, group);
      const provider = group.id.toLowerCase();
      expect(methods.map((method) => method.id)).toEqual([
        `${provider}_common`,
        `${provider}_one_off`,
        ...(provider === "cryptomus"
          ? ["cryptomus_subscription"]
          : ["cispay_subscription_card", "cispay_subscription_sbp"]),
      ]);
      for (const method of methods.filter((item) => item.id.includes("subscription"))) {
        expect(method.fields).toHaveLength(2);
        expect(method.fields.every((item) => item.key.includes("SUBSCRIPTION_"))).toBe(true);
      }
    }
    for (const [provider, method, legacy] of [
      ["cryptomus", "subscription", "cryptomus-recurring"],
      ["cispay", "subscription-card", "cispay-card-recurring"],
      ["cispay", "subscription-sbp", "cispay-sbp-recurring"],
    ]) {
      const target = resolveSettingsPath(["payments", provider, method], [section]);
      expect(target?.fieldGroup?.id).toBe(`${provider}_${method.replaceAll("-", "_")}`);
      expect(resolveSettingsPath(["payments", legacy], [section])?.anchorKey).toBe(
        target?.anchorKey
      );
    }
  });

  it("groups subsection fields and attaches webhook metadata", () => {
    const section: AdminSettingsSection = {
      id: "payments",
      title: "Payments",
      fields: [
        field("PLATEGA_SBP_ENABLED", { subsection: "Platega" }),
        field("PLATEGA_WEBHOOK_SECRET", {
          subsection: "Platega",
          webhook_path: "payments/platega/webhook",
          provider_id: "platega",
          provider_info_url: "https://platega.io/",
          provider_label: "Platega",
          provider_logo_url: "/provider-logos/platega.png",
        }),
      ],
    } as AdminSettingsSection;

    const [group] = groupSectionFields(section);

    expect(group.id).toBe("Platega");
    expect(group.webhook).toMatchObject({
      key: "platega:/payments/platega/webhook",
      path: "/payments/platega/webhook",
      url: "/payments/platega/webhook",
    });
    expect(group.providerInfo).toMatchObject({
      id: "platega",
      infoUrl: "https://platega.io/",
      label: "Platega",
      logoFallback: "PL",
      logoUrl: "/provider-logos/platega.png",
    });
  });

  it("derives semantic payment groups and resolves anchor aliases", () => {
    const section: AdminSettingsSection = {
      id: "payments",
      title: "Payments",
      fields: [
        field("PLATEGA_API_URL", { subsection: "Platega" }),
        field("PLATEGA_SBP_ENABLED", { subsection: "Platega" }),
        field("PLATEGA_CARD_ENABLED", { subsection: "Platega" }),
        field("PLATEGA_CRYPTO_ENABLED", { subsection: "Platega" }),
        field("PLATEGA_INTERNATIONAL_ENABLED", { subsection: "Platega" }),
        field("PLATEGA_ALL_METHODS_ENABLED", { subsection: "Platega" }),
      ],
    } as AdminSettingsSection;
    const [group] = groupSectionFields(section);

    expect(semanticFieldGroups(section, group).map((item) => item.id)).toEqual([
      "platega_common",
      "platega_sbp",
      "platega_card",
      "platega_crypto",
      "platega_international",
      "platega_all_methods",
    ]);

    const resolved = resolveSettingsPath(["payments", "platega", "card"], [section]);

    expect(resolved?.anchorKey).toBe(
      settingsFieldGroupAnchorKey("payments", "Platega", "platega_card")
    );
    expect(settingsPathAnchorKey(["payments", "platega", "card"], resolved)).toBe(
      settingsFieldGroupAnchorKey("payments", "Platega", "platega_card")
    );
    expect(settingsPathAnchorKey(["payments", "platega", "sbp"], resolved)).toBe(
      settingsFieldGroupAnchorKey("payments", "Platega", "platega_sbp")
    );
    expect(settingsPathAnchorKey(["payments", "platega", "international"], resolved)).toBe(
      settingsFieldGroupAnchorKey("payments", "Platega", "platega_international")
    );
    expect(settingsPathAnchorKey(["payments", "platega", "all-methods"], resolved)).toBe(
      settingsFieldGroupAnchorKey("payments", "Platega", "platega_all_methods")
    );
  });
});
