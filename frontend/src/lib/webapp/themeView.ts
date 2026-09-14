// Pure theme-derivation slice extracted from App.svelte (T2 decompose-then-type).
// Mirrors the former theme reactive blocks 1:1 so behaviour is identical; the
// shell binds the returned view and re-runs computeThemeView when its inputs change.
import {
  findThemeEntry,
  materializeThemeEntry,
  materializeThemesCatalog,
  resolveEffectiveThemeKey,
  themeCssHref,
  themeEntryToInlineStyle,
  themeRootClass,
} from "./themeStyle";
import { resolveThemePreference, THEME_PREFERENCE_AUTO } from "./themePreference.js";

type ThemeData = Record<string, unknown>;
type ThemeTokens = ThemeData & {
  color_scheme?: string;
  bg?: string;
};
type ThemeEntry =
  | (ThemeData & {
      key?: string;
      use_in_admin?: unknown;
      tokens?: ThemeTokens | null;
    })
  | null;

export interface ThemeView {
  themesCatalog: ThemeData;
  userThemeModeEnabled: boolean;
  resolvedThemeKey: string;
  effectiveThemeEntry: ThemeEntry;
  shellStyle: string;
  shellToneClass: string;
  shellThemeClass: string;
  shellThemeCssHref: string | null;
  toastTheme: "dark" | "light";
}

export interface ThemeViewInput {
  themePreviewDraft: ThemeData | null;
  themePreviewKey: string | null;
  data: ThemeData | null;
  user: ThemeData;
  screen: string;
  cfgThemesCatalog: ThemeData | null | undefined;
  primaryColor: string | undefined;
  themePreference?: string | null;
  systemColorScheme?: string | null;
  userThemeModeEnabled?: boolean | null;
}

export function computeThemeView({
  themePreviewDraft,
  themePreviewKey,
  data,
  user,
  screen,
  cfgThemesCatalog,
  primaryColor,
  themePreference = THEME_PREFERENCE_AUTO,
  systemColorScheme = "",
  userThemeModeEnabled = true,
}: ThemeViewInput): ThemeView {
  const rawThemesCatalog = themePreviewDraft?.catalog ||
    data?.themes_catalog ||
    cfgThemesCatalog || { default_theme: "dark", themes: [] };
  const themesCatalog = materializeThemesCatalog(rawThemesCatalog);
  const previewThemeAllowed = Boolean(themePreviewKey && (!data?.user || user?.is_admin));
  const previewThemeEntry: ThemeEntry = previewThemeAllowed
    ? findThemeEntry(themesCatalog, themePreviewKey)
    : null;
  const userTheme = userThemeModeEnabled
    ? resolveThemePreference({
        catalog: themesCatalog,
        preference: themePreference,
        systemScheme: systemColorScheme,
      })
    : { key: "", variant: "" };
  const userThemeSource = userTheme.key ? findThemeEntry(themesCatalog, userTheme.key) : null;
  const userThemeEntry: ThemeEntry = userThemeSource
    ? materializeThemeEntry(userThemeSource, userTheme.variant || null)
    : null;
  const resolvedThemeKey =
    previewThemeEntry?.key || userThemeEntry?.key || resolveEffectiveThemeKey(themesCatalog);
  const activeThemeEntry: ThemeEntry =
    previewThemeEntry || userThemeEntry || findThemeEntry(themesCatalog, resolvedThemeKey);
  const darkThemeEntry: ThemeEntry = findThemeEntry(themesCatalog, "dark");
  const adminFallbackTheme = darkThemeEntry
    ? resolveThemePreference({
        catalog: { ...themesCatalog, default_theme: darkThemeEntry.key },
        preference: themePreference,
        systemScheme: systemColorScheme,
      })
    : { key: "", variant: "" };
  const adminFallbackEntry = materializeThemeEntry(
    darkThemeEntry,
    adminFallbackTheme.variant || null
  );
  const effectiveThemeEntry: ThemeEntry =
    screen === "admin" && activeThemeEntry?.use_in_admin === false
      ? adminFallbackEntry || activeThemeEntry
      : activeThemeEntry;
  const tokens = (effectiveThemeEntry?.tokens as ThemeTokens | undefined) || {};
  const colorScheme = tokens.color_scheme === "light" ? "light" : "dark";
  return {
    themesCatalog,
    userThemeModeEnabled: Boolean(userThemeModeEnabled),
    resolvedThemeKey,
    effectiveThemeEntry,
    shellStyle: themeEntryToInlineStyle(effectiveThemeEntry, primaryColor),
    shellToneClass: colorScheme === "light" ? "theme-light" : "theme-dark",
    shellThemeClass: themeRootClass(effectiveThemeEntry),
    shellThemeCssHref: themeCssHref(effectiveThemeEntry),
    toastTheme: colorScheme,
  };
}
