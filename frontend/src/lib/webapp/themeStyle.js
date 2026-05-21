/** Maps JSON theme token keys to CSS custom properties used by the Mini App shell. */

const TOKEN_TO_CSS_VAR = {
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
  font_sans: "--font-sans",
  font_logo: "--font-logo",
  font_mono: "--font-mono",
  home_logo_scale: "--home-logo-scale",
  admin_bg: "--admin-bg",
  admin_surface: "--admin-surface",
  admin_surface_2: "--admin-surface-2",
  admin_elev: "--admin-elev",
  admin_border: "--admin-border",
  admin_border_strong: "--admin-border-strong",
  admin_text: "--admin-text",
  admin_muted: "--admin-muted",
  admin_dim: "--admin-dim",
};

export function themeTokensToInlineStyle(tokens, primaryFallback = "#00fe7a", options = {}) {
  const t = tokens && typeof tokens === "object" ? tokens : {};
  const parts = [];
  const useFallbackAccent = options.fallbackAccent !== false;
  const accent = t.accent || (useFallbackAccent ? primaryFallback || "#00fe7a" : "");
  if (accent) parts.push(`--accent:${accent}`);
  for (const [key, cssVar] of Object.entries(TOKEN_TO_CSS_VAR)) {
    if (key === "accent") continue;
    const value = t[key];
    if (value === undefined || value === null || value === "") continue;
    if (key === "home_logo_scale") {
      const scale = Number(value);
      if (!Number.isFinite(scale) || scale <= 0) continue;
      parts.push(`${cssVar}:${scale / 100}`);
      continue;
    }
    parts.push(`${cssVar}:${String(value)}`);
  }
  return parts.join(";");
}

export function findThemeEntry(themesCatalog, key) {
  const themes = themesCatalog?.themes || [];
  return themes.find((entry) => entry && entry.key === key) || null;
}

export function resolveEffectiveThemeKey(themesCatalog) {
  const themes = themesCatalog?.themes || [];
  const byKey = (k) => themes.find((entry) => entry.key === k);
  const def = themesCatalog?.default_theme || themes[0]?.key || "dark";
  return byKey(def) ? def : themes[0]?.key || "dark";
}

export function themePresetClass(tokens) {
  const preset = String(tokens?.style_preset || "")
    .trim()
    .toLowerCase();
  if (!preset || preset === "none") return "";
  if (preset === "win95" || preset === "windows95") return "theme-preset-win95";
  return "";
}

export function themeKeyClass(key) {
  const safe = String(key || "")
    .trim()
    .toLowerCase()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return safe ? `theme-key-${safe}` : "";
}

export function themeCssClass(cssFile) {
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

export function themeRootClass(theme) {
  return [
    themeKeyClass(theme?.key),
    themeCssClass(theme?.css_file),
    themePresetClass(theme?.tokens),
  ]
    .filter(Boolean)
    .join(" ");
}

export function themeEntryToInlineStyle(theme, primaryFallback = "#00fe7a") {
  return themeTokensToInlineStyle(theme?.tokens, primaryFallback, {
    fallbackAccent: !theme?.css_file,
  });
}

function encodeThemeCssPath(path) {
  return String(path || "")
    .replace(/\\/g, "/")
    .split("/")
    .filter(Boolean)
    .map(encodeURIComponent)
    .join("/");
}

function themeAssetsVersion(theme) {
  const version = Number(theme?.assets_version || 0);
  return Number.isFinite(version) && version > 0 ? String(Math.floor(version)) : "";
}

export function themeCssHref(theme) {
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

export function localizedThemeName(theme, lang = "en") {
  const names = theme?.names || {};
  const key = String(lang || "")
    .trim()
    .toLowerCase();
  const base = key.split("-")[0];
  return names[key] || names[base] || names.en || theme?.key || "";
}
