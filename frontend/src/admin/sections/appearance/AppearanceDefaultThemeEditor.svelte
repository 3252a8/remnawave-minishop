<script lang="ts">
  import {
    Check,
    ExternalLink,
    Paintbrush,
    RefreshCw,
    Sliders,
    Sparkles,
    Type,
  } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import AdminSelect from "$components/patterns/admin/AdminSelect.svelte";
  import { ColorInput, Input, RangeInput } from "$components/ui/index.js";
  import { Tabs } from "$components/ui/primitives.js";
  import {
    DEFAULT_THEME_PRESETS,
    FONT_OPTIONS,
    HOME_ELEMENT_VISIBILITY_FIELDS,
    MONO_FONT_OPTIONS,
  } from "$lib/admin/appearanceOptions";
  import type {
    FontOption,
    ThemeEntry,
    ThemeVariant,
    TokenMap,
  } from "$lib/admin/appearanceOptions";
  import { selectedThemeVariant } from "$lib/admin/themeEditorContext";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type LogoMode = "desktop" | "mobile";
  type SelectCallback = (value: number) => void;

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

  let {
    at,
    defaultTheme,
    defaultVariant,
    selectedVariant = defaultVariant,
    defaultThemeIsCurrent = false,
    themesSaving = false,
    defaultTokens = {},
    customGoogleFontName = $bindable(""),
    isThemeDirty,
    isDefaultVariantDirty,
    themeDescription,
    activateDefaultThemeFromClick,
    onVariantChange,
    previewDefaultVariantFromClick,
    applyDefaultPreset,
    isDefaultTokenDirty,
    tokenTextValue,
    fontItemsWithCurrent,
    defaultFontSelectHandler,
    applyCustomGoogleFont,
    radiusNumber,
    transparencyNumber,
    defaultRadiusRangeHandler,
    defaultRadiusInputHandler,
    defaultTransparencyRangeHandler,
    defaultTransparencyInputHandler,
    isThemeHomeLogoScaleDirty,
    defaultHomeLogoScale,
    defaultLogoScaleSelectHandler,
    defaultLogoScaleInputHandler,
    defaultTokenValue,
    pickerHex,
    defaultColorInputHandler,
    defaultTokenInputHandler,
    defaultTokenSelectHandler,
    resetDefaultToken,
    editorTitle = "",
    editorSubtitle = "",
    activationLabel = "",
    radiusMin = 4,
    showPresets = true,
  }: {
    at: TranslateFn;
    defaultTheme: ThemeEntry | undefined;
    defaultVariant: ThemeVariant;
    selectedVariant?: ThemeVariant;
    defaultThemeIsCurrent?: boolean;
    themesSaving?: boolean;
    defaultTokens?: TokenMap;
    customGoogleFontName?: string;
    isThemeDirty: (theme: ThemeEntry | null | undefined) => boolean;
    isDefaultVariantDirty: () => boolean;
    themeDescription: (theme: ThemeEntry) => string;
    activateDefaultThemeFromClick: (event: MouseEvent) => void;
    onVariantChange: (variant: ThemeVariant) => void;
    previewDefaultVariantFromClick: (event: MouseEvent) => void;
    applyDefaultPreset: (
      preset: { tokens?: TokenMap } | null | undefined,
      variant?: ThemeVariant
    ) => void;
    isDefaultTokenDirty: (tokenKey: string) => boolean;
    tokenTextValue: (tokenKey: string, tokens?: TokenMap) => string;
    fontItemsWithCurrent: (items: FontOption[], value: unknown) => FontOption[];
    defaultFontSelectHandler: (tokenKey: string) => (value: string) => void;
    applyCustomGoogleFont: (tokenKey: string, kind?: "sans" | "mono") => void;
    radiusNumber: (tokens?: TokenMap) => number;
    transparencyNumber: (tokens?: TokenMap) => number;
    defaultRadiusRangeHandler: (value: number, variant?: ThemeVariant) => void;
    defaultRadiusInputHandler: (event: Event, variant?: ThemeVariant) => void;
    defaultTransparencyRangeHandler: (value: number, variant?: ThemeVariant) => void;
    defaultTransparencyInputHandler: (event: Event, variant?: ThemeVariant) => void;
    isThemeHomeLogoScaleDirty: (
      theme: ThemeEntry | null | undefined,
      mode: LogoMode,
      variant?: ThemeVariant
    ) => boolean;
    defaultHomeLogoScale: (
      mode: LogoMode,
      theme?: ThemeEntry | null | undefined,
      variant?: ThemeVariant
    ) => number;
    defaultLogoScaleSelectHandler: (mode: LogoMode, variant?: ThemeVariant) => SelectCallback;
    defaultLogoScaleInputHandler: (
      mode: LogoMode,
      variant?: ThemeVariant
    ) => (event: Event) => void;
    defaultTokenValue: (tokenKey: string, tokens?: TokenMap) => unknown;
    pickerHex: (value: unknown) => string | null;
    defaultColorInputHandler: (tokenKey: string, variant?: ThemeVariant) => (event: Event) => void;
    defaultTokenInputHandler: (tokenKey: string, variant?: ThemeVariant) => (event: Event) => void;
    defaultTokenSelectHandler: (
      tokenKey: string,
      variant?: ThemeVariant
    ) => (value: string) => void;
    resetDefaultToken: (tokenKey: string, variant?: ThemeVariant) => void;
    editorTitle?: string;
    editorSubtitle?: string;
    activationLabel?: string;
    radiusMin?: number;
    showPresets?: boolean;
  } = $props();

  const editorVariant = $derived(selectedThemeVariant(selectedVariant, defaultVariant));
  const homeVisibilityItems = $derived([
    { value: "auto", label: at("appearance_visibility_auto", {}, "Automatic") },
    { value: "visible", label: at("appearance_visibility_visible", {}, "Always show") },
    { value: "hidden", label: at("appearance_visibility_hidden", {}, "Hide") },
  ]);

  function homeVisibilityValue(tokenKey: string): string {
    const value = String(defaultTokenValue(tokenKey, defaultTokens) || "")
      .trim()
      .toLowerCase();
    return ["auto", "visible", "hidden"].includes(value) ? value : "auto";
  }

  function selectVariant(value: string): void {
    onVariantChange(value === "light" ? "light" : "dark");
  }
</script>

<section class="appearance-theme-section">
  <header class="appearance-theme-section-head">
    <div>
      <h4>{editorTitle || at("appearance_default_theme_title", {}, "Default theme")}</h4>
      <small>
        {editorSubtitle ||
          at(
            "appearance_default_theme_section_sub",
            {},
            "The app baseline theme: dark and light modes, colors, fonts, and logo scale."
          )}
      </small>
    </div>
    {#if isThemeDirty(defaultTheme)}
      <AdminBadge variant="warning">
        {at("settings_badge_dirty", {}, "Changed")}
      </AdminBadge>
    {/if}
  </header>
  {#if defaultTheme}
    <section
      class="default-theme-editor"
      class:is-current={defaultThemeIsCurrent}
      class:is-disabled={themesSaving}
      class:is-dirty={isThemeDirty(defaultTheme)}
      aria-current={defaultThemeIsCurrent ? "true" : undefined}
    >
      <div class="default-theme-head">
        <div>
          <div class="default-theme-title">
            <Paintbrush size={17} />
            <strong
              >{editorTitle || at("appearance_default_theme_title", {}, "Default theme")}</strong
            >
            {#if defaultThemeIsCurrent}
              <AdminBadge variant="success">{at("status_current", {}, "Current")}</AdminBadge>
            {/if}
            {#if isDefaultVariantDirty()}
              <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Changed")}</AdminBadge>
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
              class="appearance-theme-activate"
              size="sm"
              onclick={activateDefaultThemeFromClick}
              disabled={themesSaving}
            >
              <Check size={13} />
              {activationLabel || at("appearance_use_default_theme", {}, "Select default theme")}
            </AdminButton>
          {/if}
          <Tabs.Root
            class="appearance-variant-tabs"
            value={editorVariant}
            onValueChange={selectVariant}
          >
            <Tabs.List
              class="admin-tabs-list appearance-variant-tabs-list"
              aria-label={at("appearance_default_variant", {}, "Default theme variant")}
            >
              <Tabs.Trigger
                class="admin-tabs-trigger appearance-variant-tab"
                value="dark"
                disabled={themesSaving}
              >
                {at("appearance_default_dark", {}, "Dark")}
              </Tabs.Trigger>
              <Tabs.Trigger
                class="admin-tabs-trigger appearance-variant-tab"
                value="light"
                disabled={themesSaving}
              >
                {at("appearance_default_light", {}, "Light")}
              </Tabs.Trigger>
            </Tabs.List>
          </Tabs.Root>
          <AdminButton size="sm" variant="ghost" onclick={previewDefaultVariantFromClick}>
            <ExternalLink size={13} />
            {at("appearance_preview_theme", {}, "Preview")}
          </AdminButton>
        </div>
      </div>

      {#if showPresets}
        <div
          class="appearance-preset-row"
          aria-label={at("appearance_default_presets", {}, "Default theme presets")}
        >
          {#each DEFAULT_THEME_PRESETS[editorVariant] || [] as preset (preset.id)}
            <button
              type="button"
              class="appearance-preset-btn"
              onclick={() => applyDefaultPreset(preset, selectedVariant)}
            >
              <span style={`background:${preset.swatch}`}></span>
              {preset.label}
            </button>
          {/each}
        </div>
      {/if}

      <div class="default-theme-grid">
        <section class="default-theme-panel">
          <h4><Type size={15} /> {at("appearance_typography", {}, "Typography")}</h4>
          <div class="appearance-select-grid">
            <label class:is-dirty={isDefaultTokenDirty("font_sans")}>
              <span>
                {at("appearance_font_ui", {}, "Interface")}
                {#if isDefaultTokenDirty("font_sans")}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
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
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
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
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
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
                  >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                >
              {/if}
            </span>
            <RangeInput
              class="appearance-logo-scale-range"
              min={radiusMin}
              max="28"
              step="1"
              ariaLabel={at("appearance_radius", {}, "Radius")}
              value={radiusNumber(defaultTokens)}
              onValueChange={(value) => defaultRadiusRangeHandler(value, selectedVariant)}
            />
            <span class="appearance-logo-scale-value">
              <Input
                class="input"
                type="number"
                min={radiusMin}
                max="28"
                step="1"
                value={radiusNumber(defaultTokens)}
                oninput={(event) => defaultRadiusInputHandler(event, selectedVariant)}
              />
              px
            </span>
          </div>
          <div
            class="appearance-logo-scale-row appearance-default-scale-row"
            class:is-dirty={isDefaultTokenDirty("transparency")}
          >
            <span class="appearance-logo-scale-label">
              {at("appearance_transparency", {}, "Transparency")}
              {#if isDefaultTokenDirty("transparency")}
                <AdminBadge variant="warning"
                  >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                >
              {/if}
            </span>
            <RangeInput
              class="appearance-logo-scale-range"
              min="0"
              max="100"
              step="1"
              ariaLabel={at("appearance_transparency", {}, "Transparency")}
              value={transparencyNumber(defaultTokens)}
              onValueChange={(value) => defaultTransparencyRangeHandler(value, selectedVariant)}
            />
            <span class="appearance-logo-scale-value">
              <Input
                class="input"
                type="number"
                min="0"
                max="100"
                step="1"
                value={transparencyNumber(defaultTokens)}
                oninput={(event) => defaultTransparencyInputHandler(event, selectedVariant)}
              />
              %
            </span>
          </div>
          <div
            class="appearance-logo-scale-row appearance-default-scale-row"
            class:is-dirty={isThemeHomeLogoScaleDirty(defaultTheme, "desktop", selectedVariant)}
          >
            <span class="appearance-logo-scale-label">
              {at("appearance_logo_desktop", {}, "Desktop logo")}
              {#if isThemeHomeLogoScaleDirty(defaultTheme, "desktop", selectedVariant)}
                <AdminBadge variant="warning"
                  >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                >
              {/if}
            </span>
            <RangeInput
              class="appearance-logo-scale-range"
              min="50"
              max="300"
              step="5"
              ariaLabel={at("appearance_logo_desktop", {}, "Desktop logo")}
              value={defaultHomeLogoScale("desktop", defaultTheme, selectedVariant)}
              onValueChange={defaultLogoScaleSelectHandler("desktop", selectedVariant)}
            />
            <span class="appearance-logo-scale-value">
              <Input
                class="input"
                type="number"
                min="50"
                max="300"
                step="5"
                value={defaultHomeLogoScale("desktop", defaultTheme, selectedVariant)}
                oninput={defaultLogoScaleInputHandler("desktop", selectedVariant)}
              />
              %
            </span>
          </div>
          <div
            class="appearance-logo-scale-row appearance-default-scale-row"
            class:is-dirty={isThemeHomeLogoScaleDirty(defaultTheme, "mobile", selectedVariant)}
          >
            <span class="appearance-logo-scale-label">
              {at("appearance_logo_mobile", {}, "Mobile logo")}
              {#if isThemeHomeLogoScaleDirty(defaultTheme, "mobile", selectedVariant)}
                <AdminBadge variant="warning"
                  >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                >
              {/if}
            </span>
            <RangeInput
              class="appearance-logo-scale-range"
              min="50"
              max="300"
              step="5"
              ariaLabel={at("appearance_logo_mobile", {}, "Mobile logo")}
              value={defaultHomeLogoScale("mobile", defaultTheme, selectedVariant)}
              onValueChange={defaultLogoScaleSelectHandler("mobile", selectedVariant)}
            />
            <span class="appearance-logo-scale-value">
              <Input
                class="input"
                type="number"
                min="50"
                max="300"
                step="5"
                value={defaultHomeLogoScale("mobile", defaultTheme, selectedVariant)}
                oninput={defaultLogoScaleInputHandler("mobile", selectedVariant)}
              />
              %
            </span>
          </div>
        </section>
      </div>

      <section class="default-theme-panel appearance-home-elements-panel">
        <h4>
          <Sliders size={15} />
          {at("appearance_home_elements_title", {}, "Home screen elements")}
        </h4>
        <p class="appearance-home-elements-hint">
          {at(
            "appearance_home_elements_hint",
            {},
            "Use one visibility policy for every supported Home screen element. Automatic preserves product rules; Always show still respects feature availability."
          )}
        </p>
        <div class="appearance-home-elements-grid">
          {#each HOME_ELEMENT_VISIBILITY_FIELDS as field (field.token)}
            <label class:is-dirty={isDefaultTokenDirty(field.token)}>
              <span>
                {at(field.labelKey, {}, field.label)}
                {#if isDefaultTokenDirty(field.token)}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                  >
                {/if}
              </span>
              <AdminSelect
                class="appearance-select"
                value={homeVisibilityValue(field.token)}
                items={homeVisibilityItems}
                ariaLabel={at(field.labelKey, {}, field.label)}
                onValueChange={defaultTokenSelectHandler(field.token, editorVariant)}
              />
            </label>
          {/each}
        </div>
      </section>

      <div class="default-theme-token-grid">
        {#each TOKEN_GROUPS as group (group.title)}
          {@const GroupIcon = group.icon}
          <section class="default-theme-panel">
            <h4>
              <GroupIcon size={15} />
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
                        >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                      >
                    {/if}
                  </span>
                  <ColorInput
                    class="admin-color appearance-color-picker"
                    translate={at}
                    allowAlpha={tokenKey !== "accent"}
                    value={pickerHex(defaultTokenValue(tokenKey, defaultTokens)) || ""}
                    disabled={!pickerHex(defaultTokenValue(tokenKey, defaultTokens))}
                    ariaLabel={tokenLabel}
                    oninput={defaultColorInputHandler(tokenKey, selectedVariant)}
                  />
                  <Input
                    class="input appearance-color-text"
                    type="text"
                    placeholder={at("appearance_token_empty", {}, "not set")}
                    value={tokenTextValue(tokenKey, defaultTokens)}
                    oninput={defaultTokenInputHandler(tokenKey, selectedVariant)}
                  />
                  <AdminButton
                    class="appearance-token-reset"
                    size="sm"
                    variant="ghost"
                    title={at("appearance_reset_token", { label: tokenLabel }, "Reset {label}")}
                    aria-label={at(
                      "appearance_reset_token",
                      { label: tokenLabel },
                      "Reset {label}"
                    )}
                    onclick={() => resetDefaultToken(tokenKey, selectedVariant)}
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
      {at(
        "themes_catalog_empty",
        {},
        "The catalog is empty. Add a theme folder to data/themes and refresh."
      )}
    </AdminEmptyState>
  {/if}
</section>
