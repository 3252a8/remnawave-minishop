<script lang="ts">
  import { getSettingsStore, getThemesStore } from "$lib/admin/context";
  import { RefreshCw, Save } from "$components/ui/icons.js";
  import { AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { onMount } from "svelte";

  import {
    firstFontFamily,
    localizedThemeName,
    writeThemePreviewDraft,
  } from "$lib/webapp/themeStyle";
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
    "WEBAPP_LOGO_URL",
    "WEBAPP_FAVICON_URL",
    "WEBAPP_FAVICON_USE_CUSTOM",
    "WEBAPP_LOGO_FAVICON_URL",
    "WEBAPP_ENABLED",
  ]);
  let customGoogleFontName = $state("");

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

  function isAppearanceSettingKey(key: string): boolean {
    return APPEARANCE_SETTING_KEYS.has(key) || appearanceFields.some((field) => field.key === key);
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

  function defaultFontSelectHandler(tokenKey: string): (value: string) => void {
    return (value: string) => setDefaultFont(tokenKey, value);
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

  function selectTheme(theme: ThemeEntry): void {
    if (!themesSaving) themesStore.setCurrentTheme(theme.key);
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
</script>

{#if themesLoading || settingsLoading}
  <AdminEmptyState>{at("loading", {}, "Loading…")}</AdminEmptyState>
{:else}
  <div class="appearance-stack">
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

    <article class="admin-card">
      <header class="admin-card-head">
        <div>
          <h3>{at("appearance_themes_title", {}, "Themes")}</h3>
          <small>{at("appearance_themes_sub", {}, "Global theme, accent color, and preview")}</small
          >
        </div>
        <div class="admin-editor-section-actions">
          <AdminButton
            size="sm"
            onclick={themesStore.loadThemes}
            disabled={themesLoading || themesSaving}
          >
            <RefreshCw size={13} />
            {at("btn_refresh", {}, "Refresh")}
          </AdminButton>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={saveAppearance}
            disabled={settingsSaving || themesSaving}
          >
            <Save size={13} />
            {at("btn_save", {}, "Save")}
          </AdminButton>
        </div>
      </header>
      <div class="admin-card-body appearance-themes-body">
        {#if !visibleThemes.length}
          <AdminEmptyState>
            {at(
              "themes_catalog_empty",
              {},
              "The catalog is empty. Add a theme folder to data/themes and refresh."
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
          />
        {/if}
      </div>
    </article>
  </div>
{/if}
