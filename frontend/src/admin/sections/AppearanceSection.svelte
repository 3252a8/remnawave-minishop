<script lang="ts">
  import {
    Check,
    ExternalLink,
    FileText,
    Paintbrush,
    RefreshCw,
    Save,
    Sliders,
    Sparkles,
    Type,
  } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import AdminSelect from "$components/patterns/admin/AdminSelect.svelte";
  import { Checkbox, ColorInput, FileInput, Input, RangeInput } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { getContext, onDestroy, onMount } from "svelte";

  import {
    firstFontFamily,
    localizedThemeName,
    writeThemePreviewDraft,
  } from "$lib/webapp/themeStyle.js";
  import type {
    SettingField,
    SettingsDirtyEntry,
    SettingsSavedPayload,
    SettingsSection,
    SettingsStore,
  } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SettingsDirtyState = Record<string, SettingsDirtyEntry>;
  type TokenMap = Record<string, unknown>;
  type ThemeVariant = "dark" | "light";
  type LogoMode = "desktop" | "mobile";
  type SelectCallback = (...args: never[]) => void;
  type FontOption = { value: string; label: string };
  type BrandInfo = Record<string, unknown> & { logoUrl?: string };
  type ThemeEntry = Record<string, unknown> & {
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
  type ThemeCatalog = { default_theme: string; themes: ThemeEntry[] };
  type ThemesState = {
    themesCatalog: ThemeCatalog;
    savedThemesCatalog: ThemeCatalog;
    themesLoading: boolean;
    themesDir: string;
    themesSaving: boolean;
    themesDirty: boolean;
  };
  type ThemesStore = {
    subscribe: (run: (value: ThemesState) => void) => () => void;
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

  export let at: TranslateFn;
  export let currentLang = "ru";
  export let onSettingsSaved: (payload: SettingsSavedPayload) => void | Promise<void> = () => {};
  export let brand: BrandInfo = {};
  export let appFaviconUrl = "";
  export let appFaviconUseCustom = false;

  const settingsStore = getContext<SettingsStore>("settingsStore");
  const themesStore = getContext<ThemesStore>("themesStore");
  const APPEARANCE_SETTING_KEYS = new Set([
    "SUBSCRIPTION_MINI_APP_URL",
    "WEBAPP_PRIMARY_COLOR",
    "WEBAPP_LOGO_URL",
    "WEBAPP_FAVICON_URL",
    "WEBAPP_FAVICON_USE_CUSTOM",
    "WEBAPP_LOGO_FAVICON_URL",
    "WEBAPP_ENABLED",
  ]);
  const DEFAULT_THEME_KEY = "dark";
  const DEFAULT_THEME_VARIANTS = ["dark", "light"];
  const VARIANT_LABELS = {
    dark: "Dark",
    light: "Light",
  };
  const SANS_FALLBACK = '-apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif';
  const MONO_FALLBACK =
    'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';
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
  const googleSansFontStack = (family: string): string =>
    `${quoteFontFamily(family)}, ${SANS_FALLBACK}`;
  const googleMonoFontStack = (family: string): string =>
    `${quoteFontFamily(family)}, ${MONO_FALLBACK}`;
  const FONT_OPTIONS = [
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
  const MONO_FONT_OPTIONS = [
    { value: "", label: "Default mono" },
    { value: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", label: "System mono" },
    ...GOOGLE_MONO_FONTS.map((family) => ({
      value: googleMonoFontStack(family),
      label: family,
    })),
  ];
  const DEFAULT_THEME_PRESETS = {
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
  const TOKEN_GROUPS = [
    {
      titleKey: "appearance_token_group_brand",
      title: "Brand",
      icon: Paintbrush,
      items: [
        ["accent", "appearance_token_accent", "Accent"],
        ["bg", "appearance_token_bg", "Background"],
        ["panel", "appearance_token_panel", "Card"],
        ["panel_2", "appearance_token_panel_2", "Muted card"],
        ["panel_3", "appearance_token_panel_3", "Elevated"],
      ],
    },
    {
      titleKey: "appearance_token_group_text_borders",
      title: "Text and borders",
      icon: Sliders,
      items: [
        ["text", "appearance_token_text", "Text"],
        ["muted", "appearance_token_muted", "Muted"],
        ["dim", "appearance_token_dim", "Dim"],
        ["border", "appearance_token_border", "Border"],
        ["border_strong", "appearance_token_border_strong", "Strong border"],
      ],
    },
    {
      titleKey: "appearance_token_group_states",
      title: "States",
      icon: Sparkles,
      items: [
        ["success", "appearance_token_success", "Success"],
        ["warning", "appearance_token_warning", "Warning"],
        ["danger", "appearance_token_danger", "Danger"],
        ["info", "appearance_token_info", "Info"],
      ],
    },
  ];

  let settingsSections: SettingsSection[] = [];
  let settingsLoading = false;
  let settingsDirty: SettingsDirtyState = {};
  let settingsSaving = false;
  let themesCatalog: ThemeCatalog = { default_theme: DEFAULT_THEME_KEY, themes: [] };
  let savedThemesCatalog: ThemeCatalog = { default_theme: DEFAULT_THEME_KEY, themes: [] };
  let themesLoading = false;
  let themesDir = "";
  let themesSaving = false;
  let themesDirty = false;
  let appearanceFields: SettingField[] = [];
  let fieldMap = new Map<string, SettingField>();
  let activeKey = DEFAULT_THEME_KEY;
  let logoUrl = "";
  let currentLogoUrl = "";
  let previewLogoUrl = "";
  let persistedUseCustomFavicon = false;
  let useCustomFavicon = false;
  let faviconUrl = "";
  let logoFaviconUrl = "";
  let generatedFaviconUrl = "";
  let currentFaviconUrl = "";
  let previewFaviconUrl = "";
  let dirtyCount = 0;
  let appearanceDirtyCount = 0;
  let appearanceDirtyKeys: string[] = [];
  let defaultTheme: ThemeEntry | undefined;
  let defaultVariant: ThemeVariant = "dark";
  let defaultTokens: TokenMap = {};
  let visibleThemes: ThemeEntry[] = [];
  let customThemes: ThemeEntry[] = [];
  let defaultThemeIsCurrent = false;

  $: ({ settingsSections, settingsLoading, settingsDirty, settingsSaving } = $settingsStore);
  $: ({ themesCatalog, savedThemesCatalog, themesLoading, themesDir, themesSaving, themesDirty } =
    $themesStore);
  $: appearanceFields =
    settingsSections.find((section) => section.id === "appearance")?.fields || [];
  $: fieldMap = new Map(appearanceFields.map((field) => [field.key, field]));
  $: activeKey = themesCatalog.default_theme;
  $: logoUrl = stringValueForKey("WEBAPP_LOGO_URL");
  $: currentLogoUrl = pendingLogoPreviewUrl || logoUrl || brand?.logoUrl || "";
  $: previewLogoUrl =
    logoPreviewNonce && currentLogoUrl ? withLogoCacheBust(currentLogoUrl) : currentLogoUrl;
  $: persistedUseCustomFavicon = boolValue(
    valueForKey("WEBAPP_FAVICON_USE_CUSTOM", appFaviconUseCustom)
  );
  $: if (
    !Object.prototype.hasOwnProperty.call(settingsDirty, "WEBAPP_FAVICON_USE_CUSTOM") &&
    lastPersistedUseCustomFavicon !== persistedUseCustomFavicon
  ) {
    faviconUseCustomDraft = persistedUseCustomFavicon;
    lastPersistedUseCustomFavicon = persistedUseCustomFavicon;
  }
  $: useCustomFavicon = faviconUseCustomDraft;
  $: faviconUrl = stringValueForKey("WEBAPP_FAVICON_URL", appFaviconUrl);
  $: logoFaviconUrl = stringValueForKey("WEBAPP_LOGO_FAVICON_URL");
  $: generatedFaviconUrl = logoFaviconUrl || appFaviconUrl || previewLogoUrl || "";
  $: currentFaviconUrl = useCustomFavicon
    ? pendingFaviconPreviewUrl || faviconUrl || ""
    : generatedFaviconUrl;
  $: previewFaviconUrl =
    faviconPreviewNonce && currentFaviconUrl
      ? withCacheBust(currentFaviconUrl, faviconPreviewNonce)
      : currentFaviconUrl;
  $: dirtyCount = Object.keys(settingsDirty || {}).filter((key) =>
    isAppearanceSettingKey(key)
  ).length;
  $: appearanceDirtyCount = dirtyCount + (themesDirty ? 1 : 0);
  $: appearanceDirtyKeys = Object.keys(settingsDirty || {}).filter((key) =>
    isAppearanceSettingKey(key)
  );
  $: defaultTheme = (themesCatalog.themes || []).find((theme) => theme.key === DEFAULT_THEME_KEY);
  $: defaultVariant = normalizeVariant(
    defaultTheme?.active_variant || defaultTheme?.tokens?.color_scheme
  );
  $: defaultTokens = defaultTheme
    ? themesStore.resolveThemeTokens(defaultTheme, defaultVariant)
    : {};
  $: visibleThemes = (themesCatalog.themes || []).filter(
    (theme) => !theme.hidden && !theme.variant_alias_for
  );
  $: customThemes = visibleThemes.filter((theme) => theme.key !== DEFAULT_THEME_KEY);
  $: defaultThemeIsCurrent = activeKey === DEFAULT_THEME_KEY;

  let logoFileInput: HTMLInputElement | null = null;
  let faviconFileInput: HTMLInputElement | null = null;
  let customGoogleFontName = "";
  let logoSourceUrl = "";
  let faviconSourceUrl = "";
  let logoPreviewNonce = 0;
  let faviconPreviewNonce = 0;
  let logoPreviewFailed = false;
  let faviconPreviewFailed = false;
  let lastPreviewLogoUrl = "";
  let lastPreviewFaviconUrl = "";
  let lastPersistedUseCustomFavicon: boolean | undefined;
  let faviconUseCustomDraft = false;
  let pendingLogoPreviewUrl = "";
  let pendingFaviconPreviewUrl = "";
  let pendingObjectUrl = "";
  let pendingFaviconObjectUrl = "";

  $: if (previewLogoUrl !== lastPreviewLogoUrl) {
    lastPreviewLogoUrl = previewLogoUrl;
    logoPreviewFailed = false;
  }

  $: if (previewFaviconUrl !== lastPreviewFaviconUrl) {
    lastPreviewFaviconUrl = previewFaviconUrl;
    faviconPreviewFailed = false;
  }

  function valueForKey(key: string, fallback: unknown = ""): unknown {
    if (settingsDirty[key]?.deleted) return "";
    if (Object.prototype.hasOwnProperty.call(settingsDirty, key)) {
      return settingsDirty[key].value;
    }
    const field = fieldMap.get(key);
    if (!field) return fallback;
    return field.value ?? fallback;
  }

  function stringValueForKey(key: string, fallback = ""): string {
    const value = valueForKey(key, fallback);
    return value == null ? "" : String(value);
  }

  function isAppearanceSettingKey(key: string): boolean {
    return APPEARANCE_SETTING_KEYS.has(key) || appearanceFields.some((field) => field.key === key);
  }

  function boolValue(value: unknown): boolean {
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  }

  function withLogoCacheBust(url: string): string {
    return withCacheBust(url, logoPreviewNonce);
  }

  function withCacheBust(url: string, nonce: number): string {
    if (!url || url.startsWith("data:") || url.startsWith("blob:")) return url;
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}v=${nonce}`;
  }

  function clearPendingObjectUrl(): void {
    if (pendingObjectUrl && typeof URL !== "undefined") {
      URL.revokeObjectURL(pendingObjectUrl);
    }
    pendingObjectUrl = "";
  }

  function clearPendingFaviconObjectUrl(): void {
    if (pendingFaviconObjectUrl && typeof URL !== "undefined") {
      URL.revokeObjectURL(pendingFaviconObjectUrl);
    }
    pendingFaviconObjectUrl = "";
  }

  function setPendingLogoPreview(url: string, objectUrl = ""): void {
    clearPendingObjectUrl();
    pendingObjectUrl = objectUrl;
    pendingLogoPreviewUrl = url;
    logoPreviewFailed = false;
    logoPreviewNonce = Date.now();
  }

  function setPendingFaviconPreview(url: string, objectUrl = ""): void {
    clearPendingFaviconObjectUrl();
    pendingFaviconObjectUrl = objectUrl;
    pendingFaviconPreviewUrl = url;
    faviconPreviewFailed = false;
    faviconPreviewNonce = Date.now();
  }

  function themeTitle(theme: ThemeEntry): string {
    return localizedThemeName(theme, currentLang) || "—";
  }

  function themeDescription(theme: ThemeEntry): string {
    const folder = `${themesDir || "data/themes"}/${theme.key}`;
    return theme.css_file ? `${folder}/${theme.css_file}` : `${folder}/theme.json`;
  }

  function isThemeAccentSet(theme: ThemeEntry): boolean {
    return Boolean(String(theme.tokens?.accent || "").trim());
  }

  function pickerHex(value: unknown): string {
    const raw = String(value || "").trim();
    const match = raw.match(/^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/);
    if (!match) return "#000000";
    let hex = match[1].toLowerCase();
    if (hex.length === 3)
      hex = hex
        .split("")
        .map((char) => char + char)
        .join("");
    return `#${hex}`;
  }

  function normalizeVariant(variant: unknown): ThemeVariant {
    return String(variant || "")
      .trim()
      .toLowerCase() === "light"
      ? "light"
      : "dark";
  }

  function defaultVariantTitle(variant: unknown): string {
    const normalizedVariant = normalizeVariant(variant);
    return VARIANT_LABELS[normalizedVariant] || normalizedVariant;
  }

  function defaultTokenValue(tokenKey: string, tokens: TokenMap = defaultTokens): unknown {
    return tokens?.[tokenKey] ?? "";
  }

  function tokenTextValue(tokenKey: string, tokens: TokenMap = defaultTokens): string {
    const value = defaultTokenValue(tokenKey, tokens);
    return value == null ? "" : String(value);
  }

  function inputValue(event: Event): string {
    return (event.currentTarget as HTMLInputElement | null)?.value ?? "";
  }

  function normalizedCompareValue(value: unknown): string {
    return String(value ?? "").trim();
  }

  function savedThemeByKey(key: string): ThemeEntry | null {
    return (savedThemesCatalog.themes || []).find((theme) => theme.key === key) || null;
  }

  function themeFingerprint(theme: unknown): string {
    return JSON.stringify(theme || null);
  }

  function isThemeDirty(theme: ThemeEntry | null | undefined): boolean {
    if (!theme) return false;
    const savedTheme = savedThemeByKey(theme.key);
    if (!savedTheme) return false;
    return themeFingerprint(theme) !== themeFingerprint(savedTheme);
  }

  function themeTokenValue(
    theme: ThemeEntry | null | undefined,
    tokenKey: string,
    variant: string | null = null
  ): unknown {
    if (!theme) return "";
    if (theme.key === DEFAULT_THEME_KEY) {
      return themesStore.resolveThemeTokens(theme, variant || defaultVariant)?.[tokenKey] ?? "";
    }
    return theme.tokens?.[tokenKey] ?? "";
  }

  function isThemeTokenDirty(
    theme: ThemeEntry | null | undefined,
    tokenKey: string,
    variant: string | null = null
  ): boolean {
    if (!theme) return false;
    const savedTheme = savedThemeByKey(theme.key);
    if (!savedTheme) return false;
    return (
      normalizedCompareValue(themeTokenValue(theme, tokenKey, variant)) !==
      normalizedCompareValue(themeTokenValue(savedTheme, tokenKey, variant))
    );
  }

  function isThemePropertyDirty(theme: ThemeEntry | null | undefined, property: string): boolean {
    if (!theme) return false;
    const savedTheme = savedThemeByKey(theme.key);
    if (!savedTheme) return false;
    return (
      normalizedCompareValue(theme?.[property]) !== normalizedCompareValue(savedTheme?.[property])
    );
  }

  function isDefaultTokenDirty(tokenKey: string): boolean {
    return isThemeTokenDirty(defaultTheme, tokenKey, defaultVariant);
  }

  function isDefaultVariantDirty(): boolean {
    return isThemePropertyDirty(defaultTheme, "active_variant");
  }

  function isThemeHomeLogoScaleDirty(
    theme: ThemeEntry | null | undefined,
    mode: LogoMode,
    variant: string | null = null
  ): boolean {
    if (!theme) return false;
    const savedTheme = savedThemeByKey(theme.key);
    if (!savedTheme) return false;
    return (
      Number(themesStore.resolveThemeHomeLogoScale(theme, mode, variant)) !==
      Number(themesStore.resolveThemeHomeLogoScale(savedTheme, mode, variant))
    );
  }

  function fontItemsWithCurrent(items: FontOption[], value: unknown): FontOption[] {
    const currentValue = String(value ?? "");
    if (!currentValue || items.some((item) => item.value === currentValue)) return items;
    return [
      {
        value: currentValue,
        label: `${at("appearance_font_custom_current", {}, "Custom")}: ${
          firstFontFamily(currentValue) || currentValue
        }`,
      },
      ...items,
    ];
  }

  function customGoogleFontStack(kind: "sans" | "mono" = "sans"): string {
    const family = String(customGoogleFontName || "").trim();
    if (!family) return "";
    return kind === "mono" ? googleMonoFontStack(family) : googleSansFontStack(family);
  }

  function applyCustomGoogleFont(tokenKey: string, kind: "sans" | "mono" = "sans"): void {
    const stack = customGoogleFontStack(kind);
    if (!stack) return;
    setDefaultFont(tokenKey, stack);
  }

  function setDefaultVariantFromSwitch(checked: boolean): void {
    themesStore.setDefaultThemeVariant(checked ? "light" : "dark");
  }

  function setDefaultToken(tokenKey: string, value: unknown): void {
    themesStore.setThemeToken(DEFAULT_THEME_KEY, tokenKey, value, { variant: defaultVariant });
  }

  function resetDefaultToken(tokenKey: string): void {
    themesStore.resetThemeToken(DEFAULT_THEME_KEY, tokenKey, { variant: defaultVariant });
  }

  function setDefaultColorToken(tokenKey: string, value: unknown): void {
    setDefaultToken(tokenKey, value);
  }

  function openDefaultColorPicker(tokenKey: string, fallback = "#00fe7a"): void {
    setDefaultColorToken(tokenKey, pickerHex(defaultTokenValue(tokenKey) || fallback));
  }

  function setDefaultRadius(value: unknown): void {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    setDefaultToken("radius", `${Math.min(28, Math.max(4, Math.round(numeric)))}px`);
  }

  const defaultRadiusRangeHandler = ((value: number) => setDefaultRadius(value)) as SelectCallback;

  function radiusNumber(tokens: TokenMap = defaultTokens): number {
    const match = String(defaultTokenValue("radius", tokens) || "").match(/(\d+)/);
    return match ? Math.min(28, Math.max(4, Number(match[1]))) : 8;
  }

  function setDefaultFont(tokenKey: string, value: unknown): void {
    for (const variant of DEFAULT_THEME_VARIANTS) {
      themesStore.setThemeToken(DEFAULT_THEME_KEY, tokenKey, value, { variant });
    }
  }

  function applyDefaultPreset(preset: { tokens?: TokenMap } | null | undefined): void {
    if (!preset?.tokens) return;
    themesStore.applyThemePreset(DEFAULT_THEME_KEY, defaultVariant, preset.tokens);
  }

  function defaultHomeLogoScale(
    mode: LogoMode,
    theme: ThemeEntry | null | undefined = defaultTheme,
    variant: string | null = defaultVariant
  ): number {
    return themesStore.resolveThemeHomeLogoScale(theme, mode, variant);
  }

  function setDefaultHomeLogoScale(mode: LogoMode, value: unknown): void {
    themesStore.setThemeHomeLogoScale(DEFAULT_THEME_KEY, mode, value);
  }

  function homeLogoScale(theme: ThemeEntry, mode: LogoMode): number {
    return Number(themesStore.resolveThemeHomeLogoScale(theme, mode)) || 0;
  }

  function defaultFontSelectHandler(tokenKey: string): SelectCallback {
    return ((value: string) => setDefaultFont(tokenKey, value)) as SelectCallback;
  }

  function defaultLogoScaleSelectHandler(mode: LogoMode): SelectCallback {
    return ((value: number) => setDefaultHomeLogoScale(mode, value)) as SelectCallback;
  }

  function themeLogoScaleSelectHandler(theme: ThemeEntry, mode: LogoMode): SelectCallback {
    return ((value: number) => setThemeHomeLogoScale(theme, mode, value)) as SelectCallback;
  }

  function defaultRadiusInputHandler(event: Event): void {
    setDefaultRadius(inputValue(event));
  }

  function defaultLogoScaleInputHandler(mode: LogoMode): (event: Event) => void {
    return (event) => setDefaultHomeLogoScale(mode, inputValue(event));
  }

  function themeLogoScaleInputHandler(theme: ThemeEntry, mode: LogoMode): (event: Event) => void {
    return (event) => setThemeHomeLogoScale(theme, mode, inputValue(event));
  }

  function defaultTokenInputHandler(tokenKey: string): (event: Event) => void {
    return (event) => setDefaultToken(tokenKey, inputValue(event));
  }

  function defaultColorInputHandler(tokenKey: string): (event: Event) => void {
    return (event) => setDefaultColorToken(tokenKey, inputValue(event));
  }

  function themeAccentInputHandler(theme: ThemeEntry): (event: Event) => void {
    return (event) => setThemeAccent(theme, inputValue(event));
  }

  function openThemeAccentPicker(theme: ThemeEntry): void {
    themesStore.setThemeAccent(theme.key, pickerHex(theme.tokens?.accent || "#00fe7a"));
  }

  function handleLogoFileChange(event: Event): void {
    const input = event.currentTarget as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) return;
    if (typeof URL !== "undefined") {
      const objectUrl = URL.createObjectURL(file);
      setPendingLogoPreview(objectUrl, objectUrl);
    }
    themesStore.uploadLogoFile(file).then((uploaded) => {
      const uploadedUrl = uploaded?.logoUrl || "";
      if (!uploadedUrl) {
        pendingLogoPreviewUrl = "";
        clearPendingObjectUrl();
        return;
      }
      settingsStore.setFieldValue("WEBAPP_LOGO_URL", uploadedUrl);
      if (uploaded?.faviconUrl) {
        settingsStore.setFieldValue("WEBAPP_LOGO_FAVICON_URL", uploaded.faviconUrl);
      }
      if (logoFileInput) logoFileInput.value = "";
    });
  }

  function uploadLogoFromUrl(): void {
    themesStore.uploadLogoUrl(logoSourceUrl).then((uploaded) => {
      const uploadedUrl = uploaded?.logoUrl || "";
      if (!uploadedUrl) return;
      setPendingLogoPreview(uploadedUrl);
      logoSourceUrl = "";
      settingsStore.setFieldValue("WEBAPP_LOGO_URL", uploadedUrl);
      if (uploaded?.faviconUrl) {
        settingsStore.setFieldValue("WEBAPP_LOGO_FAVICON_URL", uploaded.faviconUrl);
      }
    });
  }

  function handleFaviconFileChange(event: Event): void {
    const input = event.currentTarget as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) return;
    if (typeof URL !== "undefined") {
      const objectUrl = URL.createObjectURL(file);
      setPendingFaviconPreview(objectUrl, objectUrl);
    }
    themesStore.uploadFaviconFile(file).then((uploaded) => {
      const uploadedUrl = uploaded?.faviconUrl || "";
      if (!uploadedUrl) {
        pendingFaviconPreviewUrl = "";
        clearPendingFaviconObjectUrl();
        return;
      }
      settingsStore.setFieldValue("WEBAPP_FAVICON_URL", uploadedUrl);
      settingsStore.setFieldValue("WEBAPP_FAVICON_USE_CUSTOM", true);
      faviconUseCustomDraft = true;
      if (faviconFileInput) faviconFileInput.value = "";
    });
  }

  function uploadFaviconFromUrl(): void {
    themesStore.uploadFaviconUrl(faviconSourceUrl).then((uploaded) => {
      const uploadedUrl = uploaded?.faviconUrl || "";
      if (!uploadedUrl) return;
      setPendingFaviconPreview(uploadedUrl);
      faviconSourceUrl = "";
      settingsStore.setFieldValue("WEBAPP_FAVICON_URL", uploadedUrl);
      settingsStore.setFieldValue("WEBAPP_FAVICON_USE_CUSTOM", true);
      faviconUseCustomDraft = true;
    });
  }

  function setCustomFavicon(enabled: boolean): void {
    const nextEnabled = Boolean(enabled);
    faviconUseCustomDraft = nextEnabled;
    settingsStore.markDirty("WEBAPP_FAVICON_USE_CUSTOM", nextEnabled);
    if (!nextEnabled) {
      pendingFaviconPreviewUrl = "";
      clearPendingFaviconObjectUrl();
    }
  }

  async function saveAppearance(): Promise<void> {
    const keysToSave = new Set(appearanceDirtyKeys);
    const shouldReloadFrontend = Array.from(keysToSave).some((key) =>
      [
        "WEBAPP_LOGO_URL",
        "WEBAPP_FAVICON_URL",
        "WEBAPP_FAVICON_USE_CUSTOM",
        "WEBAPP_LOGO_FAVICON_URL",
      ].includes(key)
    );
    let settingsSaved = true;
    if (keysToSave.size) {
      settingsSaved = await settingsStore.saveSettings((payload) =>
        onSettingsSaved({ ...payload, deferFrontendReload: true })
      );
    }
    await themesStore.saveThemes();
    if (settingsSaved && shouldReloadFrontend && typeof onSettingsSaved === "function") {
      await onSettingsSaved({ updates: {}, deletes: [], reloadFrontend: true });
    }
  }

  function toggleAdminTheme(theme: ThemeEntry, checked: boolean): void {
    themesStore.toggleAdminUse(theme.key, checked);
  }

  function setThemeAccent(theme: ThemeEntry, value: unknown): void {
    themesStore.setThemeAccent(theme.key, value);
  }

  function setThemeHomeLogoScale(theme: ThemeEntry, mode: LogoMode, value: unknown): void {
    themesStore.setThemeHomeLogoScale(theme.key, mode, value);
  }

  function activateDefaultTheme(): void {
    if (!themesSaving) themesStore.setCurrentTheme(DEFAULT_THEME_KEY);
  }

  function activateDefaultThemeFromClick(event: MouseEvent): void {
    event.stopPropagation();
    activateDefaultTheme();
  }

  function isThemeControlTarget(target: EventTarget | null | undefined): boolean {
    return (
      target instanceof Element &&
      Boolean(target.closest("button,input,label,.admin-theme-card-option,.ui-range-input"))
    );
  }

  function selectDefaultTheme(event: MouseEvent | KeyboardEvent | null = null): void {
    if (isThemeControlTarget(event?.target)) return;
    activateDefaultTheme();
  }

  function handleDefaultThemeKeydown(event: KeyboardEvent): void {
    if (isThemeControlTarget(event?.target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activateDefaultTheme();
  }

  function selectTheme(theme: ThemeEntry, event: MouseEvent | KeyboardEvent | null = null): void {
    if (isThemeControlTarget(event?.target)) return;
    if (!themesSaving) themesStore.setCurrentTheme(theme.key);
  }

  function handleThemeKeydown(event: KeyboardEvent, theme: ThemeEntry): void {
    if (isThemeControlTarget(event?.target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    selectTheme(theme);
  }

  function clonePreviewCatalog(catalog: ThemeCatalog = themesCatalog): ThemeCatalog {
    return JSON.parse(JSON.stringify(catalog || { default_theme: DEFAULT_THEME_KEY, themes: [] }));
  }

  function previewCatalogForDefaultVariant(variant: unknown): ThemeCatalog {
    const nextVariant = normalizeVariant(variant);
    const catalog = clonePreviewCatalog();
    catalog.default_theme = DEFAULT_THEME_KEY;
    catalog.themes = (catalog.themes || []).map((theme) => {
      if (theme.key === DEFAULT_THEME_KEY) {
        return { ...theme, default: true, active_variant: nextVariant };
      }
      return { ...theme, default: false };
    });
    return catalog;
  }

  function themePreviewUrl(themeKey: string): string {
    const url = new URL(window.location.href);
    const docsRuntimeIndex = url.pathname.indexOf("/demo/runtime");
    if (docsRuntimeIndex >= 0) {
      url.pathname = `${url.pathname.slice(0, docsRuntimeIndex)}/demo/runtime/app/`;
    } else {
      const adminPathIndex = url.pathname.lastIndexOf("/admin");
      const basePath = adminPathIndex >= 0 ? url.pathname.slice(0, adminPathIndex) : "";
      url.pathname = `${basePath}/home`;
    }
    url.searchParams.set("theme_preview", themeKey);
    url.searchParams.delete("screen");
    url.searchParams.delete("admin_section");
    url.hash = "";
    return url.toString();
  }

  function previewTheme(event: MouseEvent, theme: ThemeEntry): void {
    event.stopPropagation();
    writeThemePreviewDraft(clonePreviewCatalog(), theme.key);
    window.open(themePreviewUrl(theme.key), "_blank", "noopener");
  }

  function previewThemeClickHandler(theme: ThemeEntry): (event: MouseEvent) => void {
    return (event) => previewTheme(event, theme);
  }

  function previewDefaultVariant(event: MouseEvent, variant: ThemeVariant): void {
    event.stopPropagation();
    writeThemePreviewDraft(previewCatalogForDefaultVariant(variant), DEFAULT_THEME_KEY);
    window.open(themePreviewUrl(DEFAULT_THEME_KEY), "_blank", "noopener");
  }

  function previewDefaultVariantFromClick(event: MouseEvent): void {
    previewDefaultVariant(event, defaultVariant);
  }

  onMount(() => {
    themesStore.loadThemes();
    settingsStore.loadSettings();
  });

  onDestroy(() => {
    clearPendingObjectUrl();
    clearPendingFaviconObjectUrl();
  });
</script>

{#if themesLoading || settingsLoading}
  <AdminEmptyState>{at("loading", {}, "Загрузка…")}</AdminEmptyState>
{:else}
  <div class="appearance-stack">
    <article class="admin-card">
      <header class="admin-card-head">
        <div>
          <h3>{at("appearance_brand_title", {}, "Логотип")}</h3>
          <small>{at("appearance_brand_sub", {}, "Загрузите логотип файлом или по ссылке")}</small>
        </div>
        <div class="admin-editor-section-actions">
          {#if appearanceDirtyCount}
            <AdminBadge variant="warning">
              {at(
                "settings_dirty_count",
                { count: appearanceDirtyCount },
                `Изменений: ${appearanceDirtyCount}`
              )}
            </AdminBadge>
          {/if}
          <AdminButton
            size="sm"
            variant="primary"
            onclick={saveAppearance}
            disabled={settingsSaving || themesSaving}
          >
            <Save size={13} />
            {settingsSaving || themesSaving
              ? at("btn_saving", {}, "Сохранение...")
              : at("btn_save", {}, "Сохранить")}
          </AdminButton>
        </div>
      </header>
      <div class="admin-card-body appearance-logo-grid">
        <div class="appearance-logo-preview">
          {#if previewLogoUrl && !logoPreviewFailed}
            <img
              class="appearance-logo-image"
              src={previewLogoUrl}
              alt=""
              loading="eager"
              decoding="async"
              onerror={() => {
                logoPreviewFailed = true;
              }}
            />
          {:else}
            <span class="appearance-logo-empty" aria-hidden="true"></span>
          {/if}
        </div>

        <div class="appearance-controls">
          <section class="appearance-control-card">
            <FileInput
              bind:element={logoFileInput}
              class="appearance-file-input"
              accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml,image/x-icon"
              onchange={handleLogoFileChange}
            />
            <AdminButton
              class="appearance-control"
              size="sm"
              onclick={() => logoFileInput?.click()}
              disabled={themesSaving}
            >
              <FileText size={13} />
              {at("appearance_logo_upload_file", {}, "Загрузить файл")}
            </AdminButton>
            <div class="appearance-url-row">
              <Input
                class="input appearance-control"
                type="url"
                placeholder="https://example.com/logo.png"
                bind:value={logoSourceUrl}
              />
              <AdminButton
                class="appearance-control"
                size="sm"
                onclick={uploadLogoFromUrl}
                disabled={themesSaving || !logoSourceUrl.trim()}
              >
                {at("appearance_logo_upload_url", {}, "По ссылке")}
              </AdminButton>
            </div>
          </section>
        </div>
      </div>

      <div class="admin-card-body appearance-logo-grid appearance-favicon-grid">
        <div class="appearance-logo-preview appearance-favicon-preview">
          {#if previewFaviconUrl && !faviconPreviewFailed}
            <img
              class="appearance-logo-image"
              src={previewFaviconUrl}
              alt=""
              loading="eager"
              decoding="async"
              onerror={() => {
                faviconPreviewFailed = true;
              }}
            />
          {:else}
            <span class="appearance-logo-empty" aria-hidden="true"></span>
          {/if}
        </div>

        <div class="appearance-controls">
          <section class="appearance-control-card">
            <label class="appearance-switch">
              <Switch.Root
                bind:checked={faviconUseCustomDraft}
                onCheckedChange={setCustomFavicon}
                class="admin-switch-root"
              >
                <Switch.Thumb class="admin-switch-thumb" />
              </Switch.Root>
              <span
                >{at("appearance_use_custom_favicon", {}, "Использовать отдельную favicon")}</span
              >
            </label>
            <FileInput
              bind:element={faviconFileInput}
              class="appearance-file-input"
              accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml,image/x-icon,.ico"
              onchange={handleFaviconFileChange}
            />
            <AdminButton
              class="appearance-control"
              size="sm"
              onclick={() => faviconFileInput?.click()}
              disabled={themesSaving}
            >
              <FileText size={13} />
              {at("appearance_favicon_upload_file", {}, "Загрузить favicon")}
            </AdminButton>
            <div class="appearance-url-row">
              <Input
                class="input appearance-control"
                type="url"
                placeholder="https://example.com/icon.png"
                bind:value={faviconSourceUrl}
              />
              <AdminButton
                class="appearance-control"
                size="sm"
                onclick={uploadFaviconFromUrl}
                disabled={themesSaving || !faviconSourceUrl.trim()}
              >
                {at("appearance_favicon_upload_url", {}, "По ссылке")}
              </AdminButton>
            </div>
          </section>
        </div>
      </div>
    </article>

    <article class="admin-card">
      <header class="admin-card-head">
        <div>
          <h3>{at("appearance_themes_title", {}, "Темы")}</h3>
          <small
            >{at(
              "appearance_themes_sub",
              {},
              "Глобальная тема, accent color и предпросмотр"
            )}</small
          >
        </div>
        <div class="admin-editor-section-actions">
          <AdminButton
            size="sm"
            onclick={themesStore.loadThemes}
            disabled={themesLoading || themesSaving}
          >
            <RefreshCw size={13} />
            {at("btn_refresh", {}, "Обновить")}
          </AdminButton>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={saveAppearance}
            disabled={settingsSaving || themesSaving}
          >
            <Save size={13} />
            {at("btn_save", {}, "Сохранить")}
          </AdminButton>
        </div>
      </header>
      <div class="admin-card-body appearance-themes-body">
        {#if !visibleThemes.length}
          <AdminEmptyState>
            {at(
              "themes_catalog_empty",
              {},
              "Каталог пуст. Добавьте папку темы в data/themes и обновите список."
            )}
          </AdminEmptyState>
        {:else}
          <section class="appearance-theme-section">
            <header class="appearance-theme-section-head">
              <div>
                <h4>{at("appearance_default_theme_title", {}, "Тема по-умолчанию")}</h4>
                <small>
                  {at(
                    "appearance_default_theme_section_sub",
                    {},
                    "Базовая тема приложения: темный и светлый режимы, цвета, шрифты и логотип."
                  )}
                </small>
              </div>
              {#if isThemeDirty(defaultTheme)}
                <AdminBadge variant="warning">
                  {at("settings_badge_dirty", {}, "Изменено")}
                </AdminBadge>
              {/if}
            </header>
            {#if defaultTheme}
              <section
                role="button"
                tabindex={themesSaving ? -1 : 0}
                class="default-theme-editor"
                class:is-current={defaultThemeIsCurrent}
                class:is-disabled={themesSaving}
                class:is-dirty={isThemeDirty(defaultTheme)}
                aria-pressed={defaultThemeIsCurrent}
                aria-disabled={themesSaving}
                onclick={(event) => selectDefaultTheme(event)}
                onkeydown={(event) => handleDefaultThemeKeydown(event)}
              >
                <div class="default-theme-head">
                  <div>
                    <div class="default-theme-title">
                      <Paintbrush size={17} />
                      <strong
                        >{at("appearance_default_theme_title", {}, "Тема по-умолчанию")}</strong
                      >
                      {#if defaultThemeIsCurrent}
                        <AdminBadge variant="success"
                          >{at("status_current", {}, "Current")}</AdminBadge
                        >
                      {/if}
                      <AdminBadge>{defaultVariantTitle(defaultVariant)}</AdminBadge>
                      {#if isDefaultVariantDirty()}
                        <AdminBadge variant="warning"
                          >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                        >
                      {/if}
                      {#if defaultThemeIsCurrent}
                        <span class="default-theme-check" aria-hidden="true">
                          <Check size={18} />
                        </span>
                      {/if}
                    </div>
                    <small>{themeDescription(defaultTheme)}</small>
                  </div>
                  <div class="default-theme-actions">
                    {#if !defaultThemeIsCurrent}
                      <AdminButton
                        size="sm"
                        onclick={activateDefaultThemeFromClick}
                        disabled={themesSaving}
                      >
                        <Check size={13} />
                        {at("appearance_use_default_theme", {}, "Выбрать тему по-умолчанию")}
                      </AdminButton>
                    {/if}
                    <label class="appearance-switch appearance-mode-switch">
                      <span>{at("appearance_default_dark", {}, "Dark")}</span>
                      <Switch.Root
                        checked={defaultVariant === "light"}
                        onCheckedChange={setDefaultVariantFromSwitch}
                        class="admin-switch-root"
                      >
                        <Switch.Thumb class="admin-switch-thumb" />
                      </Switch.Root>
                      <span>{at("appearance_default_light", {}, "Light")}</span>
                    </label>
                    <AdminButton size="sm" variant="ghost" onclick={previewDefaultVariantFromClick}>
                      <ExternalLink size={13} />
                      {at("appearance_preview_theme", {}, "Preview")}
                    </AdminButton>
                  </div>
                </div>

                <div class="appearance-preset-row" aria-label="Default theme presets">
                  {#each DEFAULT_THEME_PRESETS[defaultVariant] || [] as preset (preset.id)}
                    <button
                      type="button"
                      class="appearance-preset-btn"
                      onclick={() => applyDefaultPreset(preset)}
                    >
                      <span style={`background:${preset.swatch}`}></span>
                      {preset.label}
                    </button>
                  {/each}
                </div>

                <div class="default-theme-grid">
                  <section class="default-theme-panel">
                    <h4><Type size={15} /> {at("appearance_typography", {}, "Typography")}</h4>
                    <div class="appearance-select-grid">
                      <label class:is-dirty={isDefaultTokenDirty("font_sans")}>
                        <span>
                          {at("appearance_font_ui", {}, "Interface")}
                          {#if isDefaultTokenDirty("font_sans")}
                            <AdminBadge variant="warning"
                              >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                            >
                          {/if}
                        </span>
                        <AdminSelect
                          class="appearance-select"
                          value={tokenTextValue("font_sans", defaultTokens)}
                          items={fontItemsWithCurrent(
                            FONT_OPTIONS,
                            tokenTextValue("font_sans", defaultTokens)
                          )}
                          placeholder="System"
                          onValueChange={defaultFontSelectHandler("font_sans")}
                        />
                      </label>
                      <label class:is-dirty={isDefaultTokenDirty("font_logo")}>
                        <span>
                          {at("appearance_font_brand", {}, "Brand")}
                          {#if isDefaultTokenDirty("font_logo")}
                            <AdminBadge variant="warning"
                              >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                            >
                          {/if}
                        </span>
                        <AdminSelect
                          class="appearance-select"
                          value={tokenTextValue("font_logo", defaultTokens)}
                          items={fontItemsWithCurrent(
                            FONT_OPTIONS,
                            tokenTextValue("font_logo", defaultTokens)
                          )}
                          placeholder="System"
                          onValueChange={defaultFontSelectHandler("font_logo")}
                        />
                      </label>
                      <label class:is-dirty={isDefaultTokenDirty("font_mono")}>
                        <span>
                          {at("appearance_font_mono", {}, "Mono")}
                          {#if isDefaultTokenDirty("font_mono")}
                            <AdminBadge variant="warning"
                              >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                            >
                          {/if}
                        </span>
                        <AdminSelect
                          class="appearance-select"
                          value={tokenTextValue("font_mono", defaultTokens)}
                          items={fontItemsWithCurrent(
                            MONO_FONT_OPTIONS,
                            tokenTextValue("font_mono", defaultTokens)
                          )}
                          placeholder="Default mono"
                          onValueChange={defaultFontSelectHandler("font_mono")}
                        />
                      </label>
                    </div>
                    <div class="appearance-custom-font-row">
                      <Input
                        class="input"
                        type="text"
                        placeholder={at("appearance_font_google_placeholder", {}, "Nunito Sans")}
                        bind:value={customGoogleFontName}
                        aria-label={at("appearance_font_google_custom", {}, "Google Font family")}
                      />
                      <AdminButton
                        size="sm"
                        onclick={() => applyCustomGoogleFont("font_sans")}
                        disabled={!customGoogleFontName.trim()}
                      >
                        <Type size={12} />
                        {at("appearance_font_apply_ui", {}, "Interface")}
                      </AdminButton>
                      <AdminButton
                        size="sm"
                        onclick={() => applyCustomGoogleFont("font_logo")}
                        disabled={!customGoogleFontName.trim()}
                      >
                        <Type size={12} />
                        {at("appearance_font_apply_brand", {}, "Brand")}
                      </AdminButton>
                      <AdminButton
                        size="sm"
                        onclick={() => applyCustomGoogleFont("font_mono", "mono")}
                        disabled={!customGoogleFontName.trim()}
                      >
                        <Type size={12} />
                        {at("appearance_font_apply_mono", {}, "Mono")}
                      </AdminButton>
                    </div>
                  </section>

                  <section class="default-theme-panel">
                    <h4>
                      <Sliders size={15} />
                      {at("appearance_shape_logo", {}, "Shape and logo")}
                    </h4>
                    <div
                      class="appearance-logo-scale-row appearance-default-scale-row"
                      class:is-dirty={isDefaultTokenDirty("radius")}
                    >
                      <span class="appearance-logo-scale-label">
                        {at("appearance_radius", {}, "Radius")}
                        {#if isDefaultTokenDirty("radius")}
                          <AdminBadge variant="warning"
                            >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                          >
                        {/if}
                      </span>
                      <RangeInput
                        class="appearance-logo-scale-range"
                        min="4"
                        max="28"
                        step="1"
                        ariaLabel={at("appearance_radius", {}, "Radius")}
                        value={radiusNumber(defaultTokens)}
                        onValueChange={defaultRadiusRangeHandler}
                      />
                      <span class="appearance-logo-scale-value">
                        <Input
                          class="input"
                          type="number"
                          min="4"
                          max="28"
                          step="1"
                          value={radiusNumber(defaultTokens)}
                          oninput={defaultRadiusInputHandler}
                        />
                        px
                      </span>
                    </div>
                    <div
                      class="appearance-logo-scale-row appearance-default-scale-row"
                      class:is-dirty={isThemeHomeLogoScaleDirty(
                        defaultTheme,
                        "desktop",
                        defaultVariant
                      )}
                    >
                      <span class="appearance-logo-scale-label">
                        {at("appearance_logo_desktop", {}, "Desktop logo")}
                        {#if isThemeHomeLogoScaleDirty(defaultTheme, "desktop", defaultVariant)}
                          <AdminBadge variant="warning"
                            >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                          >
                        {/if}
                      </span>
                      <RangeInput
                        class="appearance-logo-scale-range"
                        min="50"
                        max="300"
                        step="5"
                        ariaLabel={at("appearance_logo_desktop", {}, "Desktop logo")}
                        value={defaultHomeLogoScale("desktop", defaultTheme, defaultVariant)}
                        onValueChange={defaultLogoScaleSelectHandler("desktop")}
                      />
                      <span class="appearance-logo-scale-value">
                        <Input
                          class="input"
                          type="number"
                          min="50"
                          max="300"
                          step="5"
                          value={defaultHomeLogoScale("desktop", defaultTheme, defaultVariant)}
                          oninput={defaultLogoScaleInputHandler("desktop")}
                        />
                        %
                      </span>
                    </div>
                    <div
                      class="appearance-logo-scale-row appearance-default-scale-row"
                      class:is-dirty={isThemeHomeLogoScaleDirty(
                        defaultTheme,
                        "mobile",
                        defaultVariant
                      )}
                    >
                      <span class="appearance-logo-scale-label">
                        {at("appearance_logo_mobile", {}, "Mobile logo")}
                        {#if isThemeHomeLogoScaleDirty(defaultTheme, "mobile", defaultVariant)}
                          <AdminBadge variant="warning"
                            >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                          >
                        {/if}
                      </span>
                      <RangeInput
                        class="appearance-logo-scale-range"
                        min="50"
                        max="300"
                        step="5"
                        ariaLabel={at("appearance_logo_mobile", {}, "Mobile logo")}
                        value={defaultHomeLogoScale("mobile", defaultTheme, defaultVariant)}
                        onValueChange={defaultLogoScaleSelectHandler("mobile")}
                      />
                      <span class="appearance-logo-scale-value">
                        <Input
                          class="input"
                          type="number"
                          min="50"
                          max="300"
                          step="5"
                          value={defaultHomeLogoScale("mobile", defaultTheme, defaultVariant)}
                          oninput={defaultLogoScaleInputHandler("mobile")}
                        />
                        %
                      </span>
                    </div>
                  </section>
                </div>

                <div class="default-theme-token-grid">
                  {#each TOKEN_GROUPS as group (group.title)}
                    <section class="default-theme-panel">
                      <h4>
                        <svelte:component this={group.icon} size={15} />
                        {at(group.titleKey, {}, group.title)}
                      </h4>
                      <div class="appearance-token-list">
                        {#each group.items as item (item[0])}
                          {@const tokenKey = item[0]}
                          {@const tokenLabel = at(item[1], {}, item[2])}
                          <label
                            class="appearance-token-control"
                            class:is-dirty={isDefaultTokenDirty(tokenKey)}
                          >
                            <span>
                              {tokenLabel}
                              {#if isDefaultTokenDirty(tokenKey)}
                                <AdminBadge variant="warning"
                                  >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                                >
                              {/if}
                            </span>
                            <ColorInput
                              class="admin-color"
                              value={pickerHex(defaultTokenValue(tokenKey, defaultTokens))}
                              ariaLabel={tokenLabel}
                              onclick={() => openDefaultColorPicker(tokenKey)}
                              oninput={defaultColorInputHandler(tokenKey)}
                            />
                            <Input
                              class="input appearance-color-text"
                              type="text"
                              placeholder={at("appearance_token_empty", {}, "not set")}
                              value={tokenTextValue(tokenKey, defaultTokens)}
                              oninput={defaultTokenInputHandler(tokenKey)}
                            />
                            <AdminButton
                              class="appearance-token-reset"
                              size="sm"
                              variant="ghost"
                              onclick={() => resetDefaultToken(tokenKey)}
                            >
                              <RefreshCw size={12} />
                            </AdminButton>
                          </label>
                        {/each}
                      </div>
                    </section>
                  {/each}
                </div>
              </section>
            {:else}
              <AdminEmptyState>
                {at("themes_catalog_empty", {}, "Каталог тем пуст. Обновите список тем.")}
              </AdminEmptyState>
            {/if}
          </section>

          <section class="appearance-theme-section">
            <header class="appearance-theme-section-head">
              <div>
                <h4>{at("appearance_custom_themes_title", {}, "Пользовательские темы")}</h4>
                <small>
                  {at(
                    "appearance_custom_themes_sub",
                    {},
                    "Отдельные темы из каталога: выбор активной темы, акцент, логотип и применение в админке."
                  )}
                </small>
              </div>
              {#if customThemes.some((theme) => isThemeDirty(theme))}
                <AdminBadge variant="warning">
                  {at("settings_badge_dirty", {}, "Изменено")}
                </AdminBadge>
              {/if}
            </header>

            {#if customThemes.length}
              <div class="admin-theme-grid">
                {#each customThemes as theme (theme.key)}
                  {@const isCurrent = theme.key === activeKey}
                  <div
                    role="button"
                    tabindex={themesSaving ? -1 : 0}
                    class="admin-theme-card"
                    class:is-current={isCurrent}
                    class:is-disabled={theme.enabled === false}
                    class:is-dirty={isThemeDirty(theme)}
                    aria-pressed={isCurrent}
                    aria-disabled={themesSaving}
                    onclick={(event) => selectTheme(theme, event)}
                    onkeydown={(event) => handleThemeKeydown(event, theme)}
                  >
                    <span class="admin-theme-card-main">
                      <span class="admin-theme-card-title">
                        <strong>{themeTitle(theme)}</strong>
                        {#if isCurrent}
                          <AdminBadge variant="success"
                            >{at("status_current", {}, "Текущая")}</AdminBadge
                          >
                        {/if}
                      </span>
                      <small>{theme.key}</small>
                    </span>
                    <span class="admin-theme-card-meta">
                      <FileText size={15} />
                      <span>{themeDescription(theme)}</span>
                    </span>
                    <label
                      class="admin-theme-card-option appearance-color-row"
                      class:is-dirty={isThemeTokenDirty(theme, "accent")}
                    >
                      <span>
                        {at("appearance_theme_accent", {}, "Accent")}
                        {#if isThemeTokenDirty(theme, "accent")}
                          <AdminBadge variant="warning"
                            >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                          >
                        {/if}
                      </span>
                      <ColorInput
                        class={`admin-color${!isThemeAccentSet(theme) ? " is-empty" : ""}`}
                        value={pickerHex(theme.tokens?.accent)}
                        ariaLabel={at("appearance_theme_accent", {}, "Accent")}
                        title={isThemeAccentSet(theme)
                          ? String(theme.tokens?.accent ?? "")
                          : at("appearance_theme_accent_empty", {}, "Не задан")}
                        onclick={() => openThemeAccentPicker(theme)}
                        oninput={themeAccentInputHandler(theme)}
                      />
                      <Input
                        class="input appearance-color-text"
                        type="text"
                        placeholder={at("appearance_theme_accent_placeholder", {}, "Не задан")}
                        value={String(theme.tokens?.accent ?? "")}
                        oninput={themeAccentInputHandler(theme)}
                      />
                    </label>
                    <label
                      class="admin-theme-card-option"
                      class:is-dirty={isThemePropertyDirty(theme, "use_in_admin")}
                    >
                      <Checkbox
                        checked={theme.use_in_admin !== false}
                        disabled={themesSaving}
                        ariaLabel={at("themes_use_in_admin", {}, "Use in admin")}
                        onCheckedChange={(checked) => toggleAdminTheme(theme, checked)}
                      />
                      <span>
                        {at("themes_use_in_admin", {}, "Использовать в админке")}
                        {#if isThemePropertyDirty(theme, "use_in_admin")}
                          <AdminBadge variant="warning"
                            >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                          >
                        {/if}
                      </span>
                    </label>
                    <div
                      class="admin-theme-card-option appearance-logo-scale-row"
                      class:is-dirty={isThemeHomeLogoScaleDirty(theme, "desktop")}
                    >
                      <span class="appearance-logo-scale-label"
                        >{at("appearance_theme_home_logo_scale_desktop", {}, "Логотип на десктопе")}
                        {#if isThemeHomeLogoScaleDirty(theme, "desktop")}
                          <AdminBadge variant="warning"
                            >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                          >
                        {/if}
                      </span>
                      <RangeInput
                        class="appearance-logo-scale-range"
                        min="50"
                        max="300"
                        step="5"
                        ariaLabel={at(
                          "appearance_theme_home_logo_scale_desktop",
                          {},
                          "Desktop logo scale"
                        )}
                        value={homeLogoScale(theme, "desktop")}
                        onValueChange={themeLogoScaleSelectHandler(theme, "desktop")}
                      />
                      <span class="appearance-logo-scale-value">
                        <Input
                          class="input"
                          type="number"
                          min="50"
                          max="300"
                          step="5"
                          value={homeLogoScale(theme, "desktop")}
                          oninput={themeLogoScaleInputHandler(theme, "desktop")}
                        />
                        %
                      </span>
                    </div>
                    <div
                      class="admin-theme-card-option appearance-logo-scale-row"
                      class:is-dirty={isThemeHomeLogoScaleDirty(theme, "mobile")}
                    >
                      <span class="appearance-logo-scale-label"
                        >{at("appearance_theme_home_logo_scale_mobile", {}, "Логотип на мобильных")}
                        {#if isThemeHomeLogoScaleDirty(theme, "mobile")}
                          <AdminBadge variant="warning"
                            >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                          >
                        {/if}
                      </span>
                      <RangeInput
                        class="appearance-logo-scale-range"
                        min="50"
                        max="300"
                        step="5"
                        ariaLabel={at(
                          "appearance_theme_home_logo_scale_mobile",
                          {},
                          "Mobile logo scale"
                        )}
                        value={homeLogoScale(theme, "mobile")}
                        onValueChange={themeLogoScaleSelectHandler(theme, "mobile")}
                      />
                      <span class="appearance-logo-scale-value">
                        <Input
                          class="input"
                          type="number"
                          min="50"
                          max="300"
                          step="5"
                          value={homeLogoScale(theme, "mobile")}
                          oninput={themeLogoScaleInputHandler(theme, "mobile")}
                        />
                        %
                      </span>
                    </div>
                    <div class="appearance-theme-actions">
                      <AdminButton
                        size="sm"
                        variant="ghost"
                        onclick={previewThemeClickHandler(theme)}
                      >
                        <ExternalLink size={13} />
                        {at("appearance_preview_theme", {}, "Предпросмотр")}
                      </AdminButton>
                    </div>
                    <span class="admin-theme-card-check" aria-hidden="true">
                      {#if isCurrent}<Check size={18} />{/if}
                    </span>
                  </div>
                {/each}
              </div>
            {:else}
              <AdminEmptyState>
                {at(
                  "appearance_custom_themes_empty",
                  {},
                  "Пользовательских тем пока нет. Добавьте отдельную тему в каталог, если нужно выйти за рамки темы по-умолчанию."
                )}
              </AdminEmptyState>
            {/if}
          </section>
        {/if}
      </div>
    </article>
  </div>
{/if}

<style>
  .appearance-stack {
    display: grid;
    gap: 14px;
  }

  .appearance-logo-grid {
    display: grid;
    grid-template-columns: minmax(190px, 220px) minmax(0, 520px);
    gap: 18px;
    align-items: stretch;
  }

  .appearance-favicon-grid {
    grid-template-columns: minmax(132px, 140px) minmax(0, 520px);
    border-top: 1px solid var(--admin-border);
  }

  .appearance-logo-preview {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    grid-row: 1;
    width: auto;
    height: 100%;
    aspect-ratio: 1 / 1;
    justify-self: start;
    padding: 10px;
    overflow: hidden;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--admin-surface-2) 54%, var(--admin-surface));
  }

  .appearance-favicon-preview {
    width: 140px;
    height: 140px;
    max-width: 100%;
  }

  .appearance-logo-image {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }

  .appearance-logo-empty {
    width: 44%;
    aspect-ratio: 1 / 1;
    border: 1px dashed var(--admin-border-strong);
    border-radius: 8px;
    opacity: 0.65;
  }

  .appearance-logo-preview :global(.brand-mark) {
    width: 100%;
    height: 100%;
    font-size: clamp(3rem, 8vw, 5rem);
  }

  .appearance-controls {
    display: grid;
    gap: 12px;
    align-content: start;
    max-width: 520px;
  }

  .appearance-control-card {
    display: grid;
    gap: 10px;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--admin-surface-2) 40%, transparent);
  }

  :global(.appearance-file-input) {
    display: none;
  }

  .appearance-url-row {
    display: grid;
    gap: 8px;
    max-width: 520px;
    grid-template-columns: minmax(0, 1fr) max-content;
    width: 100%;
  }

  :global(.appearance-control.input),
  :global(.appearance-control.admin-btn),
  :global(.appearance-control.admin-select-trigger) {
    height: 36px;
    min-height: 36px;
  }

  :global(.appearance-control.admin-btn) {
    padding-inline: 12px;
    border-radius: 8px;
    font-size: 13px;
  }

  .appearance-switch {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    width: fit-content;
    max-width: 520px;
    color: var(--admin-text);
    font-size: 13px;
  }

  .appearance-themes-body {
    display: grid;
    gap: 14px;
  }

  .appearance-theme-section {
    display: grid;
    gap: 12px;
    min-width: 0;
  }

  .appearance-theme-section + .appearance-theme-section {
    padding-top: 14px;
    border-top: 1px solid var(--admin-border);
  }

  .appearance-theme-section-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }

  .appearance-theme-section-head h4 {
    margin: 0;
    color: var(--admin-text);
    font-size: 14px;
    line-height: 1.2;
  }

  .appearance-theme-section-head small {
    display: block;
    margin-top: 4px;
    color: var(--admin-muted);
    font-size: 12px;
  }

  .default-theme-editor {
    position: relative;
    display: grid;
    gap: 14px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: color-mix(in srgb, var(--admin-surface-2) 34%, transparent);
    color: var(--admin-text);
    cursor: pointer;
    padding: 14px;
  }

  .default-theme-editor:hover {
    border-color: var(--admin-border-strong);
    background: color-mix(in srgb, var(--admin-surface-2) 58%, transparent);
  }

  .default-theme-editor:focus-visible {
    outline: 2px solid color-mix(in srgb, var(--accent) 70%, transparent);
    outline-offset: 2px;
  }

  .default-theme-editor.is-current {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 4%, var(--admin-surface-2));
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 44%, transparent);
  }

  .default-theme-editor.is-dirty {
    border-color: color-mix(in srgb, var(--warning, #f5b84b) 42%, var(--admin-border));
    background: color-mix(in srgb, var(--warning, #f5b84b) 5%, var(--admin-surface-2));
  }

  .default-theme-editor.is-disabled {
    cursor: default;
    opacity: 0.58;
  }

  .default-theme-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }

  .default-theme-title {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    color: var(--admin-text);
  }

  .default-theme-title strong {
    font-size: 15px;
    line-height: 1.2;
  }

  .default-theme-check {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 999px;
    color: var(--accent);
  }

  .default-theme-head small {
    display: block;
    margin-top: 5px;
    color: var(--admin-muted);
    font-size: 12px;
  }

  .default-theme-actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
  }

  .appearance-mode-switch {
    min-height: 32px;
    padding: 4px 8px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: var(--admin-surface);
  }

  .appearance-preset-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .appearance-preset-btn {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    min-height: 32px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: var(--admin-surface);
    color: var(--admin-text);
    padding: 0 10px;
    font-size: 12px;
    font-weight: 750;
  }

  .appearance-preset-btn:hover {
    border-color: var(--admin-border-strong);
    background: var(--surface-hover);
  }

  .appearance-preset-btn span {
    width: 14px;
    height: 14px;
    border: 1px solid var(--admin-border-strong);
    border-radius: 999px;
  }

  .default-theme-grid,
  .default-theme-token-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .default-theme-token-grid {
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }

  .default-theme-panel {
    display: grid;
    align-content: start;
    gap: 11px;
    min-width: 0;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: var(--admin-surface);
    padding: 12px;
  }

  .default-theme-panel h4 {
    display: flex;
    align-items: center;
    gap: 7px;
    margin: 0;
    color: var(--admin-text);
    font-size: 13px;
    line-height: 1.2;
  }

  .appearance-select-grid {
    display: grid;
    gap: 8px;
  }

  .appearance-select-grid label {
    display: grid;
    gap: 5px;
    min-width: 0;
    color: var(--admin-muted);
    font-size: 12px;
  }

  .appearance-select-grid label > span,
  .appearance-token-control > span,
  .appearance-logo-scale-label,
  .admin-theme-card-option > span {
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
  }

  .appearance-select-grid label.is-dirty,
  .appearance-token-control.is-dirty,
  .appearance-logo-scale-row.is-dirty,
  .admin-theme-card-option.is-dirty {
    color: color-mix(in srgb, var(--warning, #f5b84b) 78%, var(--admin-text));
  }

  .appearance-custom-font-row {
    display: grid;
    grid-template-columns: minmax(180px, 1fr) repeat(3, max-content);
    gap: 8px;
    align-items: center;
  }

  .appearance-custom-font-row :global(.admin-btn) {
    min-height: 34px;
    padding-inline: 10px;
  }

  :global(.appearance-select) {
    width: 100%;
    min-height: 34px;
  }

  .appearance-token-list {
    display: grid;
    gap: 8px;
  }

  .appearance-token-control {
    display: grid;
    grid-template-columns: minmax(92px, 0.62fr) 38px minmax(0, 1fr) 32px;
    align-items: center;
    gap: 8px;
    min-width: 0;
    color: var(--admin-muted);
    font-size: 12px;
  }

  .appearance-token-control > span {
    min-width: 0;
    line-height: 1.25;
  }

  :global(.appearance-token-reset.admin-btn) {
    min-width: 32px;
    width: 32px;
    height: 32px;
    min-height: 32px;
    padding: 0;
  }

  .appearance-default-scale-row {
    grid-template-columns: minmax(96px, 0.75fr) minmax(110px, 1fr) auto;
  }

  .admin-theme-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 12px;
  }

  .admin-theme-card {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
    min-height: 154px;
    padding: 14px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    background: var(--admin-surface);
    color: var(--admin-text);
    text-align: left;
    cursor: pointer;
  }

  .admin-theme-card:hover {
    border-color: var(--admin-border-strong);
    background: color-mix(in srgb, var(--admin-surface-2) 72%, var(--admin-surface));
  }

  .admin-theme-card.is-current {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 44%, transparent);
  }

  .admin-theme-card.is-dirty {
    border-color: color-mix(in srgb, var(--warning, #f5b84b) 42%, var(--admin-border));
  }

  .admin-theme-card.is-disabled {
    opacity: 0.58;
  }

  .admin-theme-card-main {
    display: grid;
    align-content: start;
    gap: 5px;
    min-width: 0;
  }

  .admin-theme-card-title {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .admin-theme-card-title strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-theme-card-main small,
  .admin-theme-card-meta {
    color: var(--admin-muted);
    font-size: 12px;
  }

  .admin-theme-card-meta {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
  }

  .admin-theme-card-meta span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-theme-card-option {
    grid-column: 1 / -1;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    max-width: 100%;
    color: var(--admin-muted);
    font-size: 12px;
    cursor: default;
  }

  .appearance-color-row {
    display: grid;
    grid-template-columns: auto 38px minmax(0, 1fr);
    width: 100%;
  }

  :global(.appearance-color-text) {
    min-width: 0;
  }

  .appearance-logo-scale-row {
    display: grid;
    grid-template-columns: minmax(112px, 0.8fr) minmax(96px, 1fr) auto;
    width: 100%;
  }

  .appearance-logo-scale-label {
    min-width: 0;
    line-height: 1.25;
  }

  :global(.appearance-logo-scale-range) {
    width: 100%;
    accent-color: var(--accent);
  }

  .appearance-logo-scale-value {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--admin-text);
  }

  :global(.appearance-logo-scale-value .input) {
    width: 70px;
    min-height: 32px;
    padding: 4px 8px;
    font-size: 12px;
  }

  :global(.admin-color.is-empty) {
    opacity: 0.42;
    filter: grayscale(1);
  }

  .appearance-theme-actions {
    grid-column: 1 / -1;
    display: flex;
    justify-content: flex-start;
  }

  .admin-theme-card-check {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 999px;
    color: var(--accent);
  }

  @media (max-width: 720px) {
    .appearance-logo-grid {
      grid-template-columns: 1fr;
    }

    .appearance-logo-preview {
      grid-row: auto;
      height: auto;
      width: min(164px, 100%);
    }

    .appearance-favicon-preview {
      width: min(140px, 100%);
      height: auto;
    }

    .appearance-url-row {
      grid-template-columns: 1fr;
    }

    .appearance-logo-scale-row {
      grid-template-columns: minmax(0, 1fr) auto;
    }

    :global(.appearance-logo-scale-range) {
      grid-column: 1 / -1;
    }

    .default-theme-head {
      display: grid;
    }

    .default-theme-actions {
      justify-content: flex-start;
    }

    .default-theme-grid,
    .default-theme-token-grid {
      grid-template-columns: 1fr;
    }

    .appearance-theme-section-head {
      display: grid;
    }

    .appearance-custom-font-row {
      grid-template-columns: 1fr;
    }

    .appearance-token-control {
      grid-template-columns: minmax(0, 1fr) 38px 32px;
    }

    :global(.appearance-token-control .appearance-color-text) {
      grid-column: 1 / -1;
    }
  }
</style>
