type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

export function settingsDirtyCountLabel(at: TranslateFn, count: number): string {
  return count ? at("settings_dirty_count", { count }, `${count} изм.`) : "";
}

export function settingsFieldsCountLabel(at: TranslateFn, count: number): string {
  return at("settings_fields_count", { count }, `${count} полей`);
}

export function settingsOverriddenCountLabel(at: TranslateFn, count: number): string {
  return count ? at("settings_overridden_count", { count }, `${count} override`) : "";
}

export function settingsParamsCountLabel(at: TranslateFn, count: number): string {
  return at("settings_params_count", { count }, `${count} параметров`);
}
