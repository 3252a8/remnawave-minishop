// Pure theme-derivation slice extracted from App.svelte (T2 decompose-then-type).
// Mirrors the former $: theme reactive blocks 1:1 so behaviour is identical; the
// shell binds the returned view and re-runs computeThemeView when its inputs change.
import {
  findThemeEntry,
  materializeThemesCatalog,
  resolveEffectiveThemeKey,
  themeCssHref,
  themeEntryToInlineStyle,
  themeRootClass,
} from "./themeStyle.js";

type AnyRecord = Record<string, any>;
type ThemeEntry = AnyRecord | null;

export interface ThemeView {
  themesCatalog: AnyRecord;
  resolvedThemeKey: string;
  effectiveThemeEntry: ThemeEntry;
  shellStyle: string;
  shellToneClass: string;
  shellThemeClass: string;
  shellThemeCssHref: string | null;
}

export interface ThemeViewInput {
  themePreviewDraft: AnyRecord | null;
  themePreviewKey: string | null;
  data: AnyRecord | null;
  user: AnyRecord;
  screen: string;
  cfgThemesCatalog: AnyRecord | null | undefined;
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
  return {
    themesCatalog,
    resolvedThemeKey,
    effectiveThemeEntry,
    shellStyle: themeEntryToInlineStyle(effectiveThemeEntry, primaryColor),
    shellToneClass:
      effectiveThemeEntry?.tokens?.color_scheme === "light" ? "theme-light" : "theme-dark",
    shellThemeClass: themeRootClass(effectiveThemeEntry),
    shellThemeCssHref: themeCssHref(effectiveThemeEntry),
  };
}
