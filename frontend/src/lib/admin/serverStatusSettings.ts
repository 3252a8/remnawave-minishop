import type { AdminSettingField, AdminSettingsSection } from "./settingsSections";
import type { SettingsDirtyEntry } from "./stores/settingsStore";

export type ServerStatusProvider = "url" | "uptime-kuma" | "xray-checker";

const ALWAYS_VISIBLE = new Set([
  "SERVER_STATUS_ENABLED",
  "SERVER_STATUS_SHOW_ON_HOME",
  "SERVER_STATUS_PROVIDER",
]);
const EMBEDDED_COMMON = new Set([
  "SERVER_STATUS_CACHE_TTL_SECONDS",
  "SERVER_STATUS_STALE_TTL_SECONDS",
  "SERVER_STATUS_TIMEOUT_SECONDS",
]);
const PROVIDER_FIELDS: Record<ServerStatusProvider, Set<string>> = {
  url: new Set(["SERVER_STATUS_URL"]),
  "uptime-kuma": new Set(["SERVER_STATUS_KUMA_URL", "SERVER_STATUS_KUMA_SLUG", ...EMBEDDED_COMMON]),
  "xray-checker": new Set(["SERVER_STATUS_XRAY_CHECKER_URL", ...EMBEDDED_COMMON]),
};

export function effectiveServerStatusProvider(
  sections: AdminSettingsSection[],
  dirty: Record<string, SettingsDirtyEntry>
): ServerStatusProvider {
  const providerField = sections
    .flatMap((section) => section.fields)
    .find((field) => field.key === "SERVER_STATUS_PROVIDER");
  const dirtyProvider = dirty.SERVER_STATUS_PROVIDER;
  const raw = dirtyProvider && !dirtyProvider.deleted ? dirtyProvider.value : providerField?.value;
  return raw === "uptime-kuma" || raw === "xray-checker" ? raw : "url";
}

export function isKumaUrlValid(value: unknown): boolean {
  const valueText = String(value ?? "").trim();
  if (!valueText) return true;
  try {
    const url = new URL(valueText);
    return (url.protocol === "http:" || url.protocol === "https:") && Boolean(url.hostname);
  } catch {
    return false;
  }
}

export function serverStatusFieldVisible(
  field: Pick<AdminSettingField, "key" | "subsection">,
  provider: ServerStatusProvider
): boolean {
  if (field.subsection !== "server_status") return true;
  return ALWAYS_VISIBLE.has(field.key) || PROVIDER_FIELDS[provider].has(field.key);
}

export function filterServerStatusSettings(
  sections: AdminSettingsSection[],
  dirty: Record<string, SettingsDirtyEntry>
): AdminSettingsSection[] {
  const provider = effectiveServerStatusProvider(sections, dirty);
  return sections.map((section) => ({
    ...section,
    fields: section.fields.filter((field) => serverStatusFieldVisible(field, provider)),
  }));
}
