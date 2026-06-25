export type AdminPersistedSettingsOptions = {
  deletes?: string[];
  updates?: Record<string, unknown>;
};

const FRONTEND_RELOAD_SETTING_KEYS = new Set([
  "WEBAPP_LOGO_URL",
  "WEBAPP_FAVICON_URL",
  "WEBAPP_FAVICON_USE_CUSTOM",
  "WEBAPP_LOGO_FAVICON_URL",
]);

export function adminPayloadHasFrontendReloadChange(options: AdminPersistedSettingsOptions = {}) {
  const keys = new Set([
    ...Object.keys(options.updates || {}),
    ...(Array.isArray(options.deletes) ? options.deletes : []),
  ]);
  return Array.from(FRONTEND_RELOAD_SETTING_KEYS).some((key) => keys.has(key));
}
