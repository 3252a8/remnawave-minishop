<script>
  import { Check, ExternalLink, FileText, RefreshCw, Save } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { Checkbox, ColorInput, FileInput, Input, RangeInput } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { getContext, onDestroy, onMount } from "svelte";

  import { localizedThemeName } from "$lib/webapp/themeStyle.js";

  export let at;
  export let currentLang = "ru";
  export let onSettingsSaved = () => {};
  export let brand = {};
  export let appFaviconUrl = "";
  export let appFaviconUseCustom = false;

  const settingsStore = getContext("settingsStore");
  const themesStore = getContext("themesStore");
  const APPEARANCE_SETTING_KEYS = new Set([
    "SUBSCRIPTION_MINI_APP_URL",
    "WEBAPP_PRIMARY_COLOR",
    "WEBAPP_LOGO_URL",
    "WEBAPP_FAVICON_URL",
    "WEBAPP_FAVICON_USE_CUSTOM",
    "WEBAPP_LOGO_FAVICON_URL",
    "WEBAPP_ENABLED",
  ]);

  $: ({ settingsSections, settingsLoading, settingsDirty, settingsSaving } = $settingsStore);
  $: ({ themesCatalog, themesLoading, themesDir, themesSaving } = $themesStore);
  $: appearanceFields =
    settingsSections.find((section) => section.id === "appearance")?.fields || [];
  $: fieldMap = new Map(appearanceFields.map((field) => [field.key, field]));
  $: activeKey = themesCatalog.default_theme;
  $: logoUrl = valueForKey("WEBAPP_LOGO_URL");
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
  $: faviconUrl = valueForKey("WEBAPP_FAVICON_URL", appFaviconUrl);
  $: logoFaviconUrl = valueForKey("WEBAPP_LOGO_FAVICON_URL");
  $: generatedFaviconUrl = logoFaviconUrl || appFaviconUrl || previewLogoUrl || "";
  $: currentFaviconUrl = useCustomFavicon
    ? pendingFaviconPreviewUrl || faviconUrl || ""
    : generatedFaviconUrl;
  $: previewFaviconUrl =
    faviconPreviewNonce && currentFaviconUrl ? withCacheBust(currentFaviconUrl) : currentFaviconUrl;
  $: dirtyCount = Object.keys(settingsDirty || {}).filter((key) =>
    isAppearanceSettingKey(key)
  ).length;
  $: appearanceDirtyKeys = Object.keys(settingsDirty || {}).filter((key) =>
    isAppearanceSettingKey(key)
  );

  let logoFileInput;
  let faviconFileInput;
  let logoSourceUrl = "";
  let faviconSourceUrl = "";
  let logoPreviewNonce = 0;
  let faviconPreviewNonce = 0;
  let logoPreviewFailed = false;
  let faviconPreviewFailed = false;
  let lastPreviewLogoUrl = "";
  let lastPreviewFaviconUrl = "";
  let lastPersistedUseCustomFavicon;
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

  function valueForKey(key, fallback = "") {
    if (settingsDirty[key]?.deleted) return "";
    if (Object.prototype.hasOwnProperty.call(settingsDirty, key)) {
      return settingsDirty[key].value;
    }
    const field = fieldMap.get(key);
    if (!field) return fallback;
    return field.value ?? fallback;
  }

  function isAppearanceSettingKey(key) {
    return APPEARANCE_SETTING_KEYS.has(key) || appearanceFields.some((field) => field.key === key);
  }

  function boolValue(value) {
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  }

  function withLogoCacheBust(url) {
    return withCacheBust(url, logoPreviewNonce);
  }

  function withCacheBust(url, nonce) {
    if (!url || url.startsWith("data:") || url.startsWith("blob:")) return url;
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}v=${nonce}`;
  }

  function clearPendingObjectUrl() {
    if (pendingObjectUrl && typeof URL !== "undefined") {
      URL.revokeObjectURL(pendingObjectUrl);
    }
    pendingObjectUrl = "";
  }

  function clearPendingFaviconObjectUrl() {
    if (pendingFaviconObjectUrl && typeof URL !== "undefined") {
      URL.revokeObjectURL(pendingFaviconObjectUrl);
    }
    pendingFaviconObjectUrl = "";
  }

  function setPendingLogoPreview(url, objectUrl = "") {
    clearPendingObjectUrl();
    pendingObjectUrl = objectUrl;
    pendingLogoPreviewUrl = url;
    logoPreviewFailed = false;
    logoPreviewNonce = Date.now();
  }

  function setPendingFaviconPreview(url, objectUrl = "") {
    clearPendingFaviconObjectUrl();
    pendingFaviconObjectUrl = objectUrl;
    pendingFaviconPreviewUrl = url;
    faviconPreviewFailed = false;
    faviconPreviewNonce = Date.now();
  }

  function themeTitle(theme) {
    return localizedThemeName(theme, currentLang) || "—";
  }

  function themeDescription(theme) {
    const folder = `${themesDir || "data/themes"}/${theme.key}`;
    return theme.css_file ? `${folder}/${theme.css_file}` : `${folder}/theme.json`;
  }

  function isThemeAccentSet(theme) {
    return Boolean(String(theme.tokens?.accent || "").trim());
  }

  function pickerHex(value) {
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

  function homeLogoScale(theme, mode) {
    return themesStore.resolveThemeHomeLogoScale(theme, mode);
  }

  function openThemeAccentPicker(theme) {
    themesStore.setThemeAccent(theme.key, pickerHex(theme.tokens?.accent || "#00fe7a"));
  }

  function handleLogoFileChange(event) {
    const file = event.currentTarget.files?.[0];
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

  function uploadLogoFromUrl() {
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

  function handleFaviconFileChange(event) {
    const file = event.currentTarget.files?.[0];
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

  function uploadFaviconFromUrl() {
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

  function setCustomFavicon(enabled) {
    const nextEnabled = Boolean(enabled);
    faviconUseCustomDraft = nextEnabled;
    settingsStore.markDirty("WEBAPP_FAVICON_USE_CUSTOM", nextEnabled);
    if (!nextEnabled) {
      pendingFaviconPreviewUrl = "";
      clearPendingFaviconObjectUrl();
    }
  }

  async function saveAppearance() {
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
      await onSettingsSaved({ reloadFrontend: true });
    }
  }

  function toggleAdminTheme(theme, checked) {
    themesStore.toggleAdminUse(theme.key, checked);
  }

  function setThemeAccent(theme, value) {
    themesStore.setThemeAccent(theme.key, value);
  }

  function setThemeHomeLogoScale(theme, mode, value) {
    themesStore.setThemeHomeLogoScale(theme.key, mode, value);
  }

  function isThemeControlTarget(target) {
    return target?.closest?.("button,input,label,.admin-theme-card-option,.ui-range-input");
  }

  function selectTheme(theme, event = null) {
    if (isThemeControlTarget(event?.target)) return;
    if (!themesSaving) themesStore.setCurrentTheme(theme.key);
  }

  function handleThemeKeydown(event, theme) {
    if (isThemeControlTarget(event?.target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    selectTheme(theme);
  }

  function previewTheme(event, theme) {
    event.stopPropagation();
    const url = `/home?theme_preview=${encodeURIComponent(theme.key)}`;
    window.open(url, "_blank", "noopener");
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
          {#if dirtyCount}
            <AdminBadge variant="warning">
              {at("settings_dirty_count", { count: dirtyCount }, `Изменений: ${dirtyCount}`)}
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
      <div class="admin-card-body">
        {#if !themesCatalog.themes.length}
          <AdminEmptyState>
            {at(
              "themes_catalog_empty",
              {},
              "Каталог пуст. Добавьте папку темы в data/themes и обновите список."
            )}
          </AdminEmptyState>
        {:else}
          <div class="admin-theme-grid">
            {#each themesCatalog.themes as theme (theme.key)}
              {@const isCurrent = theme.key === activeKey}
              <div
                role="button"
                tabindex={themesSaving ? -1 : 0}
                class="admin-theme-card"
                class:is-current={isCurrent}
                class:is-disabled={theme.enabled === false}
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
                <label class="admin-theme-card-option appearance-color-row">
                  <span>{at("appearance_theme_accent", {}, "Accent")}</span>
                  <ColorInput
                    class={`admin-color${!isThemeAccentSet(theme) ? " is-empty" : ""}`}
                    value={pickerHex(theme.tokens?.accent)}
                    ariaLabel={at("appearance_theme_accent", {}, "Accent")}
                    title={isThemeAccentSet(theme)
                      ? theme.tokens?.accent
                      : at("appearance_theme_accent_empty", {}, "Не задан")}
                    onclick={() => openThemeAccentPicker(theme)}
                    oninput={(event) => setThemeAccent(theme, event.currentTarget.value)}
                  />
                  <Input
                    class="input appearance-color-text"
                    type="text"
                    placeholder={at("appearance_theme_accent_placeholder", {}, "Не задан")}
                    value={theme.tokens?.accent || ""}
                    oninput={(event) => setThemeAccent(theme, event.currentTarget.value)}
                  />
                </label>
                <label class="admin-theme-card-option">
                  <Checkbox
                    checked={theme.use_in_admin !== false}
                    disabled={themesSaving}
                    ariaLabel={at("themes_use_in_admin", {}, "Use in admin")}
                    onCheckedChange={(checked) => toggleAdminTheme(theme, checked)}
                  />
                  <span>{at("themes_use_in_admin", {}, "Использовать в админке")}</span>
                </label>
                <div class="admin-theme-card-option appearance-logo-scale-row">
                  <span class="appearance-logo-scale-label"
                    >{at(
                      "appearance_theme_home_logo_scale_desktop",
                      {},
                      "Логотип на десктопе"
                    )}</span
                  >
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
                    onValueChange={(value) => setThemeHomeLogoScale(theme, "desktop", value)}
                  />
                  <span class="appearance-logo-scale-value">
                    <Input
                      class="input"
                      type="number"
                      min="50"
                      max="300"
                      step="5"
                      value={homeLogoScale(theme, "desktop")}
                      oninput={(event) =>
                        setThemeHomeLogoScale(theme, "desktop", event.currentTarget.value)}
                    />
                    %
                  </span>
                </div>
                <div class="admin-theme-card-option appearance-logo-scale-row">
                  <span class="appearance-logo-scale-label"
                    >{at(
                      "appearance_theme_home_logo_scale_mobile",
                      {},
                      "Логотип на мобильных"
                    )}</span
                  >
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
                    onValueChange={(value) => setThemeHomeLogoScale(theme, "mobile", value)}
                  />
                  <span class="appearance-logo-scale-value">
                    <Input
                      class="input"
                      type="number"
                      min="50"
                      max="300"
                      step="5"
                      value={homeLogoScale(theme, "mobile")}
                      oninput={(event) =>
                        setThemeHomeLogoScale(theme, "mobile", event.currentTarget.value)}
                    />
                    %
                  </span>
                </div>
                <div class="appearance-theme-actions">
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={(event) => previewTheme(event, theme)}
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
  }
</style>
