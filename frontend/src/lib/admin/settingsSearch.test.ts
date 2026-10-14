import { describe, expect, it } from "vitest";

import {
  buildSectionFieldSearchEntries,
  buildSettingsSearchEntries,
  searchSettingsEntries,
} from "./settingsSearch";
import type { AdminSettingField, AdminSettingsSection } from "./settingsSections";

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
