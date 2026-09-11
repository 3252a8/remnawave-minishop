<script lang="ts">
  import { ChevronDown } from "$components/ui/icons.js";
  import { AdminEmptyState } from "$components/patterns/admin/index.js";
  import { Checkbox, ColorInput, Input } from "$components/ui/index.js";
  import type {
    FontOption,
    LogoMode,
    ThemeEntry,
    ThemeVariant,
    TokenMap,
  } from "$lib/admin/appearanceOptions";
  import { selectedThemeVariant } from "$lib/admin/themeEditorContext";
  import AppearanceDefaultThemeEditor from "./AppearanceDefaultThemeEditor.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SelectCallback = (value: number) => void;

  let {
    at,
    customThemes = [],
    activeKey = "",
    themesSaving = false,
    customGoogleFontName = $bindable(""),
    isThemeDirty,
    themeTitle,
    themeDescription,
    themeVariant,
    customThemeTokens,
    activateThemeFromClick,
    previewThemeClickHandler,
    applyCustomThemePreset,
    isThemeTokenDirty,
    customThemeTokenText,
    fontItemsWithCurrent,
    setCustomThemeFont,
    applyCustomThemeGoogleFont,
    customThemeRadiusNumber,
    customThemeTransparencyNumber,
    setCustomThemeRadius,
    setCustomThemeTransparency,
    isThemeHomeLogoScaleDirty,
    homeLogoScale,
    themeLogoScaleSelectHandler,
    themeLogoScaleInputHandler,
    customThemeTokenValue,
    customThemePickerHex,
    themeCssPickerHex,
    setCustomThemeToken,
    resetCustomThemeToken,
    themeCssVariables,
    themeCssVariableValue,
    themeCssVariableInputHandler,
    isThemePropertyDirty,
    toggleAdminTheme,
  }: {
    at: TranslateFn;
    customThemes?: ThemeEntry[];
    activeKey?: string;
    themesSaving?: boolean;
    customGoogleFontName?: string;
    isThemeDirty: (theme: ThemeEntry | null | undefined) => boolean;
    themeTitle: (theme: ThemeEntry) => string;
    themeDescription: (theme: ThemeEntry) => string;
    themeVariant: (theme: ThemeEntry) => ThemeVariant;
    customThemeTokens: (theme: ThemeEntry, variant?: ThemeVariant) => TokenMap;
    activateThemeFromClick: (theme: ThemeEntry, event: MouseEvent) => void;
    previewThemeClickHandler: (theme: ThemeEntry) => (event: MouseEvent) => void;
    applyCustomThemePreset: (
      theme: ThemeEntry,
      preset: { tokens?: TokenMap } | null | undefined
    ) => void;
    isThemeTokenDirty: (
      theme: ThemeEntry | null | undefined,
      key: string,
      variant?: string | null
    ) => boolean;
    customThemeTokenText: (theme: ThemeEntry, key: string, variant?: ThemeVariant) => string;
    fontItemsWithCurrent: (items: FontOption[], value: unknown) => FontOption[];
    setCustomThemeFont: (theme: ThemeEntry, key: string, value: unknown) => void;
    applyCustomThemeGoogleFont: (theme: ThemeEntry, key: string, kind?: "sans" | "mono") => void;
    customThemeRadiusNumber: (theme: ThemeEntry, variant?: ThemeVariant) => number;
    customThemeTransparencyNumber: (theme: ThemeEntry, variant?: ThemeVariant) => number;
    setCustomThemeRadius: (theme: ThemeEntry, value: unknown, variant?: ThemeVariant) => void;
    setCustomThemeTransparency: (theme: ThemeEntry, value: unknown, variant?: ThemeVariant) => void;
    isThemeHomeLogoScaleDirty: (
      theme: ThemeEntry | null | undefined,
      mode: LogoMode,
      variant?: string | null
    ) => boolean;
    homeLogoScale: (theme: ThemeEntry, mode: LogoMode, variant?: ThemeVariant) => number;
    themeLogoScaleSelectHandler: (
      theme: ThemeEntry,
      mode: LogoMode,
      variant?: ThemeVariant
    ) => SelectCallback;
    themeLogoScaleInputHandler: (
      theme: ThemeEntry,
      mode: LogoMode,
      variant?: ThemeVariant
    ) => (event: Event) => void;
    customThemeTokenValue: (theme: ThemeEntry, key: string, variant?: ThemeVariant) => unknown;
    customThemePickerHex: (
      theme: ThemeEntry,
      value: unknown,
      variant?: ThemeVariant
    ) => string | null;
    themeCssPickerHex: (theme: ThemeEntry, key: string, variant?: ThemeVariant) => string | null;
    setCustomThemeToken: (
      theme: ThemeEntry,
      key: string,
      value: unknown,
      variant?: ThemeVariant
    ) => void;
    resetCustomThemeToken: (theme: ThemeEntry, key: string, variant?: ThemeVariant) => void;
    themeCssVariables: (theme: ThemeEntry, variant?: ThemeVariant) => Record<string, string>;
    themeCssVariableValue: (theme: ThemeEntry, key: string, variant?: ThemeVariant) => string;
    themeCssVariableInputHandler: (
      theme: ThemeEntry,
      key: string,
      variant?: ThemeVariant
    ) => (event: Event) => void;
    isThemePropertyDirty: (theme: ThemeEntry | null | undefined, property: string) => boolean;
    toggleAdminTheme: (theme: ThemeEntry, checked: boolean) => void;
  } = $props();

  let selectedVariants = $state<Record<string, ThemeVariant>>({});

  const inputValue = (event: Event): string =>
    (event.currentTarget as HTMLInputElement | null)?.value ?? "";
</script>

<section class="appearance-theme-section">
  {#if customThemes.length}
    {#each customThemes as theme (theme.key)}
      {@const variant = themeVariant(theme)}
      {@const selectedVariant = selectedThemeVariant(selectedVariants[theme.key], variant)}
      {@const tokens = customThemeTokens(theme, selectedVariant)}
      <AppearanceDefaultThemeEditor
        {at}
        defaultTheme={theme}
        defaultVariant={variant}
        {selectedVariant}
        defaultThemeIsCurrent={theme.key === activeKey}
        showPresets={false}
        {themesSaving}
        defaultTokens={tokens}
        bind:customGoogleFontName
        {isThemeDirty}
        isDefaultVariantDirty={() => isThemePropertyDirty(theme, "active_variant")}
        {themeDescription}
        activateDefaultThemeFromClick={(event) => activateThemeFromClick(theme, event)}
        onVariantChange={(nextVariant) => (selectedVariants[theme.key] = nextVariant)}
        previewDefaultVariantFromClick={previewThemeClickHandler(theme)}
        applyDefaultPreset={(preset) => applyCustomThemePreset(theme, preset)}
        isDefaultTokenDirty={(key) => isThemeTokenDirty(theme, key, selectedVariant)}
        tokenTextValue={(key) => customThemeTokenText(theme, key, selectedVariant)}
        {fontItemsWithCurrent}
        defaultFontSelectHandler={(key) => (value) => setCustomThemeFont(theme, key, value)}
        applyCustomGoogleFont={(key, kind) => applyCustomThemeGoogleFont(theme, key, kind)}
        radiusNumber={() => customThemeRadiusNumber(theme, selectedVariant)}
        transparencyNumber={() => customThemeTransparencyNumber(theme, selectedVariant)}
        defaultRadiusRangeHandler={(value) => setCustomThemeRadius(theme, value, selectedVariant)}
        defaultRadiusInputHandler={(event) =>
          setCustomThemeRadius(theme, inputValue(event), selectedVariant)}
        defaultTransparencyRangeHandler={(value) =>
          setCustomThemeTransparency(theme, value, selectedVariant)}
        defaultTransparencyInputHandler={(event) =>
          setCustomThemeTransparency(theme, inputValue(event), selectedVariant)}
        {isThemeHomeLogoScaleDirty}
        defaultHomeLogoScale={(mode, _theme, nextVariant) =>
          homeLogoScale(theme, mode, nextVariant ?? selectedVariant)}
        defaultLogoScaleSelectHandler={(mode, nextVariant) =>
          themeLogoScaleSelectHandler(theme, mode, nextVariant ?? selectedVariant)}
        defaultLogoScaleInputHandler={(mode, nextVariant) =>
          themeLogoScaleInputHandler(theme, mode, nextVariant ?? selectedVariant)}
        defaultTokenValue={(key) => customThemeTokenValue(theme, key, selectedVariant)}
        pickerHex={(value) => customThemePickerHex(theme, value, selectedVariant)}
        defaultColorInputHandler={(key) => (event) =>
          setCustomThemeToken(theme, key, inputValue(event), selectedVariant)}
        defaultTokenInputHandler={(key) => (event) =>
          setCustomThemeToken(theme, key, inputValue(event), selectedVariant)}
        resetDefaultToken={(key) => resetCustomThemeToken(theme, key, selectedVariant)}
        editorTitle={themeTitle(theme)}
        editorSubtitle={at(
          "appearance_custom_theme_editor_sub",
          {},
          "The same core controls as the standard theme."
        )}
        activationLabel={at(
          "appearance_use_theme_named",
          { title: themeTitle(theme) },
          "Select {title}"
        )}
        radiusMin={0}
      />

      <details class="appearance-custom-extras">
        <summary class="appearance-custom-extras-trigger">
          <span>
            <strong>{at("appearance_custom_advanced", {}, "Additional theme options")}</strong>
            <small>
              {at("appearance_custom_advanced_sub", {}, "Admin usage and package CSS variables")}
            </small>
          </span>
          <ChevronDown size={16} />
        </summary>
        <div class="appearance-custom-extras-content">
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
            <span>{at("themes_use_in_admin", {}, "Use in admin panel")}</span>
          </label>
          {#if Object.keys(themeCssVariables(theme, selectedVariant)).length}
            <div class="appearance-custom-css-list">
              {#each Object.entries(themeCssVariables(theme, selectedVariant)) as [key, cssValue] (key)}
                {@const resolvedColor = themeCssPickerHex(theme, key, selectedVariant)}
                <label
                  class="appearance-custom-css-row"
                  class:is-dirty={isThemeTokenDirty(theme, key, selectedVariant)}
                >
                  <code title={key}>{key}</code>
                  <ColorInput
                    class="admin-color appearance-color-picker"
                    value={resolvedColor || ""}
                    disabled={!resolvedColor}
                    ariaLabel={key}
                    oninput={themeCssVariableInputHandler(theme, key, selectedVariant)}
                  />
                  <Input
                    class="input appearance-color-text"
                    type="text"
                    value={themeCssVariableValue(theme, key, selectedVariant) || cssValue}
                    oninput={themeCssVariableInputHandler(theme, key, selectedVariant)}
                  />
                </label>
              {/each}
            </div>
          {/if}
        </div>
      </details>
    {/each}
  {:else}
    <AdminEmptyState>
      {at("appearance_custom_themes_empty", {}, "No custom themes yet.")}
    </AdminEmptyState>
  {/if}
</section>
