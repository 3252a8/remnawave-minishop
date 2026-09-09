// Client-only preference for the light/dark mode of the current theme.
// The administrator still owns the theme family through catalog.default_theme;
// users can only choose how that same family is rendered.

import {
  findThemeEntry,
  resolveEffectiveThemeKey,
  type ThemeEntry,
  type ThemesCatalog,
} from "./themeStyle";

export const THEME_PREFERENCE_AUTO = "auto";
export const THEME_PREFERENCE_LIGHT = "light";
export const THEME_PREFERENCE_DARK = "dark";
// A new key deliberately ignores values from the abandoned theme-family picker.
export const THEME_PREFERENCE_STORAGE_KEY = "rw_webapp_theme_mode_v1";

type ColorScheme = typeof THEME_PREFERENCE_LIGHT | typeof THEME_PREFERENCE_DARK;
export type ThemePreference = typeof THEME_PREFERENCE_AUTO | ColorScheme;

export type ResolvedThemePreference = {
  key: string;
  variant: ColorScheme | "";
};

export type ThemeOption = {
  value: ThemePreference;
  label: string;
};

function clientColorScheme(value: unknown): ColorScheme | "" {
  const raw = String(value || "")
    .trim()
    .toLowerCase();
  return raw === THEME_PREFERENCE_LIGHT || raw === THEME_PREFERENCE_DARK ? raw : "";
}

/** Only the three supported mode values may ever reach storage or the UI. */
export function normalizeThemePreference(value: unknown): ThemePreference {
  const raw = String(value || "")
    .trim()
    .toLowerCase();
  if (raw === THEME_PREFERENCE_LIGHT || raw === THEME_PREFERENCE_DARK) return raw;
  return THEME_PREFERENCE_AUTO;
}

function themeHasVariant(theme: ThemeEntry | null | undefined, scheme: ColorScheme): boolean {
  const variant = theme?.variants?.[scheme];
  return Boolean(variant && typeof variant === "object" && !Array.isArray(variant));
}

function currentTheme(catalog: ThemesCatalog | null | undefined): ThemeEntry | null {
  return findThemeEntry(catalog, resolveEffectiveThemeKey(catalog));
}

/** The control is meaningful only when the current theme implements both modes. */
export function themeSwitcherAvailable(catalog: ThemesCatalog | null | undefined): boolean {
  const theme = currentTheme(catalog);
  return (
    themeHasVariant(theme, THEME_PREFERENCE_LIGHT) && themeHasVariant(theme, THEME_PREFERENCE_DARK)
  );
}

export function themeOptions(
  autoLabel: string,
  lightLabel: string,
  darkLabel: string
): ThemeOption[] {
  return [
    { value: THEME_PREFERENCE_AUTO, label: autoLabel },
    { value: THEME_PREFERENCE_LIGHT, label: lightLabel },
    { value: THEME_PREFERENCE_DARK, label: darkLabel },
  ];
}

export function activeThemeOption(preference: unknown): ThemePreference {
  return normalizeThemePreference(preference);
}

/**
 * Resolve a mode within catalog.default_theme. The key never comes from user
 * input, so changing Auto/Light/Dark cannot switch to Windows 95, ASCII, or any
 * other catalog theme. Auto follows Telegram/browser when a signal is present;
 * without one, the administrator's active_variant stays untouched.
 */
export function resolveThemePreference({
  catalog,
  preference,
  systemScheme,
}: {
  catalog: ThemesCatalog | null | undefined;
  preference: unknown;
  systemScheme: unknown;
}): ResolvedThemePreference {
  if (!themeSwitcherAvailable(catalog)) return { key: "", variant: "" };

  const mode = normalizeThemePreference(preference);
  const scheme = mode === THEME_PREFERENCE_AUTO ? clientColorScheme(systemScheme) : mode;
  if (!scheme) return { key: "", variant: "" };

  const theme = currentTheme(catalog);
  if (!theme?.key || !themeHasVariant(theme, scheme)) return { key: "", variant: "" };
  return { key: String(theme.key), variant: scheme };
}

/** Compatibility helper for consumers that only need the current family key. */
export function resolveThemePreferenceKey(input: {
  catalog: ThemesCatalog | null | undefined;
  preference: unknown;
  systemScheme: unknown;
}): string {
  return resolveThemePreference(input).key;
}
