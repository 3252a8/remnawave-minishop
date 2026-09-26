export type LoginProvider = "discord" | "google" | "yandex";
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

export function loginProviderHelpTitle(provider: string, at: TranslateFn): string {
  if (provider === "google")
    return at("settings_login_google_help_title", {}, "Google OAuth application");
  if (provider === "yandex")
    return at("settings_login_yandex_help_title", {}, "Yandex OAuth application");
  if (provider === "discord")
    return at("settings_login_discord_help_title", {}, "Discord OAuth2 application");
  return at("settings_login_passkey_help_title", {}, "Passkey domain settings");
}

export function loginProviderHelpHint(provider: string, at: TranslateFn): string {
  if (provider === "google")
    return at(
      "settings_login_google_help_hint",
      {},
      "Create a Web OAuth client and add the exact callback URL below."
    );
  if (provider === "yandex")
    return at(
      "settings_login_yandex_help_hint",
      {},
      "Create an app for user authorization and add the callback as a Web service Redirect URI."
    );
  if (provider === "discord")
    return at(
      "settings_login_discord_help_hint",
      {},
      "Create a Discord application and add the exact OAuth2 redirect URL below."
    );
  return at(
    "settings_login_passkey_help_hint",
    {},
    "Use HTTPS; RP ID must be the application domain and origins must contain its full origin."
  );
}

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
