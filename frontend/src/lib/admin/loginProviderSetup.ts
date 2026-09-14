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

export function loginProviderOfficialUrl(provider: string): string {
  if (provider === "google")
    return "https://developers.google.com/identity/protocols/oauth2/web-server";
  if (provider === "yandex") return "https://yandex.com/dev/id/doc/en/register-auth";
  if (provider === "discord") return "https://docs.discord.com/developers/topics/oauth2";
  return "https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys";
}

export function loginProviderGuideUrl(provider: string, repositoryUrl: string): string {
  const section = provider === "yandex" ? "yandex-id" : provider;
  return `${repositoryUrl.replace(/\/+$/, "")}/features/login-methods/#${section}`;
}
