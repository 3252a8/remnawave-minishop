<script lang="ts">
  import { getSettingsStore, getThemesStore } from "$lib/admin/context";
  import { AdminEmptyState } from "$components/patterns/admin/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { onMount } from "svelte";
  import { captureThemePreview } from "$lib/admin/captureThemePreview";

  import {
    firstFontFamily,
    localizedThemeName,
    writeThemePreviewDraft,
  } from "$lib/webapp/themeStyle";
  import {
    DEFAULT_THEME_KEY,
    DEFAULT_THEME_VARIANTS,
    appearanceColorVariables,
    appearanceThemeTokenValue,
    googleMonoFontStack,
    googleSansFontStack,
    resolveAppearanceColor,
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
  import AppearanceLibrary from "./appearance/AppearanceLibrary.svelte";
  import AppearanceBrandCard from "./appearance/AppearanceBrandCard.svelte";
  import AppearanceDefaultThemeEditor from "./appearance/AppearanceDefaultThemeEditor.svelte";
  import AppearanceCustomThemes from "./appearance/AppearanceCustomThemes.svelte";
  import type {
    SettingField,
    SettingsDirtyEntry,
    SettingsSavedPayload,
    SettingsSection,
  } from "$lib/admin/stores/settingsStore";

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

  const settingsStore = getSettingsStore();
  const themesStore = getThemesStore();
  const APPEARANCE_SETTING_KEYS = new Set([
    "SUBSCRIPTION_MINI_APP_URL",
    "WEBAPP_PRIMARY_COLOR",
    "WEBAPP_USER_THEME_MODE_ENABLED",
    "WEBAPP_COMPACT_HOME_ENABLED",
    "WEBAPP_LOGO_URL",
    "WEBAPP_FAVICON_URL",
    "WEBAPP_FAVICON_USE_CUSTOM",
    "WEBAPP_LOGO_FAVICON_URL",
    "WEBAPP_ENABLED",
  ]);
  let customGoogleFontName = $state("");
  let defaultEditorVariant = $state<ThemeVariant>("dark");

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
  const activeKey = $derived(themesCatalog.default_theme);
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
  $effect(() => {
    defaultEditorVariant = defaultVariant;
  });
  const defaultTokens: TokenMap = $derived(
    defaultTheme ? themesStore.resolveThemeTokens(defaultTheme, defaultEditorVariant) : {}
  );
  const visibleThemes: ThemeEntry[] = $derived(
    (themesCatalog.themes || []).filter((theme) => !theme.hidden && !theme.variant_alias_for)
  );
  const customThemes: ThemeEntry[] = $derived(
    visibleThemes.filter((theme) => theme.key !== DEFAULT_THEME_KEY)
  );
  const defaultThemeIsCurrent = $derived(activeKey === DEFAULT_THEME_KEY);
  const userThemeModeEnabled = $derived(
    boolAppearanceSettingValue("WEBAPP_USER_THEME_MODE_ENABLED", true)
  );
  const compactHomeEnabled = $derived(
    boolAppearanceSettingValue("WEBAPP_COMPACT_HOME_ENABLED", false)
  );

  function isAppearanceSettingKey(key: string): boolean {
    return APPEARANCE_SETTING_KEYS.has(key) || appearanceFields.some((field) => field.key === key);
  }

  function appearanceSettingValue(key: string, fallback: unknown): unknown {
    const dirty = settingsDirty[key];
    if (dirty?.deleted) return fallback;
    if (Object.prototype.hasOwnProperty.call(settingsDirty, key)) return dirty.value;
    return appearanceFields.find((field) => field.key === key)?.value ?? fallback;
  }

  function boolAppearanceSettingValue(key: string, fallback: boolean): boolean {
    const value = appearanceSettingValue(key, fallback);
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  }

  function setUserThemeModeEnabled(enabled: boolean): void {
    settingsStore.markDirty("WEBAPP_USER_THEME_MODE_ENABLED", Boolean(enabled));
  }

  function setCompactHomeEnabled(enabled: boolean): void {
    settingsStore.markDirty("WEBAPP_COMPACT_HOME_ENABLED", Boolean(enabled));
  }

  function themeTitle(theme: ThemeEntry): string {
    return localizedThemeName(theme, currentLang) || "—";
  }

  function themeDescription(theme: ThemeEntry): string {
    const folder = `${themesDir || "data/themes"}/${theme.key}`;
    return theme.css_file ? `${folder}/${theme.css_file}` : `${folder}/theme.json`;
  }

  function pickerHex(value: unknown, tokens: TokenMap = defaultTokens): string | null {
    return resolveAppearanceColor(value, appearanceColorVariables({}, tokens));
  }

  function normalizeVariant(variant: unknown): ThemeVariant {
    return String(variant || "")
      .trim()
      .toLowerCase() === "light"
      ? "light"
      : "dark";
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
    return themesStore.resolveThemeTokens(theme, variant || theme.active_variant)?.[tokenKey] ?? "";
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

  function isDefaultTokenDirty(tokenKey: string, variant: ThemeVariant = defaultEditorVariant): boolean {
    return isThemeTokenDirty(defaultTheme, tokenKey, variant);
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

  function customThemeTokens(theme: ThemeEntry, variant: ThemeVariant = themeVariant(theme)): TokenMap {
    return themesStore.resolveThemeTokens(theme, variant);
  }

  function customThemeTokenValue(theme: ThemeEntry, tokenKey: string, variant = themeVariant(theme)): unknown {
    const value = appearanceThemeTokenValue(
      theme,
      customThemeTokens(theme, variant),
      tokenKey,
      themeCssVariables(theme, variant)
    );
    if (tokenKey === "accent" && (value == null || value === "") && theme.use_primary_accent !== false) {
      return appearanceSettingValue("WEBAPP_PRIMARY_COLOR", "#00fe7a") || "#00fe7a";
    }
    return value;
  }

  function customThemeTokenText(theme: ThemeEntry, tokenKey: string, variant = themeVariant(theme)): string {
    const value = customThemeTokenValue(theme, tokenKey, variant);
    return value == null ? "" : String(value);
  }

  function setCustomThemeToken(theme: ThemeEntry, tokenKey: string, value: unknown, variant = themeVariant(theme)): void {
    themesStore.setThemeToken(theme.key, tokenKey, value, { variant });
  }

  function resetCustomThemeToken(theme: ThemeEntry, tokenKey: string, variant = themeVariant(theme)): void {
    themesStore.resetThemeToken(theme.key, tokenKey, { variant });
  }

  function setCustomThemeFont(theme: ThemeEntry, tokenKey: string, value: unknown): void {
    for (const variant of DEFAULT_THEME_VARIANTS) {
      themesStore.setThemeToken(theme.key, tokenKey, value, { variant });
    }
  }

  function applyCustomThemeGoogleFont(
    theme: ThemeEntry,
    tokenKey: string,
    kind: "sans" | "mono" = "sans"
  ): void {
    const stack = customGoogleFontStack(kind);
    if (stack) setCustomThemeFont(theme, tokenKey, stack);
  }

  function setCustomThemeRadius(theme: ThemeEntry, value: unknown, variant = themeVariant(theme)): void {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    setCustomThemeToken(theme, "radius", `${Math.min(28, Math.max(0, Math.round(numeric)))}px`, variant);
  }

  function customThemeRadiusNumber(theme: ThemeEntry, variant = themeVariant(theme)): number {
    const match = String(customThemeTokenValue(theme, "radius", variant) || "").match(/(\d+)/);
    return match ? Math.min(28, Math.max(0, Number(match[1]))) : 8;
  }

  function setCustomThemeTransparency(
    theme: ThemeEntry,
    value: unknown,
    variant = themeVariant(theme)
  ): void {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    setCustomThemeToken(theme, "transparency", Math.min(100, Math.max(0, Math.round(numeric))), variant);
  }

  function customThemeTransparencyNumber(theme: ThemeEntry, variant = themeVariant(theme)): number {
    const numeric = Number(customThemeTokenValue(theme, "transparency", variant));
    return Number.isFinite(numeric) ? Math.min(100, Math.max(0, Math.round(numeric))) : 100;
  }

  function applyCustomThemePreset(
    theme: ThemeEntry,
    preset: { tokens?: TokenMap } | null | undefined,
    variant = themeVariant(theme)
  ): void {
    if (preset?.tokens) themesStore.applyThemePreset(theme.key, variant, preset.tokens);
  }

  function themeVariant(theme: ThemeEntry): ThemeVariant {
    return normalizeVariant(theme.active_variant || theme.tokens?.color_scheme);
  }

  function setDefaultVariant(variant: ThemeVariant): void {
    themesStore.setDefaultThemeVariant(variant);
  }

  function setCustomThemeVariant(theme: ThemeEntry, variant: ThemeVariant): void {
    themesStore.setThemeVariant(theme.key, variant);
  }

  function setDefaultToken(tokenKey: string, value: unknown, variant: ThemeVariant = defaultEditorVariant): void {
    themesStore.setThemeToken(DEFAULT_THEME_KEY, tokenKey, value, { variant });
  }

  function resetDefaultToken(tokenKey: string, variant: ThemeVariant = defaultEditorVariant): void {
    themesStore.resetThemeToken(DEFAULT_THEME_KEY, tokenKey, { variant });
  }

  function setDefaultColorToken(tokenKey: string, value: unknown, variant: ThemeVariant = defaultEditorVariant): void {
    setDefaultToken(tokenKey, value, variant);
  }

  function openDefaultColorPicker(_tokenKey: string, _fallback = "#00fe7a"): void {
    // The shared picker opens itself; writing here would replace an unresolved CSS expression.
  }

  function setDefaultRadius(value: unknown, variant: ThemeVariant = defaultEditorVariant): void {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    setDefaultToken("radius", `${Math.min(28, Math.max(4, Math.round(numeric)))}px`, variant);
  }

  function setDefaultTransparency(
    value: unknown,
    variant: ThemeVariant = defaultEditorVariant
  ): void {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return;
    setDefaultToken(
      "transparency",
      Math.min(100, Math.max(0, Math.round(numeric))),
      variant
    );
  }

  const defaultRadiusRangeHandler = ((value: number, variant?: ThemeVariant) =>
    setDefaultRadius(value, variant)) as SelectCallback;
  const defaultTransparencyRangeHandler = ((value: number, variant?: ThemeVariant) =>
    setDefaultTransparency(value, variant)) as SelectCallback;

  function radiusNumber(tokens: TokenMap = defaultTokens): number {
    const match = String(defaultTokenValue("radius", tokens) || "").match(/(\d+)/);
    return match ? Math.min(28, Math.max(4, Number(match[1]))) : 8;
  }

  function transparencyNumber(tokens: TokenMap = defaultTokens): number {
    const numeric = Number(tokens.transparency);
    return Number.isFinite(numeric) ? Math.min(100, Math.max(0, Math.round(numeric))) : 100;
  }

  function setDefaultFont(tokenKey: string, value: unknown): void {
    for (const variant of DEFAULT_THEME_VARIANTS) {
      themesStore.setThemeToken(DEFAULT_THEME_KEY, tokenKey, value, { variant });
    }
  }

  function applyDefaultPreset(preset: { tokens?: TokenMap } | null | undefined, variant: ThemeVariant = defaultEditorVariant): void {
    if (!preset?.tokens) return;
    themesStore.applyThemePreset(DEFAULT_THEME_KEY, variant, preset.tokens);
  }

  function defaultHomeLogoScale(
    mode: LogoMode,
    theme: ThemeEntry | null | undefined = defaultTheme,
    variant: string | null = defaultVariant
  ): number {
    return themesStore.resolveThemeHomeLogoScale(theme, mode, variant);
  }

  function setDefaultHomeLogoScale(mode: LogoMode, value: unknown, variant: ThemeVariant = defaultEditorVariant): void {
    themesStore.setThemeHomeLogoScale(DEFAULT_THEME_KEY, mode, value, variant);
  }

  function homeLogoScale(theme: ThemeEntry, mode: LogoMode): number {
    return Number(themesStore.resolveThemeHomeLogoScale(theme, mode, themeVariant(theme))) || 0;
  }

  function defaultFontSelectHandler(tokenKey: string): (value: string) => void {
    return (value: string) => setDefaultFont(tokenKey, value);
  }

  function defaultLogoScaleSelectHandler(mode: LogoMode, variant: ThemeVariant = defaultEditorVariant): SelectCallback {
    return ((value: number) => setDefaultHomeLogoScale(mode, value, variant)) as SelectCallback;
  }

  function themeLogoScaleSelectHandler(theme: ThemeEntry, mode: LogoMode, variant = themeVariant(theme)): SelectCallback {
    return ((value: number) => setThemeHomeLogoScale(theme, mode, value, variant)) as SelectCallback;
  }

  function defaultRadiusInputHandler(event: Event, variant?: ThemeVariant): void {
    setDefaultRadius(inputValue(event), variant);
  }

  function defaultTransparencyInputHandler(event: Event, variant?: ThemeVariant): void {
    setDefaultTransparency(inputValue(event), variant);
  }

  function defaultLogoScaleInputHandler(mode: LogoMode, variant: ThemeVariant = defaultEditorVariant): (event: Event) => void {
    return (event) => setDefaultHomeLogoScale(mode, inputValue(event), variant);
  }

  function themeLogoScaleInputHandler(theme: ThemeEntry, mode: LogoMode, variant = themeVariant(theme)): (event: Event) => void {
    return (event) => setThemeHomeLogoScale(theme, mode, inputValue(event), variant);
  }

  function defaultTokenInputHandler(tokenKey: string, variant: ThemeVariant = defaultEditorVariant): (event: Event) => void {
    return (event) => setDefaultToken(tokenKey, inputValue(event), variant);
  }

  function defaultColorInputHandler(tokenKey: string, variant: ThemeVariant = defaultEditorVariant): (event: Event) => void {
    return (event) => setDefaultColorToken(tokenKey, inputValue(event), variant);
  }

  async function saveAppearance(): Promise<void> {
    const keysToSave = new Set(appearanceDirtyKeys);
    const shouldReloadFrontend = Array.from(keysToSave).some((key) =>
      [
        "WEBAPP_LOGO_URL",
        "WEBAPP_USER_THEME_MODE_ENABLED",
        "WEBAPP_COMPACT_HOME_ENABLED",
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

  function themeCssVariables(
    theme: ThemeEntry,
    variant: ThemeVariant = themeVariant(theme)
  ): Record<string, string> {
    const variables = theme.css_variables_by_variant?.[variant] ?? theme.css_variables;
    return variables && typeof variables === "object"
      ? Object.fromEntries(
          Object.entries(variables).filter(
            ([key, value]) => key.startsWith("--") && typeof value === "string"
          )
        )
      : {};
  }

  function themeCssVariableValue(theme: ThemeEntry, key: string, variant = themeVariant(theme)): string {
    const override = customThemeTokens(theme, variant)[key];
    return override == null || override === "" ? themeCssVariables(theme, variant)[key] || "" : String(override);
  }

  function customThemePickerHex(theme: ThemeEntry, value: unknown, variant = themeVariant(theme)): string | null {
    return resolveAppearanceColor(
      value,
      appearanceColorVariables(themeCssVariables(theme, variant), customThemeTokens(theme, variant))
    );
  }

  function themeCssPickerHex(theme: ThemeEntry, key: string, variant = themeVariant(theme)): string | null {
    return resolveAppearanceColor(
      themeCssVariableValue(theme, key, variant),
      appearanceColorVariables(themeCssVariables(theme, variant), customThemeTokens(theme, variant))
    );
  }

  function themeCssVariableInputHandler(theme: ThemeEntry, key: string, variant = themeVariant(theme)): (event: Event) => void {
    return (event) =>
      themesStore.setThemeToken(theme.key, key, inputValue(event), { variant });
  }

  function setThemeHomeLogoScale(theme: ThemeEntry, mode: LogoMode, value: unknown, variant = themeVariant(theme)): void {
    themesStore.setThemeHomeLogoScale(theme.key, mode, value, variant);
  }

  function activateThemeFromClick(theme: ThemeEntry, event: MouseEvent): void {
    event.stopPropagation();
    if (!themesSaving) themesStore.setCurrentTheme(theme.key);
  }

  function activateDefaultTheme(): void {
    if (!themesSaving) themesStore.setCurrentTheme(DEFAULT_THEME_KEY);
  }

  function activateDefaultThemeFromClick(event: MouseEvent): void {
    event.stopPropagation();
    activateDefaultTheme();
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

  async function captureTheme(theme: ThemeEntry): Promise<void> {
    writeThemePreviewDraft(clonePreviewCatalog(), theme.key);
    const image = await captureThemePreview(themePreviewUrl(theme.key));
    await themesStore.library.uploadPreview(theme.key, image);
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
</script>

{#snippet brandEditor()}
  <AppearanceBrandCard
    {at}
    {brand}
    {appFaviconUrl}
    {appFaviconUseCustom}
    {appearanceDirtyCount}
    {settingsSaving}
    {themesSaving}
    onSave={saveAppearance}
  />
{/snippet}

{#snippet defaultEditor()}
  <AppearanceDefaultThemeEditor
    {at}
    {defaultTheme}
    {defaultVariant}
    selectedVariant={defaultEditorVariant}
    onVariantChange={(variant) => (defaultEditorVariant = variant)}
    {defaultThemeIsCurrent}
    {themesSaving}
    {defaultTokens}
    bind:customGoogleFontName
    {isThemeDirty}
    {isDefaultVariantDirty}
    {themeDescription}
    {activateDefaultThemeFromClick}
    {previewDefaultVariantFromClick}
    {applyDefaultPreset}
    {isDefaultTokenDirty}
    {tokenTextValue}
    {fontItemsWithCurrent}
    {defaultFontSelectHandler}
    {applyCustomGoogleFont}
    {radiusNumber}
    {transparencyNumber}
    {defaultRadiusRangeHandler}
    {defaultRadiusInputHandler}
    {defaultTransparencyRangeHandler}
    {defaultTransparencyInputHandler}
    {isThemeHomeLogoScaleDirty}
    {defaultHomeLogoScale}
    {defaultLogoScaleSelectHandler}
    {defaultLogoScaleInputHandler}
    {defaultTokenValue}
    {pickerHex}
    {customThemePickerHex}
    {openDefaultColorPicker}
    {defaultColorInputHandler}
    {defaultTokenInputHandler}
    {resetDefaultToken}
  />
{/snippet}

{#snippet customEditor(themeKey: string)}
  <AppearanceCustomThemes
    {at}
    customThemes={customThemes.filter((theme) => !themeKey || theme.key === themeKey)}
    {activeKey}
    {themesSaving}
    bind:customGoogleFontName
    {isThemeDirty}
    {themeTitle}
    {themeDescription}
    {themeVariant}
    {customThemeTokens}
    {activateThemeFromClick}
    {applyCustomThemePreset}
    {isThemeTokenDirty}
    {customThemeTokenText}
    {fontItemsWithCurrent}
    {setCustomThemeFont}
    {applyCustomThemeGoogleFont}
    {customThemeRadiusNumber}
    {customThemeTransparencyNumber}
    {setCustomThemeRadius}
    {setCustomThemeTransparency}
    {customThemePickerHex}
    {themeCssPickerHex}
    {customThemeTokenValue}
    {setCustomThemeToken}
    {resetCustomThemeToken}
    {themeCssVariables}
    {themeCssVariableValue}
    {themeCssVariableInputHandler}
    {isThemePropertyDirty}
    {toggleAdminTheme}
    {isThemeHomeLogoScaleDirty}
    {homeLogoScale}
    {themeLogoScaleSelectHandler}
    {themeLogoScaleInputHandler}
    {previewThemeClickHandler}
  />
{/snippet}

{#snippet behaviorEditor()}
  <section class="appearance-theme-mode-setting">
    <div class="appearance-theme-mode-copy">
      <strong>{at("appearance_user_theme_mode_title", {}, "User theme mode selection")}</strong>
      <small>
        {at(
          "appearance_user_theme_mode_sub",
          {},
          "Allow users to choose Auto, Light, or Dark within the current theme."
        )}
      </small>
    </div>
    <div class="admin-setting-switch">
      <Switch.Root
        aria-label={at("appearance_user_theme_mode_title", {}, "User theme mode selection")}
        checked={userThemeModeEnabled}
        onCheckedChange={setUserThemeModeEnabled}
        disabled={settingsSaving || themesSaving}
        class="admin-switch-root"
      >
        <Switch.Thumb class="admin-switch-thumb" />
      </Switch.Root>
      <span>
        {userThemeModeEnabled ? at("enabled", {}, "Enabled") : at("disabled", {}, "Disabled")}
      </span>
    </div>
  </section>
  <section class="appearance-theme-mode-setting">
    <div class="appearance-theme-mode-copy">
      <strong>
        {at("settings_field_webapp_compact_home_enabled_label", {}, "Compact Home screen")}
      </strong>
      <small>
        {at(
          "settings_field_webapp_compact_home_enabled_description",
          {},
          "Combine subscription status, traffic usage, and balance into one compact summary card."
        )}
      </small>
    </div>
    <div class="admin-setting-switch">
      <Switch.Root
        aria-label={at(
          "settings_field_webapp_compact_home_enabled_label",
          {},
          "Compact Home screen"
        )}
        checked={compactHomeEnabled}
        onCheckedChange={setCompactHomeEnabled}
        disabled={settingsSaving || themesSaving}
        class="admin-switch-root"
      >
        <Switch.Thumb class="admin-switch-thumb" />
      </Switch.Root>
      <span>
        {compactHomeEnabled ? at("enabled", {}, "Enabled") : at("disabled", {}, "Disabled")}
      </span>
    </div>
  </section>
{/snippet}

{#if themesLoading || settingsLoading}
  <AdminEmptyState>{at("loading", {}, "Loading…")}</AdminEmptyState>
{:else}
  <AppearanceLibrary
    {currentLang}
    {at}
    themes={visibleThemes}
    {themeTitle}
    {defaultEditor}
    {brandEditor}
    {customEditor}
    {behaviorEditor}
    dirty={appearanceDirtyCount > 0}
    saving={settingsSaving || themesSaving}
    onsave={saveAppearance}
    onpreview={previewTheme}
    oncapture={captureTheme}
  />
{/if}
