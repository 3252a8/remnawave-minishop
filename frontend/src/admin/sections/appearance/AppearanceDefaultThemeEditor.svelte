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

  let {
    at,
    defaultTheme,
    defaultVariant,
    defaultThemeIsCurrent = false,
    themesSaving = false,
    defaultTokens = {},
    customGoogleFontName = $bindable(""),
    isThemeDirty,
    isDefaultVariantDirty,
    defaultVariantTitle,
    themeDescription,
    activateDefaultThemeFromClick,
    setDefaultVariantFromSwitch,
    previewDefaultVariantFromClick,
    applyDefaultPreset,
    isDefaultTokenDirty,
    tokenTextValue,
    fontItemsWithCurrent,
    defaultFontSelectHandler,
    applyCustomGoogleFont,
    radiusNumber,
    defaultRadiusRangeHandler,
    defaultRadiusInputHandler,
    isThemeHomeLogoScaleDirty,
    defaultHomeLogoScale,
    defaultLogoScaleSelectHandler,
    defaultLogoScaleInputHandler,
    defaultTokenValue,
    pickerHex,
    openDefaultColorPicker,
    defaultColorInputHandler,
    defaultTokenInputHandler,
    resetDefaultToken,
  }: {
    at: TranslateFn;
    defaultTheme: ThemeEntry | undefined;
    defaultVariant: ThemeVariant;
    defaultThemeIsCurrent?: boolean;
    themesSaving?: boolean;
    defaultTokens?: TokenMap;
    customGoogleFontName?: string;
    isThemeDirty: (theme: ThemeEntry | null | undefined) => boolean;
    isDefaultVariantDirty: () => boolean;
    defaultVariantTitle: (variant: unknown) => string;
    themeDescription: (theme: ThemeEntry) => string;
    activateDefaultThemeFromClick: (event: MouseEvent) => void;
    setDefaultVariantFromSwitch: (checked: boolean) => void;
    previewDefaultVariantFromClick: (event: MouseEvent) => void;
    applyDefaultPreset: (preset: { tokens?: TokenMap } | null | undefined) => void;
    isDefaultTokenDirty: (tokenKey: string) => boolean;
    tokenTextValue: (tokenKey: string, tokens?: TokenMap) => string;
    fontItemsWithCurrent: (items: FontOption[], value: unknown) => FontOption[];
    defaultFontSelectHandler: (tokenKey: string) => SelectCallback;
    applyCustomGoogleFont: (tokenKey: string, kind?: "sans" | "mono") => void;
    radiusNumber: (tokens?: TokenMap) => number;
    defaultRadiusRangeHandler: SelectCallback;
    defaultRadiusInputHandler: (event: Event) => void;
    isThemeHomeLogoScaleDirty: (
      theme: ThemeEntry | null | undefined,
      mode: LogoMode,
      variant?: string | null
    ) => boolean;
    defaultHomeLogoScale: (
      mode: LogoMode,
      theme?: ThemeEntry | null | undefined,
      variant?: string | null
    ) => number;
    defaultLogoScaleSelectHandler: (mode: LogoMode) => SelectCallback;
    defaultLogoScaleInputHandler: (mode: LogoMode) => (event: Event) => void;
    defaultTokenValue: (tokenKey: string, tokens?: TokenMap) => unknown;
    pickerHex: (value: unknown) => string;
    openDefaultColorPicker: (tokenKey: string, fallback?: string) => void;
    defaultColorInputHandler: (tokenKey: string) => (event: Event) => void;
    defaultTokenInputHandler: (tokenKey: string) => (event: Event) => void;
    resetDefaultToken: (tokenKey: string) => void;
  } = $props();
</script>

<section class="appearance-theme-section">
  <header class="appearance-theme-section-head">
    <div>
      <h4>{at("appearance_default_theme_title", {}, "默认主题")}</h4>
      <small>
        {at(
          "appearance_default_theme_section_sub",
          {},
          "应用基础主题：深色/浅色模式、颜色、字体和 Logo 缩放。"
        )}
      </small>
    </div>
    {#if isThemeDirty(defaultTheme)}
      <AdminBadge variant="warning">
        {at("settings_badge_dirty", {}, "已更改")}
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
      <button
        type="button"
        class="theme-card-select-hitbox"
        aria-label={at("appearance_use_default_theme", {}, "选择默认主题")}
        aria-pressed={defaultThemeIsCurrent}
        disabled={themesSaving || defaultThemeIsCurrent}
        onclick={activateDefaultThemeFromClick}
      ></button>
      <div class="default-theme-head">
        <div>
          <div class="default-theme-title">
            <Paintbrush size={17} />
            <strong>{at("appearance_default_theme_title", {}, "默认主题")}</strong>
            {#if defaultThemeIsCurrent}
              <AdminBadge variant="success">{at("status_current", {}, "当前")}</AdminBadge>
            {/if}
            <AdminBadge>{defaultVariantTitle(defaultVariant)}</AdminBadge>
            {#if isDefaultVariantDirty()}
              <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "已更改")}</AdminBadge>
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
              {at("appearance_use_default_theme", {}, "选择默认主题")}
            </AdminButton>
          {/if}
          <label class="appearance-switch appearance-mode-switch">
            <span>{at("appearance_default_dark", {}, "深色")}</span>
            <Switch.Root
              aria-label={at("appearance_default_variant", {}, "默认主题模式")}
              checked={defaultVariant === "light"}
              onCheckedChange={setDefaultVariantFromSwitch}
              class="admin-switch-root"
            >
              <Switch.Thumb class="admin-switch-thumb" />
            </Switch.Root>
            <span>{at("appearance_default_light", {}, "浅色")}</span>
          </label>
          <AdminButton size="sm" variant="ghost" onclick={previewDefaultVariantFromClick}>
            <ExternalLink size={13} />
            {at("appearance_preview_theme", {}, "预览")}
          </AdminButton>
        </div>
      </div>

      <div
        class="appearance-preset-row"
        aria-label={at("appearance_default_presets", {}, "默认主题预设")}
      >
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
          <h4><Type size={15} /> {at("appearance_typography", {}, "字体")}</h4>
          <div class="appearance-select-grid">
            <label class:is-dirty={isDefaultTokenDirty("font_sans")}>
              <span>
                {at("appearance_font_ui", {}, "界面")}
                {#if isDefaultTokenDirty("font_sans")}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "已更改")}</AdminBadge
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
                {at("appearance_font_brand", {}, "品牌")}
                {#if isDefaultTokenDirty("font_logo")}
                  <AdminBadge variant="warning"
                    >{at("settings_badge_dirty", {}, "已更改")}</AdminBadge
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
                    >{at("settings_badge_dirty", {}, "已更改")}</AdminBadge
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
              {at("appearance_font_apply_ui", {}, "界面")}
            </AdminButton>
            <AdminButton
              size="sm"
              onclick={() => applyCustomGoogleFont("font_logo")}
              disabled={!customGoogleFontName.trim()}
            >
              <Type size={12} />
              {at("appearance_font_apply_brand", {}, "品牌")}
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
                <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "已更改")}</AdminBadge
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
                <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "已更改")}</AdminBadge
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
                <AdminBadge variant="warning">{at("settings_badge_dirty", {}, "已更改")}</AdminBadge
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
                        >{at("settings_badge_dirty", {}, "已更改")}</AdminBadge
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
                    title={at(
                      "appearance_reset_token",
                      { label: tokenLabel },
                      `清除 ${tokenLabel}`
                    )}
                    aria-label={at(
                      "appearance_reset_token",
                      { label: tokenLabel },
                      `清除 ${tokenLabel}`
                    )}
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
      {at("themes_catalog_empty", {}, "主题目录为空，请刷新主题列表。")}
    </AdminEmptyState>
  {/if}
</section>
