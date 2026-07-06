import { describe, expect, it } from "vitest";

import {
  groupSectionFields,
  normalizeSettingsPath,
  resolveSettingsPath,
  semanticFieldGroups,
  settingsFieldGroupAnchorKey,
  settingsPathAnchorKey,
  settingsPathKey,
  settingsSubsectionAnchorKey,
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
        field("PLATEGA_CRYPTO_ENABLED", { subsection: "Platega" }),
      ],
    } as AdminSettingsSection;
    const [group] = groupSectionFields(section);

    expect(semanticFieldGroups(section, group).map((item) => item.id)).toEqual([
      "platega_common",
      "platega_sbp",
      "platega_crypto",
    ]);

    const resolved = resolveSettingsPath(["payments", "platega", "card"], [section]);

    expect(resolved?.anchorKey).toBe(settingsSubsectionAnchorKey("payments", "Platega"));
    expect(settingsPathAnchorKey(["payments", "platega", "card"], resolved)).toBe(
      settingsFieldGroupAnchorKey("payments", "Platega", "platega_sbp")
    );
  });
});
