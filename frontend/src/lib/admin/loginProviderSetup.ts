export type LoginProvider = "discord" | "google" | "yandex";

export function loginProviderOrigin(configuredUrl: string, fallbackOrigin: string): string {
  const fallback = String(fallbackOrigin || "").replace(/\/$/, "");
  const configured = String(configuredUrl || "").trim();
  if (!configured) return fallback;
  try {
    return new URL(configured).origin;
  } catch {
    return fallback;
  }
}

export function loginProviderCallbackUrl(
  provider: LoginProvider,
  configuredUrl: string,
  fallbackOrigin: string
): string {
  return `${loginProviderOrigin(configuredUrl, fallbackOrigin)}/auth/${provider}/callback`;
}
