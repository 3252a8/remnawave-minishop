<script lang="ts">
  import { getSettingsStore, getThemesStore } from "$lib/admin/context";
  import { FileText, Save } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import { FileInput, Input } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { onDestroy } from "svelte";
  import type { BrandInfo } from "$lib/admin/appearanceOptions";
  import type {
    SettingField,
    SettingsDirtyEntry,
    SettingsSection,
  } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SettingsDirtyState = Record<string, SettingsDirtyEntry>;

  let {
    at,
    brand = {},
    appFaviconUrl = "",
    appFaviconUseCustom = false,
    appearanceDirtyCount = 0,
    settingsSaving = false,
    themesSaving = false,
    onSave,
  }: {
    at: TranslateFn;
    brand?: BrandInfo;
    appFaviconUrl?: string;
    appFaviconUseCustom?: boolean;
    appearanceDirtyCount?: number;
    settingsSaving?: boolean;
    themesSaving?: boolean;
    onSave: () => void | Promise<void>;
  } = $props();

  const settingsStore = getSettingsStore();
  const themesStore = getThemesStore();

  let logoFileInput = $state<HTMLInputElement | null>(null);
  let faviconFileInput = $state<HTMLInputElement | null>(null);
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
  const settingsDirty: SettingsDirtyState = $derived(settingsStore.settingsDirty);
  const appearanceFields: SettingField[] = $derived(
    settingsSections.find((section: SettingsSection) => section.id === "appearance")?.fields || []
  );
  const fieldMap = $derived(new Map(appearanceFields.map((field) => [field.key, field])));
  const logoUrl = $derived(stringValueForKey("WEBAPP_LOGO_URL"));
  const currentLogoUrl = $derived(pendingLogoPreviewUrl || logoUrl || brand?.logoUrl || "");
  const previewLogoUrl = $derived(
    logoPreviewNonce && currentLogoUrl
      ? withCacheBust(currentLogoUrl, logoPreviewNonce)
      : currentLogoUrl
  );
  const persistedUseCustomFavicon = $derived(
    boolValue(valueForKey("WEBAPP_FAVICON_USE_CUSTOM", appFaviconUseCustom))
  );
  const faviconUrl = $derived(stringValueForKey("WEBAPP_FAVICON_URL", appFaviconUrl));
  const logoFaviconUrl = $derived(stringValueForKey("WEBAPP_LOGO_FAVICON_URL"));
  const generatedFaviconUrl = $derived(logoFaviconUrl || appFaviconUrl || previewLogoUrl || "");
  const currentFaviconUrl = $derived(
    faviconUseCustomDraft ? pendingFaviconPreviewUrl || faviconUrl || "" : generatedFaviconUrl
  );
  const previewFaviconUrl = $derived(
    faviconPreviewNonce && currentFaviconUrl
      ? withCacheBust(currentFaviconUrl, faviconPreviewNonce)
      : currentFaviconUrl
  );

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

  function boolValue(value: unknown): boolean {
    if (typeof value === "boolean") return value;
    if (typeof value === "number") return value !== 0;
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
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

  function applyUploadedAppearanceField(
    key: string,
    value: unknown,
    persisted: boolean | undefined
  ): void {
    if (persisted === false) {
      settingsStore.markDirty(key, value);
      return;
    }
    settingsStore.setFieldValue(key, value);
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
      const persisted = uploaded?.persisted;
      if (!uploadedUrl) {
        pendingLogoPreviewUrl = "";
        clearPendingObjectUrl();
        return;
      }
      applyUploadedAppearanceField("WEBAPP_LOGO_URL", uploadedUrl, persisted);
      if (uploaded?.faviconUrl) {
        applyUploadedAppearanceField("WEBAPP_LOGO_FAVICON_URL", uploaded.faviconUrl, persisted);
      }
      if (logoFileInput) logoFileInput.value = "";
    });
  }

  function uploadLogoFromUrl(): void {
    themesStore.uploadLogoUrl(logoSourceUrl).then((uploaded) => {
      const uploadedUrl = uploaded?.logoUrl || "";
      const persisted = uploaded?.persisted;
      if (!uploadedUrl) return;
      setPendingLogoPreview(uploadedUrl);
      logoSourceUrl = "";
      applyUploadedAppearanceField("WEBAPP_LOGO_URL", uploadedUrl, persisted);
      if (uploaded?.faviconUrl) {
        applyUploadedAppearanceField("WEBAPP_LOGO_FAVICON_URL", uploaded.faviconUrl, persisted);
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
      const persisted = uploaded?.persisted;
      if (!uploadedUrl) {
        pendingFaviconPreviewUrl = "";
        clearPendingFaviconObjectUrl();
        return;
      }
      applyUploadedAppearanceField("WEBAPP_FAVICON_URL", uploadedUrl, persisted);
      applyUploadedAppearanceField("WEBAPP_FAVICON_USE_CUSTOM", true, persisted);
      faviconUseCustomDraft = true;
      if (faviconFileInput) faviconFileInput.value = "";
    });
  }

  function uploadFaviconFromUrl(): void {
    themesStore.uploadFaviconUrl(faviconSourceUrl).then((uploaded) => {
      const uploadedUrl = uploaded?.faviconUrl || "";
      const persisted = uploaded?.persisted;
      if (!uploadedUrl) return;
      setPendingFaviconPreview(uploadedUrl);
      faviconSourceUrl = "";
      applyUploadedAppearanceField("WEBAPP_FAVICON_URL", uploadedUrl, persisted);
      applyUploadedAppearanceField("WEBAPP_FAVICON_USE_CUSTOM", true, persisted);
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

  onDestroy(() => {
    clearPendingObjectUrl();
    clearPendingFaviconObjectUrl();
  });
</script>

<article class="admin-card">
  <header class="admin-card-head">
    <div>
      <h3>{at("appearance_brand_title", {}, "Logo")}</h3>
      <small>{at("appearance_brand_sub", {}, "Upload a logo as a file or from a URL")}</small>
    </div>
    <div class="admin-editor-section-actions">
      {#if appearanceDirtyCount}
        <AdminBadge variant="warning">
          {at("settings_dirty_count", { count: appearanceDirtyCount }, "Changes: {count}")}
        </AdminBadge>
      {/if}
      <AdminButton
        size="sm"
        variant="primary"
        onclick={onSave}
        disabled={settingsSaving || themesSaving}
      >
        <Save size={13} />
        {settingsSaving || themesSaving
          ? at("btn_saving", {}, "Saving...")
          : at("btn_save", {}, "Save")}
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
          {at("appearance_logo_upload_file", {}, "Upload file")}
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
            {at("appearance_logo_upload_url", {}, "From URL")}
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
            aria-label={at("appearance_use_custom_favicon", {}, "Use a separate favicon")}
            bind:checked={faviconUseCustomDraft}
            onCheckedChange={setCustomFavicon}
            class="admin-switch-root"
          >
            <Switch.Thumb class="admin-switch-thumb" />
          </Switch.Root>
          <span>{at("appearance_use_custom_favicon", {}, "Use a separate favicon")}</span>
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
          {at("appearance_favicon_upload_file", {}, "Upload favicon")}
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
            {at("appearance_favicon_upload_url", {}, "From URL")}
          </AdminButton>
        </div>
      </section>
    </div>
  </div>
</article>
