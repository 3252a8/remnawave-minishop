<script lang="ts">
  import { FileText, RefreshCw, Save } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { FileInput, Input } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { getContext, onDestroy, onMount } from "svelte";

  import {
    firstFontFamily,
    localizedThemeName,
    writeThemePreviewDraft,
  } from "$lib/webapp/themeStyle.js";
  import {
    DEFAULT_THEME_KEY,
    DEFAULT_THEME_VARIANTS,
    VARIANT_LABELS,
    googleMonoFontStack,
    googleSansFontStack,
  } from "$lib/admin/appearanceOptions";
  import type {
    BrandInfo,
    FontOption,
    LogoMode,
    ThemeCatalog,
    ThemeEntry,
    ThemeVariant,
    TokenMap,
  } from "$lib/admin/appearanceOptions";
  import "./AppearanceSection.css";
  import AppearanceDefaultThemeEditor from "./appearance/AppearanceDefaultThemeEditor.svelte";
  import AppearanceCustomThemes from "./appearance/AppearanceCustomThemes.svelte";
  import type {
    SettingField,
    SettingsDirtyEntry,
    SettingsSavedPayload,
    SettingsSection,
    SettingsStore,
  } from "$lib/admin/stores/settingsStore";
  import type { ThemesStore } from "$lib/admin/stores/themesStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SettingsDirtyState = Record<string, SettingsDirtyEntry>;
  type SelectCallback = (...args: never[]) => void;

  let {
    at,
    currentLang = "ru",
    onSettingsSaved = () => {},
    brand = {},
    appFaviconUrl = "",
    appFaviconUseCustom = false,
  }: {
    at: TranslateFn;
    currentLang?: string;
    onSettingsSaved?: (payload: SettingsSavedPayload) => void | Promise<void>;
    brand?: BrandInfo;
    appFaviconUrl?: string;
    appFaviconUseCustom?: boolean;
  } = $props();

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
  let logoFileInput = $state<HTMLInputElement | null>(null);
  let faviconFileInput = $state<HTMLInputElement | null>(null);
  let customGoogleFontName = $state("");
  let logoSourceUrl = $state("");
  let faviconSourceUrl = $state("");
  let logoPreviewNonce = $state(0);
  let faviconPreviewNonce = $state(0);
  let logoPreviewFailed = $state(false);
  let faviconPreviewFailed = $state(false);
  let lastPreviewLogoUrl = $state("");
  let lastPreviewFaviconUrl = $state("");
  let lastPersistedUseCustomFavicon = $state<boolean | undefined>();
  let faviconUseCustomDraft = $state(false);
  let pendingLogoPreviewUrl = $state("");
  let pendingFaviconPreviewUrl = $state("");
  let pendingObjectUrl = $state("");
  let pendingFaviconObjectUrl = $state("");

  const settingsSections = $derived(settingsStore.settingsSections);
  const settingsLoading = $derived(settingsStore.settingsLoading);
  const settingsDirty: SettingsDirtyState = $derived(settingsStore.settingsDirty);
  const settingsSaving = $derived(settingsStore.settingsSaving);
  const themesCatalog: ThemeCatalog = $derived(themesStore.themesCatalog);
  const savedThemesCatalog: ThemeCatalog = $derived(themesStore.savedThemesCatalog);
  const themesLoading = $derived(themesStore.themesLoading);
  const themesDir = $derived(themesStore.themesDir);
  const themesSaving = $derived(themesStore.themesSaving);
  const themesDirty = $derived(themesStore.themesDirty);
  const appearanceFields: SettingField[] = $derived(
    settingsSections.find((section: SettingsSection) => section.id === "appearance")?.fields || []
  );
  const fieldMap = $derived(new Map(appearanceFields.map((field) => [field.key, field])));
  const activeKey = $derived(themesCatalog.default_theme);
  const logoUrl = $derived(stringValueForKey("WEBAPP_LOGO_URL"));
  const currentLogoUrl = $derived(pendingLogoPreviewUrl || logoUrl || brand?.logoUrl || "");
  const previewLogoUrl = $derived(
    logoPreviewNonce && currentLogoUrl ? withLogoCacheBust(currentLogoUrl) : currentLogoUrl
  );
  const persistedUseCustomFavicon = $derived(
    boolValue(valueForKey("WEBAPP_FAVICON_USE_CUSTOM", appFaviconUseCustom))
  );
  const useCustomFavicon = $derived(faviconUseCustomDraft);
  const faviconUrl = $derived(stringValueForKey("WEBAPP_FAVICON_URL", appFaviconUrl));
  const logoFaviconUrl = $derived(stringValueForKey("WEBAPP_LOGO_FAVICON_URL"));
  const generatedFaviconUrl = $derived(logoFaviconUrl || appFaviconUrl || previewLogoUrl || "");
  const currentFaviconUrl = $derived(
    useCustomFavicon ? pendingFaviconPreviewUrl || faviconUrl || "" : generatedFaviconUrl
  );
  const previewFaviconUrl = $derived(
    faviconPreviewNonce && currentFaviconUrl
      ? withCacheBust(currentFaviconUrl, faviconPreviewNonce)
      : currentFaviconUrl
  );
  const dirtyCount = $derived(
    Object.keys(settingsDirty || {}).filter((key) => isAppearanceSettingKey(key)).length
  );
  const appearanceDirtyCount = $derived(dirtyCount + (themesDirty ? 1 : 0));
  const appearanceDirtyKeys = $derived(
    Object.keys(settingsDirty || {}).filter((key) => isAppearanceSettingKey(key))
  );
  const defaultTheme: ThemeEntry | undefined = $derived(
    (themesCatalog.themes || []).find((theme) => theme.key === DEFAULT_THEME_KEY)
  );
  const defaultVariant: ThemeVariant = $derived(
    normalizeVariant(defaultTheme?.active_variant || defaultTheme?.tokens?.color_scheme)
  );
  const defaultTokens: TokenMap = $derived(
    defaultTheme ? themesStore.resolveThemeTokens(defaultTheme, defaultVariant) : {}
  );
  const visibleThemes: ThemeEntry[] = $derived(
    (themesCatalog.themes || []).filter((theme) => !theme.hidden && !theme.variant_alias_for)
  );
  const customThemes: ThemeEntry[] = $derived(
    visibleThemes.filter((theme) => theme.key !== DEFAULT_THEME_KEY)
  );
  const defaultThemeIsCurrent = $derived(activeKey === DEFAULT_THEME_KEY);

  $effect.pre(() => {
    if (
      !Object.prototype.hasOwnProperty.call(settingsDirty, "WEBAPP_FAVICON_USE_CUSTOM") &&
      lastPersistedUseCustomFavicon !== persistedUseCustomFavicon
    ) {
      faviconUseCustomDraft = persistedUseCustomFavicon;
      lastPersistedUseCustomFavicon = persistedUseCustomFavicon;
    }
  });

  $effect(() => {
    if (previewLogoUrl !== lastPreviewLogoUrl) {
      lastPreviewLogoUrl = previewLogoUrl;
      logoPreviewFailed = false;
    }
  });

  $effect(() => {
    if (previewFaviconUrl !== lastPreviewFaviconUrl) {
      lastPreviewFaviconUrl = previewFaviconUrl;
      faviconPreviewFailed = false;
    }
  });

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
          <AppearanceDefaultThemeEditor
            {at}
            {defaultTheme}
            {defaultVariant}
            {defaultThemeIsCurrent}
            {themesSaving}
            {defaultTokens}
            bind:customGoogleFontName
            {isThemeDirty}
            {isDefaultVariantDirty}
            {defaultVariantTitle}
            {themeDescription}
            {selectDefaultTheme}
            {handleDefaultThemeKeydown}
            {activateDefaultThemeFromClick}
            {setDefaultVariantFromSwitch}
            {previewDefaultVariantFromClick}
            {applyDefaultPreset}
            {isDefaultTokenDirty}
            {tokenTextValue}
            {fontItemsWithCurrent}
            {defaultFontSelectHandler}
            {applyCustomGoogleFont}
            {radiusNumber}
            {defaultRadiusRangeHandler}
            {defaultRadiusInputHandler}
            {isThemeHomeLogoScaleDirty}
            {defaultHomeLogoScale}
            {defaultLogoScaleSelectHandler}
            {defaultLogoScaleInputHandler}
            {defaultTokenValue}
            {pickerHex}
            {openDefaultColorPicker}
            {defaultColorInputHandler}
            {defaultTokenInputHandler}
            {resetDefaultToken}
          />

          <AppearanceCustomThemes
            {at}
            {customThemes}
            {activeKey}
            {themesSaving}
            {isThemeDirty}
            {themeTitle}
            {themeDescription}
            {isThemeTokenDirty}
            {isThemeAccentSet}
            {pickerHex}
            {openThemeAccentPicker}
            {themeAccentInputHandler}
            {isThemePropertyDirty}
            {toggleAdminTheme}
            {isThemeHomeLogoScaleDirty}
            {homeLogoScale}
            {themeLogoScaleSelectHandler}
            {themeLogoScaleInputHandler}
            {previewThemeClickHandler}
            {selectTheme}
            {handleThemeKeydown}
          />
        {/if}
      </div>
    </article>
  </div>
{/if}
