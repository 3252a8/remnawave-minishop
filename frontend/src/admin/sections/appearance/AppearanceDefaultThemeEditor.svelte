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
  import { Switch } from "$components/ui/primitives.js";
  import {
    DEFAULT_THEME_PRESETS,
    FONT_OPTIONS,
    MONO_FONT_OPTIONS,
  } from "$lib/admin/appearanceOptions";
  import type {
    FontOption,
    ThemeEntry,
    ThemeVariant,
    TokenMap,
  } from "$lib/admin/appearanceOptions";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type LogoMode = "desktop" | "mobile";
  type SelectCallback = (...args: never[]) => void;

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

  export let at: TranslateFn;
  export let defaultTheme: ThemeEntry | undefined;
  export let defaultVariant: ThemeVariant;
  export let defaultThemeIsCurrent = false;
  export let themesSaving = false;
  export let defaultTokens: TokenMap = {};
  export let customGoogleFontName = "";
  export let isThemeDirty: (theme: ThemeEntry | null | undefined) => boolean;
  export let isDefaultVariantDirty: () => boolean;
  export let defaultVariantTitle: (variant: unknown) => string;
  export let themeDescription: (theme: ThemeEntry) => string;
  export let selectDefaultTheme: (event: MouseEvent | KeyboardEvent | null) => void;
  export let handleDefaultThemeKeydown: (event: KeyboardEvent) => void;
  export let activateDefaultThemeFromClick: (event: MouseEvent) => void;
  export let setDefaultVariantFromSwitch: (checked: boolean) => void;
  export let previewDefaultVariantFromClick: (event: MouseEvent) => void;
  export let applyDefaultPreset: (preset: { tokens?: TokenMap } | null | undefined) => void;
  export let isDefaultTokenDirty: (tokenKey: string) => boolean;
  export let tokenTextValue: (tokenKey: string, tokens?: TokenMap) => string;
  export let fontItemsWithCurrent: (items: FontOption[], value: unknown) => FontOption[];
  export let defaultFontSelectHandler: (tokenKey: string) => SelectCallback;
  export let applyCustomGoogleFont: (tokenKey: string, kind?: "sans" | "mono") => void;
  export let radiusNumber: (tokens?: TokenMap) => number;
  export let defaultRadiusRangeHandler: SelectCallback;
  export let defaultRadiusInputHandler: (event: Event) => void;
  export let isThemeHomeLogoScaleDirty: (
    theme: ThemeEntry | null | undefined,
    mode: LogoMode,
    variant?: string | null
  ) => boolean;
  export let defaultHomeLogoScale: (
    mode: LogoMode,
    theme?: ThemeEntry | null | undefined,
    variant?: string | null
  ) => number;
  export let defaultLogoScaleSelectHandler: (mode: LogoMode) => SelectCallback;
  export let defaultLogoScaleInputHandler: (mode: LogoMode) => (event: Event) => void;
  export let defaultTokenValue: (tokenKey: string, tokens?: TokenMap) => unknown;
  export let pickerHex: (value: unknown) => string;
  export let openDefaultColorPicker: (tokenKey: string, fallback?: string) => void;
  export let defaultColorInputHandler: (tokenKey: string) => (event: Event) => void;
  export let defaultTokenInputHandler: (tokenKey: string) => (event: Event) => void;
  export let resetDefaultToken: (tokenKey: string) => void;
</script>

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
            <strong>{at("appearance_default_theme_title", {}, "Тема по-умолчанию")}</strong>
            {#if defaultThemeIsCurrent}
              <AdminBadge variant="success">{at("status_current", {}, "Current")}</AdminBadge>
            {/if}
            <AdminBadge>{defaultVariantTitle(defaultVariant)}</AdminBadge>
            {#if isDefaultVariantDirty()}
              <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
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
            <AdminButton size="sm" onclick={activateDefaultThemeFromClick} disabled={themesSaving}>
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
            class:is-dirty={isThemeHomeLogoScaleDirty(defaultTheme, "desktop", defaultVariant)}
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
            class:is-dirty={isThemeHomeLogoScaleDirty(defaultTheme, "mobile", defaultVariant)}
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
