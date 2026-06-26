// Pure theme-derivation slice extracted from App.svelte (T2 decompose-then-type).
// Mirrors the former theme reactive blocks 1:1 so behaviour is identical; the
// shell binds the returned view and re-runs computeThemeView when its inputs change.
import {
  findThemeEntry,
  materializeThemesCatalog,
  resolveEffectiveThemeKey,
  themeCssHref,
  themeEntryToInlineStyle,
  themeRootClass,
} from "./themeStyle.js";

type ThemeData = Record<string, unknown>;
type ThemeTokens = ThemeData & {
  color_scheme?: string;
  bg?: string;
};
type ThemeEntry =
  | (ThemeData & {
      use_in_admin?: unknown;
      tokens?: ThemeTokens | null;
    })
  | null;

export interface ThemeView {
  themesCatalog: ThemeData;
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
}

export function computeThemeView({
  themePreviewDraft,
  themePreviewKey,
  data,
  user,
  screen,
  cfgThemesCatalog,
  primaryColor,
}: ThemeViewInput): ThemeView {
  const rawThemesCatalog = themePreviewDraft?.catalog ||
    data?.themes_catalog ||
    cfgThemesCatalog || { default_theme: "dark", themes: [] };
  const themesCatalog = materializeThemesCatalog(rawThemesCatalog);
  const previewThemeAllowed = Boolean(themePreviewKey && (!data?.user || user?.is_admin));
  const previewThemeEntry: ThemeEntry = previewThemeAllowed
    ? findThemeEntry(themesCatalog, themePreviewKey)
    : null;
  const resolvedThemeKey = previewThemeEntry?.key || resolveEffectiveThemeKey(themesCatalog);
  const activeThemeEntry: ThemeEntry = findThemeEntry(themesCatalog, resolvedThemeKey);
  const darkThemeEntry: ThemeEntry = findThemeEntry(themesCatalog, "dark");
  const effectiveThemeEntry: ThemeEntry =
    screen === "admin" && activeThemeEntry?.use_in_admin === false
      ? darkThemeEntry || activeThemeEntry
      : activeThemeEntry;
  const tokens = (effectiveThemeEntry?.tokens as ThemeTokens | undefined) || {};
  const colorScheme = tokens.color_scheme === "light" ? "light" : "dark";
  return {
    themesCatalog,
    resolvedThemeKey,
    effectiveThemeEntry,
    shellStyle: themeEntryToInlineStyle(effectiveThemeEntry, primaryColor),
    shellToneClass: colorScheme === "light" ? "theme-light" : "theme-dark",
    shellThemeClass: themeRootClass(effectiveThemeEntry),
    shellThemeCssHref: themeCssHref(effectiveThemeEntry),
    toastTheme: colorScheme,
  };
}
