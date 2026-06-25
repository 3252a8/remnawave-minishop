<script lang="ts">
  import { Check, ExternalLink, FileText } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { Checkbox, ColorInput, Input, RangeInput } from "$components/ui/index.js";
  import type { ThemeEntry } from "$lib/admin/appearanceOptions";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type LogoMode = "desktop" | "mobile";
  type SelectCallback = (...args: never[]) => void;

  let {
    at,
    customThemes = [],
    activeKey = "",
    themesSaving = false,
    isThemeDirty,
    themeTitle,
    themeDescription,
    isThemeTokenDirty,
    isThemeAccentSet,
    pickerHex,
    openThemeAccentPicker,
    themeAccentInputHandler,
    isThemePropertyDirty,
    toggleAdminTheme,
    isThemeHomeLogoScaleDirty,
    homeLogoScale,
    themeLogoScaleSelectHandler,
    themeLogoScaleInputHandler,
    previewThemeClickHandler,
    selectTheme,
    handleThemeKeydown,
  }: {
    at: TranslateFn;
    customThemes?: ThemeEntry[];
    activeKey?: string;
    themesSaving?: boolean;
    isThemeDirty: (theme: ThemeEntry | null | undefined) => boolean;
    themeTitle: (theme: ThemeEntry) => string;
    themeDescription: (theme: ThemeEntry) => string;
    isThemeTokenDirty: (
      theme: ThemeEntry | null | undefined,
      tokenKey: string,
      variant?: string | null
    ) => boolean;
    isThemeAccentSet: (theme: ThemeEntry) => boolean;
    pickerHex: (value: unknown) => string;
    openThemeAccentPicker: (theme: ThemeEntry) => void;
    themeAccentInputHandler: (theme: ThemeEntry) => (event: Event) => void;
    isThemePropertyDirty: (theme: ThemeEntry | null | undefined, property: string) => boolean;
    toggleAdminTheme: (theme: ThemeEntry, checked: boolean) => void;
    isThemeHomeLogoScaleDirty: (
      theme: ThemeEntry | null | undefined,
      mode: LogoMode,
      variant?: string | null
    ) => boolean;
    homeLogoScale: (theme: ThemeEntry, mode: LogoMode) => number;
    themeLogoScaleSelectHandler: (theme: ThemeEntry, mode: LogoMode) => SelectCallback;
    themeLogoScaleInputHandler: (theme: ThemeEntry, mode: LogoMode) => (event: Event) => void;
    previewThemeClickHandler: (theme: ThemeEntry) => (event: MouseEvent) => void;
    selectTheme: (theme: ThemeEntry, event: MouseEvent | KeyboardEvent | null) => void;
    handleThemeKeydown: (event: KeyboardEvent, theme: ThemeEntry) => void;
  } = $props();
</script>

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
                <AdminBadge variant="success">{at("status_current", {}, "Текущая")}</AdminBadge>
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
              ariaLabel={at("appearance_theme_home_logo_scale_desktop", {}, "Desktop logo scale")}
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
              ariaLabel={at("appearance_theme_home_logo_scale_mobile", {}, "Mobile logo scale")}
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
            <AdminButton size="sm" variant="ghost" onclick={previewThemeClickHandler(theme)}>
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
