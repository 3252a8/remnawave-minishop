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
  "uptime-kuma": new Set(["SERVER_STATUS_KUMA_URL", ...EMBEDDED_COMMON]),
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

export function isKumaStatusPageUrlValid(value: unknown): boolean {
  const raw = String(value ?? "").trim();
  if (!raw || raw !== String(value ?? "") || /\s/u.test(raw)) return false;
  // WHATWG URL resolves encoded dot segments before exposing `pathname`.
  if (/%2e(?:%2e)?(?:\/|$)/iu.test(raw)) return false;
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    if (!url.hostname || url.username || url.password || url.search || url.hash) return false;
    if (url.port === "0") return false;
    const hostname = url.hostname.replace(/^\[|\]$/gu, "").replace(/\.$/u, "");
    if (
      !hostname ||
      (!hostname.includes(":") &&
        !hostname.split(".").every((label) => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/iu.test(label)))
    ) {
      return false;
    }
    const rawSegments = url.pathname.split("/");
    if (rawSegments[0] === "") rawSegments.shift();
    if (rawSegments.at(-1) === "") rawSegments.pop();
    if (rawSegments.some((segment) => !segment)) return false;
    const segments = rawSegments.map((segment) => {
      const decoded = decodeURIComponent(segment);
      if (decoded === "." || decoded === ".." || /[/\\\x00-\x1f]/u.test(decoded)) {
        throw new TypeError("invalid path segment");
      }
      return encodeURIComponent(decoded);
    });
    return segments.length >= 2 && segments.at(-2) === "status" && Boolean(segments.at(-1));
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
