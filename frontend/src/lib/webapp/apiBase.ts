export const DEFAULT_WEBAPP_API_BASE = "/api";

export function normalizeApiBase(
  value: string | null | undefined,
  fallback = DEFAULT_WEBAPP_API_BASE
): string {
  const raw = String(value || "").trim();
  const base = raw || fallback;
  return base.replace(/\/+$/, "") || fallback;
}

export function buildApiUrl(path: string, apiBase = DEFAULT_WEBAPP_API_BASE): string {
  const normalizedBase = normalizeApiBase(apiBase);
  let normalizedPath = `/${String(path || "").replace(/^\/+/, "")}`;
  if (normalizedBase.endsWith("/api") && normalizedPath === "/api") {
    normalizedPath = "";
  } else if (normalizedBase.endsWith("/api") && normalizedPath.startsWith("/api/")) {
    normalizedPath = normalizedPath.slice(4);
  }
  return `${normalizedBase}${normalizedPath}`;
}

type WebappRuntimeConfigWindow = Window & {
  __RW_WEBAPP_RUNTIME_CONFIG__?: {
    apiBaseUrl?: unknown;
  };
};

export function runtimeApiBase(): string {
  const runtimeConfig = (window as WebappRuntimeConfigWindow).__RW_WEBAPP_RUNTIME_CONFIG__;
  return normalizeApiBase(
    typeof runtimeConfig?.apiBaseUrl === "string" ? runtimeConfig.apiBaseUrl : "",
    import.meta.env.VITE_WEBAPP_API_BASE_URL || DEFAULT_WEBAPP_API_BASE
  );
}
