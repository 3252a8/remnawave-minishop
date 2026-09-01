export const RELEASE_DOCUMENTATION_URL = "https://minishop.minidoc.cc/";
export const DEV_DOCUMENTATION_URL = "https://dev.minishop.minidoc.cc/";

const STABLE_RELEASE_VERSION = /^v?\d+\.\d+\.\d+(?:\+g[0-9a-f]+)?$/i;

export function documentationBaseUrlForVersion(appVersion: unknown): string {
  const version = String(appVersion ?? "").trim();
  return STABLE_RELEASE_VERSION.test(version) ? RELEASE_DOCUMENTATION_URL : DEV_DOCUMENTATION_URL;
}
