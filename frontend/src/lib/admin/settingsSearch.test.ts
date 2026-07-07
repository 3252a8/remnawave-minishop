import { describe, expect, it } from "vitest";

import { buildSettingsSearchEntries, searchSettingsEntries } from "./settingsSearch";
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
});
