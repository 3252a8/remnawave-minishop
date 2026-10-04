import type { SettingField, SettingsDirtyEntry } from "$lib/admin/stores/settingsStore";

type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

export function settingsDirtyCountLabel(at: TranslateFn, count: number): string {
  return count ? at("settings_dirty_count", { count }, "Changes: {count}") : "";
}

export function settingsFieldsCountLabel(at: TranslateFn, count: number): string {
  return at("settings_fields_count", { count }, "{count} fields");
}

export function settingsOverriddenCountLabel(at: TranslateFn, count: number): string {
  return count ? at("settings_overridden_count", { count }, `${count} override`) : "";
}

export function settingsParamsCountLabel(at: TranslateFn, count: number): string {
  return at("settings_params_count", { count }, "{count} parameters");
}

export function settingsFieldValueSourceLabel(
  at: TranslateFn,
  field: Pick<SettingField, "value_source">,
  dirty?: SettingsDirtyEntry
): string {
  const source = dirty?.deleted
    ? "environment"
    : dirty
      ? "database_override"
      : String(field.value_source || "").trim();
  if (source === "database_override") {
    return at("settings_source_database_override", {}, "Source: database override");
  }
  if (source === "environment") {
    return at("settings_source_environment", {}, "Source: environment (.env)");
  }
  return "";
}
