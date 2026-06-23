export type TokenMap = Record<string, unknown>;
export type ThemeVariant = "dark" | "light";
export type FontOption = { value: string; label: string };
export type ThemeEntry = Record<string, unknown> & {
  active_variant?: string | null;
  css_file?: string;
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
export type AppearanceThemesStore = {
  subscribe: (run: (value: AppearanceThemesState) => void) => () => void;
  loadThemes: () => Promise<void>;
  saveThemes: (options?: { silent?: boolean }) => Promise<boolean>;
  setCurrentTheme: (key: string) => void;
  setDefaultThemeVariant: (variant: string) => void;
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
  setThemeHomeLogoScale: (key: string, mode: LogoMode, scale: unknown) => void;
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
        text: "#0f172a",
        muted: "#475569",
        dim: "#64748b",
        border: "rgba(15, 23, 42, 0.11)",
        border_strong: "rgba(15, 23, 42, 0.2)",
        radius: "8px",
      },
    },
    {
      id: "mint",
      label: "Mint",
      swatch: "#059669",
      tokens: {
        color_scheme: "light",
        accent: "#059669",
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
        accent: "#d97706",
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
