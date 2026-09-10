/** Maps JSON theme token keys to CSS custom properties used by the Mini App shell. */

type ThemeTokens = Record<string, unknown>;

export interface ThemeEntry extends Record<string, unknown> {
  key?: string;
  tokens?: ThemeTokens | null;
  variants?: Record<string, ThemeTokens | null> | null;
  active_variant?: string | null;
  css_file?: string | null;
  names?: Record<string, string> | null;
  assets_version?: unknown;
}

export interface ThemesCatalog extends Record<string, unknown> {
  default_theme?: string;
  themes?: ThemeEntry[];
}

interface ThemePreviewDraft extends Record<string, unknown> {
  preview_key?: unknown;
  catalog?: unknown;
  expires_at?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function asThemeEntries(value: unknown): ThemeEntry[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

const TOKEN_TO_CSS_VAR: Record<string, string> = {
  accent: "--accent",
  bg: "--bg",
  panel: "--panel",
  panel_2: "--panel-2",
  panel_3: "--panel-3",
  border: "--border",
  border_strong: "--border-strong",
  text: "--text",
  muted: "--muted",
  dim: "--dim",
  danger: "--danger",
  danger_text: "--danger-text",
  danger_soft: "--danger-soft",
  danger_border: "--danger-border",
  success: "--success",
  success_text: "--success-text",
  success_soft: "--success-soft",
  success_border: "--success-border",
  warning: "--warning",
  warning_text: "--warning-text",
  warning_soft: "--warning-soft",
  warning_border: "--warning-border",
  info: "--info",
  info_text: "--info-text",
  info_soft: "--info-soft",
  info_border: "--info-border",
  blue: "--blue",
  radius: "--radius",
  accent_contrast: "--accent-contrast",
  surface_sheen: "--surface-sheen",
  surface_sheen_soft: "--surface-sheen-soft",
  surface_hover: "--surface-hover",
  surface_muted: "--surface-muted",
  surface_subtle: "--surface-subtle",
  surface_subtle_border: "--surface-subtle-border",
  overlay_scrim: "--overlay-scrim",
  nav_bg: "--nav-bg",
  rail_bg: "--rail-bg",
  shadow_soft: "--shadow-soft",
  shadow_strong: "--shadow-strong",
  shadow_popover: "--shadow-popover",
  inset_highlight: "--inset-highlight",
  font_sans: "--font-sans",
  font_logo: "--font-logo",
  font_mono: "--font-mono",
  transparency: "--theme-transparency",
  home_logo_scale: "--home-logo-scale",
  home_logo_scale_desktop: "--home-logo-scale-desktop",
  home_logo_scale_mobile: "--home-logo-scale-mobile",
  admin_bg: "--admin-bg",
  admin_surface: "--admin-surface",
  admin_surface_2: "--admin-surface-2",
  admin_elev: "--admin-elev",
  admin_border: "--admin-border",
  admin_border_strong: "--admin-border-strong",
  admin_text: "--admin-text",
  admin_muted: "--admin-muted",
  admin_dim: "--admin-dim",
  admin_chart_stroke: "--admin-chart-stroke",
  admin_chart_fill: "--admin-chart-fill",
};

const ADMIN_TOKEN_FALLBACKS: Record<string, string> = {
  admin_bg: "bg",
  admin_surface: "panel",
  admin_surface_2: "panel_2",
  admin_elev: "panel_3",
  admin_border: "border",
  admin_border_strong: "border_strong",
  admin_text: "text",
  admin_muted: "muted",
  admin_dim: "dim",
};

const LOGO_SCALE_TOKEN_KEYS = new Set([
  "home_logo_scale",
  "home_logo_scale_desktop",
  "home_logo_scale_mobile",
]);
const PERCENTAGE_TOKEN_KEYS = new Set(["transparency"]);
const THEME_VARIANTS = new Set(["dark", "light"]);
const GOOGLE_FONT_LINK_ID = "webapp-theme-google-fonts";
const SYSTEM_FONT_FAMILIES = new Set([
  "-apple-system",
  "blinkmacsystemfont",
  "system-ui",
  "ui-sans-serif",
  "ui-monospace",
  "sfmono-regular",
  "segoe ui",
  "arial",
  "helvetica",
  "sans-serif",
  "serif",
  "monospace",
  "consolas",
  "menlo",
  "monaco",
  "var(--font-mono)",
]);
const GOOGLE_FONT_SINGLE_WEIGHT_FAMILIES = new Set(["press start 2p"]);

export const THEME_PREVIEW_STORAGE_KEY = "rw_webapp_theme_preview_v1";
export const THEME_PREVIEW_TTL_MS = 10 * 60 * 1000;

export function themeTokensToInlineStyle(
  tokens: ThemeTokens | null | undefined,
  primaryFallback: string | undefined = "#00fe7a",
  options: { fallbackAccent?: boolean } = {}
): string {
  const t = asRecord(tokens);
  const parts: string[] = [];
  const useFallbackAccent = options.fallbackAccent !== false;
  const accent = t.accent || (useFallbackAccent ? primaryFallback || "#00fe7a" : "");
  if (accent) parts.push(`--accent:${accent}`);
  for (const [key, cssVar] of Object.entries(TOKEN_TO_CSS_VAR)) {
    if (key === "accent") continue;
    let value = t[key];
    if ((value === undefined || value === null || value === "") && ADMIN_TOKEN_FALLBACKS[key]) {
      value = t[ADMIN_TOKEN_FALLBACKS[key]];
    }
    if (value === undefined || value === null || value === "") continue;
    if (LOGO_SCALE_TOKEN_KEYS.has(key)) {
      const scale = Number(value);
      if (!Number.isFinite(scale) || scale <= 0) continue;
      parts.push(`${cssVar}:${scale / 100}`);
      continue;
    }
    if (PERCENTAGE_TOKEN_KEYS.has(key)) {
      const percentage = Number(value);
      if (!Number.isFinite(percentage)) continue;
      parts.push(`${cssVar}:${Math.min(100, Math.max(0, percentage)) / 100}`);
      continue;
    }
    parts.push(`${cssVar}:${String(value)}`);
  }
  for (const [key, value] of Object.entries(t)) {
    if (key.startsWith("--") && value !== undefined && value !== null && value !== "") {
      parts.push(`${key}:${String(value)}`);
    }
  }
  return parts.join(";");
}

export function findThemeEntry(
  themesCatalog: ThemesCatalog | null | undefined,
  key: unknown
): ThemeEntry | null {
  const themes = asThemeEntries(themesCatalog?.themes);
  const normalizedKey = String(key || "");
  return themes.find((entry) => entry && entry.key === normalizedKey) || null;
}

function normalizeThemeVariant(variant: unknown): string {
  const value = String(variant || "")
    .trim()
    .toLowerCase();
  return THEME_VARIANTS.has(value) ? value : "";
}

export function resolveThemeEntryTokens(
  theme: ThemeEntry | null | undefined,
  variant: string | null = null
): ThemeTokens {
  const base = asRecord(theme?.tokens);
  const activeVariant =
    normalizeThemeVariant(variant) ||
    normalizeThemeVariant(theme?.active_variant) ||
    normalizeThemeVariant(base.color_scheme);
  const variants = asRecord(theme?.variants);
  const variantTokens =
    activeVariant && isRecord(variants[activeVariant]) ? variants[activeVariant] : {};
  return { ...base, ...variantTokens };
}

export function materializeThemeEntry(
  theme: unknown,
  variant: string | null = null
): ThemeEntry | null {
  if (!isRecord(theme)) return null;
  const tokens = resolveThemeEntryTokens(theme, variant);
  const activeVariant =
    normalizeThemeVariant(variant) ||
    normalizeThemeVariant(theme.active_variant) ||
    normalizeThemeVariant(tokens.color_scheme) ||
    "";
  return {
    ...theme,
    active_variant: String(activeVariant || theme.active_variant || ""),
    tokens,
  };
}

export function materializeThemesCatalog(catalog: unknown): ThemesCatalog {
  const source = asRecord(catalog);
  return {
    ...source,
    default_theme: String(source.default_theme || "dark"),
    themes: asThemeEntries(source.themes)
      .map((theme) => materializeThemeEntry(theme))
      .filter((theme): theme is ThemeEntry => Boolean(theme)),
  };
}

export function resolveEffectiveThemeKey(themesCatalog: ThemesCatalog | null | undefined): string {
  const themes = asThemeEntries(themesCatalog?.themes);
  const byKey = (k: string) => themes.find((entry) => entry.key === k);
  const def = themesCatalog?.default_theme || themes[0]?.key || "dark";
  return byKey(def) ? def : themes[0]?.key || "dark";
}

export function themePresetClass(tokens: ThemeTokens | null | undefined): string {
  const preset = String(tokens?.style_preset || "")
    .trim()
    .toLowerCase();
  if (!preset || preset === "none") return "";
  if (preset === "win95" || preset === "windows95") return "theme-preset-win95";
  return "";
}

export function themeVariantClass(theme: ThemeEntry | null | undefined): string {
  const variant = String(theme?.active_variant || theme?.tokens?.color_scheme || "")
    .trim()
    .toLowerCase();
  return variant === "light" || variant === "dark" ? `theme-variant-${variant}` : "";
}

export function themeKeyClass(key: unknown): string {
  const safe = String(key || "")
    .trim()
    .toLowerCase()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return safe ? `theme-key-${safe}` : "";
}

export function themeCssClass(cssFile: unknown): string {
  const filename = String(cssFile || "")
    .replace(/\\/g, "/")
    .split("/")
    .filter(Boolean)
    .pop();
  const slug = String(filename || "")
    .replace(/\.css$/i, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug ? `theme-css-${slug}` : "";
}

export function themeRootClass(theme: ThemeEntry | null | undefined): string {
  return [
    themeKeyClass(theme?.key),
    themeVariantClass(theme),
    themeCssClass(theme?.css_file),
    themePresetClass(theme?.tokens),
  ]
    .filter(Boolean)
    .join(" ");
}

export function themeEntryToInlineStyle(
  theme: ThemeEntry | null | undefined,
  primaryFallback: string | undefined = "#00fe7a"
): string {
  const materialized = materializeThemeEntry(theme);
  return themeTokensToInlineStyle(materialized?.tokens, primaryFallback);
}

function stripQuotes(value: unknown): string {
  return String(value || "")
    .trim()
    .replace(/^["']|["']$/g, "")
    .trim();
}

export function firstFontFamily(fontStack: unknown): string {
  const first = String(fontStack || "")
    .split(",")
    .map(stripQuotes)
    .find(Boolean);
  return first || "";
}

function shouldLoadGoogleFont(family: unknown): boolean {
  const normalized = String(family || "")
    .trim()
    .toLowerCase();
  return Boolean(
    normalized &&
    !normalized.startsWith("var(") &&
    !normalized.startsWith("ui-") &&
    !SYSTEM_FONT_FAMILIES.has(normalized)
  );
}

export function googleFontFamiliesFromTokens(tokens: ThemeTokens | null | undefined): string[] {
  const families = [
    firstFontFamily(tokens?.font_sans),
    firstFontFamily(tokens?.font_logo),
    firstFontFamily(tokens?.font_mono),
  ].filter(shouldLoadGoogleFont);
  return Array.from(new Set(families));
}

export function googleFontsHrefForTheme(theme: ThemeEntry | null | undefined): string {
  const materialized = materializeThemeEntry(theme);
  const families = googleFontFamiliesFromTokens(materialized?.tokens);
  if (!families.length) return "";
  const query = families
    .map((family) => {
      const encodedFamily = encodeURIComponent(family).replace(/%20/g, "+");
      const normalizedFamily = String(family || "")
        .trim()
        .toLowerCase();
      if (GOOGLE_FONT_SINGLE_WEIGHT_FAMILIES.has(normalizedFamily)) {
        return `family=${encodedFamily}`;
      }
      return `family=${encodedFamily}:wght@400;500;600;700;800`;
    })
    .join("&");
  return `https://fonts.googleapis.com/css2?${query}&display=swap`;
}

export function syncThemeGoogleFonts(theme: ThemeEntry | null | undefined): void {
  if (typeof document === "undefined") return;
  const href = googleFontsHrefForTheme(theme);
  let link = document.getElementById(GOOGLE_FONT_LINK_ID);
  if (!href) {
    link?.remove();
    return;
  }
  if (!link) {
    link = document.createElement("link");
    link.id = GOOGLE_FONT_LINK_ID;
    link.setAttribute("rel", "stylesheet");
    document.head.appendChild(link);
  }
  if (link.getAttribute("href") !== href) {
    link.setAttribute("href", href);
  }
}

export function readThemePreviewDraft(previewKey = ""): ThemePreviewDraft | null {
  if (typeof window === "undefined" || !previewKey) return null;
  try {
    const requestedKey = String(previewKey || "").trim();
    const raw = window.localStorage?.getItem(THEME_PREVIEW_STORAGE_KEY);
    if (!raw) return null;
    const parsed = asRecord(JSON.parse(raw));
    if (!Object.keys(parsed).length) return null;
    const storedKey = String(parsed.preview_key || "").trim();
    if (storedKey && requestedKey && storedKey !== requestedKey) return null;
    if (Number(parsed.expires_at || 0) < Date.now()) {
      window.localStorage?.removeItem(THEME_PREVIEW_STORAGE_KEY);
      return null;
    }
    if (!parsed.catalog || typeof parsed.catalog !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeThemePreviewDraft(catalog: unknown, previewKey = ""): void {
  if (typeof window === "undefined" || !catalog) return;
  try {
    window.localStorage?.setItem(
      THEME_PREVIEW_STORAGE_KEY,
      JSON.stringify({
        preview_key: previewKey || "",
        catalog,
        expires_at: Date.now() + THEME_PREVIEW_TTL_MS,
      })
    );
  } catch {
    // Preview is best-effort; opening the persisted theme should still work.
  }
}

function encodeThemeCssPath(path: unknown): string {
  return String(path || "")
    .replace(/\\/g, "/")
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
}

function themeAssetsVersion(theme: ThemeEntry | null | undefined): string {
  const version = Number(theme?.assets_version || 0);
  return Number.isFinite(version) && version > 0 ? String(Math.floor(version)) : "";
}

export function themeCssHref(theme: ThemeEntry | null | undefined): string {
  const cssFile = String(theme?.css_file || "").trim();
  if (!cssFile) return "";
  if (/^(?:https?:)?\/\//i.test(cssFile) || cssFile.startsWith("data:")) return "";
  const version = themeAssetsVersion(theme);
  if (cssFile.startsWith("/")) {
    if (!version) return cssFile;
    return `${cssFile}${cssFile.includes("?") ? "&" : "?"}v=${encodeURIComponent(version)}`;
  }
  const normalizedCssFile = cssFile.replace(/\\/g, "/").split("/").filter(Boolean).join("/");
  const key = String(theme?.key || "")
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const themedPath =
    key && normalizedCssFile.split("/")[0] !== key
      ? `${key}/${normalizedCssFile}`
      : normalizedCssFile;
  const encoded = encodeThemeCssPath(themedPath);
  if (!encoded) return "";
  const href = `/webapp-theme-css/${encoded}`;
  return version ? `${href}?v=${encodeURIComponent(version)}` : href;
}

export function localizedThemeName(theme: ThemeEntry | null | undefined, lang = "en"): string {
  const names = theme?.names || {};
  const key = String(lang || "")
    .trim()
    .toLowerCase();
  const base = key.split("-")[0];
  return names[key] || names[base] || names.en || theme?.key || "";
}
