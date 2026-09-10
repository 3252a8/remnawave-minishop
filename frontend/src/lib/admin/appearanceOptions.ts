export type TokenMap = Record<string, unknown>;
export type ThemeVariant = "dark" | "light";
export type FontOption = { value: string; label: string };
export type ThemeEntry = Record<string, unknown> & {
  active_variant?: string | null;
  css_file?: string;
  css_variables?: Record<string, string> | null;
  css_variables_by_variant?: Record<string, Record<string, string>> | null;
  default?: boolean;
  hidden?: boolean;
  key: string;
  tokens?: TokenMap | null;
  use_in_admin?: boolean;
  variant_alias_for?: string | null;
  variants?: Record<string, TokenMap | null> | null;
};
export type ThemeCatalog = { default_theme: string; themes: ThemeEntry[] };
export type ThemePreset = { id: string; label: string; swatch: string; tokens: TokenMap };
export type LogoMode = "desktop" | "mobile";
export type BrandInfo = Record<string, unknown> & { logoUrl?: string };
export type AppearanceThemesState = {
  themesCatalog: ThemeCatalog;
  savedThemesCatalog: ThemeCatalog;
  themesLoading: boolean;
  themesDir: string;
  themesSaving: boolean;
  themesDirty: boolean;
};

type RgbColor = { red: number; green: number; blue: number; alpha: number };

const HEX_COLOR = /^#([\da-f]{3}|[\da-f]{4}|[\da-f]{6}|[\da-f]{8})$/i;
const NUMBER_PART = "[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)";
const RGB_COLOR = new RegExp(
  `^rgba?\\(\\s*(${NUMBER_PART}%?)\\s*(?:,\\s*|\\s+)(${NUMBER_PART}%?)\\s*(?:,\\s*|\\s+)(${NUMBER_PART}%?)(?:\\s*(?:/|,)\\s*(${NUMBER_PART}%?))?\\s*\\)$`,
  "i"
);
const HSL_COLOR = new RegExp(
  `^hsla?\\(\\s*(${NUMBER_PART})(deg|grad|rad|turn)?\\s*(?:,\\s*|\\s+)(${NUMBER_PART})%\\s*(?:,\\s*|\\s+)(${NUMBER_PART})%(?:\\s*(?:/|,)\\s*(${NUMBER_PART}%?))?\\s*\\)$`,
  "i"
);

function clampColorPart(value: number): number {
  return Math.min(255, Math.max(0, Math.round(value)));
}

function parseAlpha(value: string | undefined): number {
  const alpha = value?.endsWith("%")
    ? Number.parseFloat(value) / 100
    : Number.parseFloat(value ?? "1");
  return Math.min(1, Math.max(0, alpha));
}

function parseRgbPart(value: string): number {
  return value.endsWith("%")
    ? clampColorPart((Number.parseFloat(value) / 100) * 255)
    : clampColorPart(Number.parseFloat(value));
}

function hueDegrees(value: number, unit: string | undefined): number {
  if (unit?.toLowerCase() === "grad") return value * 0.9;
  if (unit?.toLowerCase() === "rad") return (value * 180) / Math.PI;
  if (unit?.toLowerCase() === "turn") return value * 360;
  return value;
}

function hslToRgb(hue: number, saturation: number, lightness: number, alpha: number): RgbColor {
  const normalizedHue = (((hue % 360) + 360) % 360) / 360;
  const normalizedSaturation = Math.min(1, Math.max(0, saturation));
  const normalizedLightness = Math.min(1, Math.max(0, lightness));
  const chroma = (1 - Math.abs(2 * normalizedLightness - 1)) * normalizedSaturation;
  const segment = normalizedHue * 6;
  const secondary = chroma * (1 - Math.abs((segment % 2) - 1));
  const [red, green, blue] =
    segment < 1
      ? [chroma, secondary, 0]
      : segment < 2
        ? [secondary, chroma, 0]
        : segment < 3
          ? [0, chroma, secondary]
          : segment < 4
            ? [0, secondary, chroma]
            : segment < 5
              ? [secondary, 0, chroma]
              : [chroma, 0, secondary];
  const match = normalizedLightness - chroma / 2;
  return {
    red: clampColorPart((red + match) * 255),
    green: clampColorPart((green + match) * 255),
    blue: clampColorPart((blue + match) * 255),
    alpha,
  };
}

function parseColor(value: string): RgbColor | null {
  const text = value.trim();
  if (text === "transparent") return { red: 0, green: 0, blue: 0, alpha: 0 };
  const hexMatch = text.match(HEX_COLOR);
  if (hexMatch) {
    const hex = hexMatch[1].length <= 4
      ? hexMatch[1].split("").map((part) => part + part).join("")
      : hexMatch[1];
    return {
      red: Number.parseInt(hex.slice(0, 2), 16),
      green: Number.parseInt(hex.slice(2, 4), 16),
      blue: Number.parseInt(hex.slice(4, 6), 16),
      alpha: hex.length === 8 ? Number.parseInt(hex.slice(6, 8), 16) / 255 : 1,
    };
  }
  const rgbMatch = text.match(RGB_COLOR);
  if (rgbMatch) {
    const alpha = parseAlpha(rgbMatch[4]);
    if (![rgbMatch[1], rgbMatch[2], rgbMatch[3], alpha].every((part) => Number.isFinite(Number.parseFloat(String(part))))) {
      return null;
    }
    return {
      red: parseRgbPart(rgbMatch[1]),
      green: parseRgbPart(rgbMatch[2]),
      blue: parseRgbPart(rgbMatch[3]),
      alpha,
    };
  }
  const hslMatch = text.match(HSL_COLOR);
  if (!hslMatch) return null;
  const values = [hslMatch[1], hslMatch[3], hslMatch[4], hslMatch[5] ?? "1"].map(Number.parseFloat);
  if (!values.every(Number.isFinite)) return null;
  return hslToRgb(
    hueDegrees(values[0], hslMatch[2]),
    values[1] / 100,
    values[2] / 100,
    parseAlpha(hslMatch[5])
  );
}

function toHex(color: RgbColor): string {
  const component = (value: number): string => value.toString(16).padStart(2, "0");
  return `#${component(color.red)}${component(color.green)}${component(color.blue)}`;
}

function splitTopLevel(value: string): string[] {
  const parts: string[] = [];
  let start = 0;
  let depth = 0;
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === "(") depth += 1;
    if (value[index] === ")") depth -= 1;
    if (value[index] === "," && depth === 0) {
      parts.push(value.slice(start, index).trim());
      start = index + 1;
    }
  }
  parts.push(value.slice(start).trim());
  return parts;
}

function resolveVariables(
  value: string,
  variables: Record<string, unknown>,
  resolving: Set<string>
): string | null {
  const start = value.indexOf("var(");
  if (start < 0) return value;
  let depth = 0;
  for (let index = start + 4; index < value.length; index += 1) {
    if (value[index] === "(") depth += 1;
    if (value[index] === ")") {
      if (depth === 0) {
        const [name, ...fallbackParts] = splitTopLevel(value.slice(start + 4, index));
        const fallback = fallbackParts.length ? fallbackParts.join(",").trim() : undefined;
        const variableValue = name?.startsWith("--") && !resolving.has(name) ? variables[name] : undefined;
        const candidate = variableValue == null || variableValue === ""
          ? fallback && resolveVariables(fallback, variables, resolving)
          : resolveVariables(String(variableValue), variables, new Set([...resolving, name]));
        const replacement = candidate ?? (fallback && resolveVariables(fallback, variables, resolving));
        if (replacement == null) return null;
        return resolveVariables(
          `${value.slice(0, start)}${replacement}${value.slice(index + 1)}`,
          variables,
          resolving
        );
      }
      depth -= 1;
    }
  }
  return null;
}

function normalizedVariableMap(variables: Record<string, unknown>): Record<string, unknown> {
  const normalized: Record<string, unknown> = {};
  for (const [rawKey, value] of Object.entries(variables)) {
    const key = rawKey.trim();
    if (!key) continue;
    normalized[key.startsWith("--") ? key : `--${key.replaceAll("_", "-")}`] = value;
  }
  return normalized;
}

/** Combines package CSS defaults with editable theme tokens; token overrides take precedence. */
export function appearanceColorVariables(
  cssVariables: Record<string, unknown> = {},
  themeTokens: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    ...normalizedVariableMap(cssVariables),
    ...normalizedVariableMap(themeTokens),
  };
}

export function appearanceThemeTokenValue(
  theme: ThemeEntry,
  resolvedTokens: TokenMap,
  tokenKey: string,
  cssVariables: Record<string, string> = theme.css_variables ?? {}
): unknown {
  const tokenValue = resolvedTokens[tokenKey];
  if (tokenValue != null && tokenValue !== "") return tokenValue;
  const cssKey = `--${tokenKey.replaceAll("_", "-")}`;
  return cssVariables[cssKey] ?? "";
}

function resolveColorMix(value: string): string | null {
  const match = value.match(/^color-mix\(\s*in\s+srgb\s*,\s*(.*)\)$/i);
  if (!match) return null;
  const parts = splitTopLevel(match[1]);
  if (parts.length !== 2) return null;
  const parsePart = (part: string): { color: RgbColor; weight: number | null } | null => {
    const colorMatch = part.match(/^(.*?)(?:\s+(\d+(?:\.\d+)?)%)?$/);
    if (!colorMatch) return null;
    const color = parseColor(colorMatch[1]);
    return color ? { color, weight: colorMatch[2] ? Number(colorMatch[2]) / 100 : null } : null;
  };
  const first = parsePart(parts[0]);
  const second = parsePart(parts[1]);
  if (!first || !second) return null;
  const firstWeight = first.weight ?? (second.weight == null ? 0.5 : 1 - second.weight);
  const secondWeight = second.weight ?? 1 - firstWeight;
  if (firstWeight < 0 || secondWeight < 0 || firstWeight + secondWeight <= 0) return null;
  const weight = firstWeight + secondWeight;
  return toHex({
    red: clampColorPart((first.color.red * firstWeight + second.color.red * secondWeight) / weight),
    green: clampColorPart((first.color.green * firstWeight + second.color.green * secondWeight) / weight),
    blue: clampColorPart((first.color.blue * firstWeight + second.color.blue * secondWeight) / weight),
    alpha: 1,
  });
}

/** Resolves CSS variable references to a picker-safe opaque color without modifying the source value. */
export function resolveAppearanceColor(
  value: unknown,
  variables: Record<string, unknown>,
  currentColor?: string
): string | null {
  let resolved = resolveVariables(
    String(value ?? "").trim(),
    normalizedVariableMap(variables),
    new Set()
  );
  if (!resolved) return null;
  if (resolved.toLowerCase() === "currentcolor") resolved = currentColor ?? "";
  const color = parseColor(resolved);
  return color ? toHex(color) : resolveColorMix(resolved);
}
export type AppearanceThemesStore = {
  subscribe: (run: (value: AppearanceThemesState) => void) => () => void;
  loadThemes: () => Promise<void>;
  saveThemes: (options?: { silent?: boolean }) => Promise<boolean>;
  setCurrentTheme: (key: string) => void;
  setDefaultThemeVariant: (variant: string) => void;
  setThemeVariant: (key: string, variant: string) => void;
  setThemeAccent: (key: string, accent: unknown) => void;
  setThemeToken: (
    key: string,
    tokenKey: string,
    value: unknown,
    options?: { raw?: boolean; variant?: string | null }
  ) => void;
  resetThemeToken: (
    key: string,
    tokenKey: string,
    options?: { raw?: boolean; variant?: string | null }
  ) => void;
  applyThemePreset: (key: string, variant: string, tokens: unknown) => void;
  setThemeHomeLogoScale: (
    key: string,
    mode: LogoMode,
    scale: unknown,
    variant?: string | null
  ) => void;
  resolveThemeHomeLogoScale: (
    theme: ThemeEntry | null | undefined,
    mode: LogoMode,
    variant?: string | null
  ) => number;
  resolveThemeTokens: (theme: ThemeEntry | null | undefined, variant?: string | null) => TokenMap;
  toggleAdminUse: (key: string, enabled: boolean) => void;
  uploadLogoFile: (file: File | null) => Promise<{ logoUrl: string; faviconUrl: string } | null>;
  uploadLogoUrl: (url: string) => Promise<{ logoUrl: string; faviconUrl: string } | null>;
  uploadFaviconFile: (
    file: File | null
  ) => Promise<{ faviconUrl: string; variants: TokenMap } | null>;
  uploadFaviconUrl: (url: string) => Promise<{ faviconUrl: string; variants: TokenMap } | null>;
};

export const DEFAULT_THEME_KEY = "dark";
export const DEFAULT_THEME_VARIANTS: ThemeVariant[] = ["dark", "light"];
export const VARIANT_LABELS: Record<ThemeVariant, string> = {
  dark: "Dark",
  light: "Light",
};

const SANS_FALLBACK = '-apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif';
const MONO_FALLBACK = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';
const GOOGLE_SANS_FONTS = [
  "Roboto",
  "Nunito",
  "Open Sans",
  "Montserrat",
  "Rubik",
  "Lato",
  "Ubuntu",
  "Noto Sans",
  "PT Sans",
  "IBM Plex Sans",
  "Mulish",
  "Exo 2",
  "Manrope",
  "Inter",
];
const GOOGLE_MONO_FONTS = [
  "JetBrains Mono",
  "Fira Code",
  "Roboto Mono",
  "Source Code Pro",
  "IBM Plex Mono",
  "Space Mono",
];

const quoteFontFamily = (family: string): string =>
  /^[A-Za-z0-9_-]+$/.test(String(family || "")) ? family : `"${family}"`;

export const googleSansFontStack = (family: string): string =>
  `${quoteFontFamily(family)}, ${SANS_FALLBACK}`;

export const googleMonoFontStack = (family: string): string =>
  `${quoteFontFamily(family)}, ${MONO_FALLBACK}`;

export const FONT_OPTIONS: FontOption[] = [
  { value: "", label: "System" },
  {
    value: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif',
    label: "System UI",
  },
  ...GOOGLE_SANS_FONTS.map((family) => ({
    value: googleSansFontStack(family),
    label: family,
  })),
  {
    value: '"Press Start 2P", "JetBrains Mono", monospace',
    label: "Pixel",
  },
];

export const MONO_FONT_OPTIONS: FontOption[] = [
  { value: "", label: "Default mono" },
  { value: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", label: "System mono" },
  ...GOOGLE_MONO_FONTS.map((family) => ({
    value: googleMonoFontStack(family),
    label: family,
  })),
];

export const DEFAULT_THEME_PRESETS: Record<ThemeVariant, ThemePreset[]> = {
  dark: [
    {
      id: "emerald",
      label: "Emerald",
      swatch: "#00fe7a",
      tokens: {
        color_scheme: "dark",
        bg: "#03070b",
        panel: "#111820",
        panel_2: "#0b1118",
        panel_3: "#17212b",
        text: "#f2f7f4",
        muted: "#a9b4b0",
        dim: "#68736f",
        border: "rgba(255, 255, 255, 0.12)",
        border_strong: "rgba(255, 255, 255, 0.2)",
        accent: null,
        radius: "8px",
      },
    },
    {
      id: "ocean",
      label: "Ocean",
      swatch: "#38bdf8",
      tokens: {
        color_scheme: "dark",
        accent: "#38bdf8",
        bg: "#06111f",
        panel: "#0d1b2e",
        panel_2: "#071426",
        panel_3: "#13263d",
        text: "#eff8ff",
        muted: "#a5b8ca",
        dim: "#64798c",
        border: "rgba(148, 197, 255, 0.16)",
        border_strong: "rgba(148, 197, 255, 0.28)",
      },
    },
    {
      id: "rose",
      label: "Rose",
      swatch: "#fb7185",
      tokens: {
        color_scheme: "dark",
        accent: "#fb7185",
        bg: "#12070d",
        panel: "#211019",
        panel_2: "#170912",
        panel_3: "#2b1721",
        text: "#fff4f6",
        muted: "#d7aab4",
        dim: "#8e6670",
        border: "rgba(251, 113, 133, 0.18)",
        border_strong: "rgba(251, 113, 133, 0.34)",
      },
    },
    {
      id: "neutral",
      label: "Neutral",
      swatch: "#e5e7eb",
      tokens: {
        color_scheme: "dark",
        accent: "#e5e7eb",
        bg: "#050505",
        panel: "#161616",
        panel_2: "#0d0d0d",
        panel_3: "#222222",
        text: "#f5f5f5",
        muted: "#b5b5b5",
        dim: "#747474",
        border: "rgba(255, 255, 255, 0.12)",
        border_strong: "rgba(255, 255, 255, 0.24)",
      },
    },
  ],
  light: [
    {
      id: "clean",
      label: "Clean",
      swatch: "#047857",
      tokens: {
        color_scheme: "light",
        accent: null,
        bg: "#f7f8fb",
        panel: "#ffffff",
        panel_2: "#f1f5f9",
        panel_3: "#e8edf3",
        text: "#0b1220",
        muted: "#3f4b5f",
        dim: "#526174",
        border: "rgba(15, 23, 42, 0.14)",
        border_strong: "rgba(15, 23, 42, 0.26)",
        radius: "8px",
      },
    },
    {
      id: "mint",
      label: "Mint",
      swatch: "#059669",
      tokens: {
        color_scheme: "light",
        accent: "#047857",
        bg: "#f2fbf7",
        panel: "#ffffff",
        panel_2: "#eaf7f1",
        panel_3: "#dcefe7",
        text: "#10231b",
        muted: "#4a6358",
        dim: "#6f8279",
        border: "rgba(16, 35, 27, 0.12)",
        border_strong: "rgba(16, 35, 27, 0.22)",
      },
    },
    {
      id: "sky",
      label: "Sky",
      swatch: "#2563eb",
      tokens: {
        color_scheme: "light",
        accent: "#2563eb",
        bg: "#f6f9ff",
        panel: "#ffffff",
        panel_2: "#edf4ff",
        panel_3: "#dfeafd",
        text: "#101828",
        muted: "#475467",
        dim: "#667085",
        border: "rgba(37, 99, 235, 0.14)",
        border_strong: "rgba(37, 99, 235, 0.25)",
      },
    },
    {
      id: "warm",
      label: "Warm",
      swatch: "#d97706",
      tokens: {
        color_scheme: "light",
        accent: "#9a3412",
        bg: "#fbfaf7",
        panel: "#ffffff",
        panel_2: "#f7f1e8",
        panel_3: "#efe5d5",
        text: "#1f1a14",
        muted: "#685f53",
        dim: "#807568",
        border: "rgba(31, 26, 20, 0.12)",
        border_strong: "rgba(31, 26, 20, 0.22)",
      },
    },
  ],
};
