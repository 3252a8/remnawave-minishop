import {
  groupSectionFields,
  settingsFieldAnchorKey,
  type AdminSettingField,
  type AdminSettingsSection,
  type SettingsSubsection,
} from "./settingsSections";

export type SettingsSearchEntry = {
  key: string;
  sectionId: string;
  subsectionId: string | null;
  label: string;
  description: string;
  pathLabel: string;
  anchorKey: string;
  searchText: string;
};

type SettingsSearchTextResolvers = {
  sectionTitle: (id: string) => string;
  subsectionTitle: (group: SettingsSubsection) => string;
  fieldLabelText: (field: AdminSettingField) => string;
  fieldDescriptionText: (field: AdminSettingField) => string;
};

export function normalizeSettingsSearchText(value: unknown): string {
  return String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

export function buildSettingsSearchEntries(
  sections: AdminSettingsSection[],
  resolvers: SettingsSearchTextResolvers
): SettingsSearchEntry[] {
  const entries: SettingsSearchEntry[] = [];
  for (const section of sections) {
    const sectionTitle = resolvers.sectionTitle(section.id);
    for (const group of groupSectionFields(section)) {
      const subsectionId = group.label ? group.id : null;
      const subsectionTitle = group.label ? resolvers.subsectionTitle(group) : "";
      const pathLabel = [sectionTitle, subsectionTitle].filter(Boolean).join(" / ");
      for (const field of group.fields) {
        const label = resolvers.fieldLabelText(field);
        const description = resolvers.fieldDescriptionText(field);
        const searchText = normalizeSettingsSearchText(
          [label, description, field.key, pathLabel].filter(Boolean).join(" ")
        );
        entries.push({
          key: field.key,
          sectionId: section.id,
          subsectionId,
          label,
          description,
          pathLabel,
          anchorKey: settingsFieldAnchorKey(field.key),
          searchText,
        });
      }
    }
  }
  return entries;
}

function settingsSearchScore(
  entry: SettingsSearchEntry,
  queryText: string,
  terms: string[]
): number {
  if (!queryText || terms.some((term) => !entry.searchText.includes(term))) return 0;

  const label = normalizeSettingsSearchText(entry.label);
  const description = normalizeSettingsSearchText(entry.description);
  const key = normalizeSettingsSearchText(entry.key);
  const path = normalizeSettingsSearchText(entry.pathLabel);
  let score = 1;

  for (const term of terms) {
    if (label === term) score += 90;
    else if (label.startsWith(term)) score += 70;
    else if (label.includes(term)) score += 48;
    else if (description.includes(term)) score += 28;
    else if (key.includes(term)) score += 18;
    else if (path.includes(term)) score += 8;
  }

  if (label.includes(queryText)) score += 20;
  if (description.includes(queryText)) score += 10;
  return score;
}

export function searchSettingsEntries(
  entries: SettingsSearchEntry[],
  query: string,
  limit = 8
): SettingsSearchEntry[] {
  const queryText = normalizeSettingsSearchText(query);
  if (!queryText) return [];
  const terms = queryText.split(" ").filter(Boolean);
  return entries
    .map((entry, index) => ({
      entry,
      index,
      score: settingsSearchScore(entry, queryText, terms),
    }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, limit)
    .map((item) => item.entry);
}
