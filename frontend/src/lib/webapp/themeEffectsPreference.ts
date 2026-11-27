const STORAGE_PREFIX = "minishop-theme-effects-disabled:";
const FAILURE_PREFIX = "minishop-theme-effects-failed:";
const DISABLED_QUERY = "theme_effects_disabled";
const FAILURE_QUERY = "theme_effects_failed";

export type ThemeEffectsStatus = "enabled" | "disabled" | "failed" | "reduced-motion" | "safe-mode";
export type ThemeEffectsSettings = {
  status: ThemeEffectsStatus;
  setEnabled: (enabled: boolean) => void;
};

function readStored(storage: "localStorage" | "sessionStorage", key: string): string | null {
  try {
    return window[storage].getItem(key);
  } catch {
    return null;
  }
}

function setQuery(key: string, value: string | null): void {
  const url = new URL(location.href);
  if (value === null) url.searchParams.delete(key);
  else url.searchParams.set(key, value);
  history.replaceState(history.state, "", url);
}

export function themeEffectsStatus(
  key: string,
  digest: string,
  reducedMotion: boolean,
  userToggleEnabled: boolean
): ThemeEffectsStatus {
  const query = new URLSearchParams(location.search);
  if (query.get("theme_effects") === "off") return "safe-mode";
  if (reducedMotion) return "reduced-motion";
  if (
    userToggleEnabled &&
    (query.get(DISABLED_QUERY) === key || readStored("localStorage", STORAGE_PREFIX + key) === "1")
  ) {
    return "disabled";
  }
  if (
    query.get(FAILURE_QUERY) === `${key}.${digest}` ||
    readStored("sessionStorage", FAILURE_PREFIX + key) === digest
  ) {
    return "failed";
  }
  return "enabled";
}

export function setThemeEffectsDisabled(key: string, disabled: boolean): void {
  if (!disabled && new URLSearchParams(location.search).get("theme_effects") === "off") {
    setQuery("theme_effects", null);
  }
  try {
    if (disabled) localStorage.setItem(STORAGE_PREFIX + key, "1");
    else localStorage.removeItem(STORAGE_PREFIX + key);
  } catch {
    setQuery(DISABLED_QUERY, disabled ? key : null);
    return;
  }
  if (new URLSearchParams(location.search).get(DISABLED_QUERY) === key)
    setQuery(DISABLED_QUERY, null);
}

export function setThemeEffectsFailure(key: string, digest: string | null): void {
  try {
    if (digest === null) sessionStorage.removeItem(FAILURE_PREFIX + key);
    else sessionStorage.setItem(FAILURE_PREFIX + key, digest);
  } catch {
    setQuery(FAILURE_QUERY, digest === null ? null : `${key}.${digest}`);
    return;
  }
  if (new URLSearchParams(location.search).get(FAILURE_QUERY)?.startsWith(`${key}.`)) {
    setQuery(FAILURE_QUERY, null);
  }
}
