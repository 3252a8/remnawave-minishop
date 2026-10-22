import { describe, expect, it } from "vitest";

import {
  buildSectionFieldSearchEntries,
  buildSettingsSearchEntries,
  searchSettingsEntries,
} from "./settingsSearch";
import type { AdminSettingField, AdminSettingsSection } from "./settingsSections";
import manifest from "../webapp/settingsManifest.generated.json";
import ru from "../../../../locales/ru.json";

const field = (key: string, extra: Partial<AdminSettingField> = {}): AdminSettingField =>
  ({
    key,
    label: key,
    type: "str",
    value: "",
    ...extra,
  }) as AdminSettingField;

describe("settingsSearch", () => {
  const sections: AdminSettingsSection[] = [
    {
      id: "general",
      title: "General",
      fields: [
        field("DEFAULT_LANGUAGE", {
          label: "Default language",
          description: "Language used for new users.",
        }),
        field("SUPPORT_LINK", {
          label: "Support link",
          description: "URL shown in the user profile.",
          subsection: "Common",
        }),
      ],
    } as AdminSettingsSection,
  ];

  const entries = buildSettingsSearchEntries(sections, {
    sectionTitle: (id) => (id === "general" ? "General" : id),
    subsectionTitle: (group) => (group.id === "Common" ? "Common settings" : group.id),
    fieldLabelText: (item) => item.label,
    fieldDescriptionText: (item) => item.description || "",
  });

  it("builds field-level search entries with display paths", () => {
    expect(entries).toMatchObject([
      {
        key: "DEFAULT_LANGUAGE",
        sectionId: "general",
        subsectionId: null,
        pathLabel: "General",
        anchorKey: "settings-field:DEFAULT_LANGUAGE",
      },
      {
        key: "SUPPORT_LINK",
        sectionId: "general",
        subsectionId: "Common",
        pathLabel: "General / Common settings",
      },
    ]);
  });

  it("finds settings by label and description", () => {
    expect(searchSettingsEntries(entries, "support").map((item) => item.key)).toEqual([
      "SUPPORT_LINK",
    ]);
    expect(searchSettingsEntries(entries, "new users").map((item) => item.key)).toEqual([
      "DEFAULT_LANGUAGE",
    ]);
  });

  it("indexes every manifest field once and routes specialized editors correctly", () => {
    const allEntries = buildSettingsSearchEntries(manifest as AdminSettingsSection[], {
      sectionTitle: (id) => id,
      subsectionTitle: (group) => group.id,
      fieldLabelText: (item) => ru[item.i18n_label_key as keyof typeof ru] || item.label,
      fieldDescriptionText: (item) => item.description || "",
    });
    const keys = manifest.flatMap((section) => section.fields.map((item) => item.key));
    expect(allEntries.map((entry) => entry.key)).toEqual(expect.arrayContaining(keys));
    expect(new Set(allEntries.map((entry) => entry.key)).size).toBe(keys.length);
    expect(searchSettingsEntries(allEntries, "капча")).toMatchObject([
      { key: "TRIAL_CAPTCHA_ENABLED", navigationSection: "tariffs" },
    ]);
    expect(searchSettingsEntries(allEntries, "TRIAL_CAPTCHA_ENABLED")[0]).toMatchObject({
      navigationSection: "tariffs",
    });
    expect(searchSettingsEntries(allEntries, "WEBAPP_COMPACT_HOME_ENABLED")[0]).toMatchObject({
      navigationSection: "appearance",
    });
    for (const [key, sectionId] of [
      ["REFERRAL_PROGRAM_ENABLED", "referral"],
      ["PARTNER_PROGRAM_ENABLED", "partner"],
    ]) {
      const entry = searchSettingsEntries(allEntries, key)[0];
      expect(entry.sectionId).toBe(sectionId);
      expect(entry.navigationSection).toBeUndefined();
    }
  });

  it("finds settings rendered outside the generic list by label or name", () => {
    const fieldsByKey = new Map([
      [
        "REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL",
        field("REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL", {
          label: "Add welcome bonus days to the trial",
          description: "Bonus days join the free trial.",
        }),
      ],
    ]);
    const programEntries = buildSectionFieldSearchEntries(
      ["REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL", "REFERRAL_NOT_IN_MANIFEST"],
      fieldsByKey,
      { sectionId: "referral", pathLabel: "Referral program" },
      {
        fieldLabelText: (item) => item.label,
        fieldDescriptionText: (item) => item.description || "",
      }
    );

    expect(programEntries).toHaveLength(1);
    expect(programEntries[0]).toMatchObject({
      key: "REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL",
      sectionId: "referral",
      subsectionId: null,
      label: "Add welcome bonus days to the trial",
      pathLabel: "Referral program",
      anchorKey: "settings-field:REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL",
    });
    for (const query of ["referral_welcome_bonus_adds_to_trial", "bonus days to the trial"]) {
      expect(
        searchSettingsEntries([...entries, ...programEntries], query).map((entry) => entry.key)
      ).toEqual(["REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL"]);
    }
  });
});
