<script lang="ts">
  import { Download, Plus, RefreshCw, Save } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import { requestSectionAction } from "$lib/admin/sectionActions.svelte";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type ActionCallback = () => unknown | Promise<unknown>;
  type Props = {
    active: string;
    at: TranslateFn;
    dirtyCount: number;
    onCreateAd: ActionCallback;
    onCreateCode: ActionCallback;
    onCreateDocument: ActionCallback;
    onExportPayments: ActionCallback;
    onSaveSettings: ActionCallback;
    onSaveTranslations: ActionCallback;
    onSyncStats: ActionCallback;
    settingsSaving: boolean;
    syncBusy: boolean;
    translationsDirtyCount: number;
    translationsSaving: boolean;
  };

  let {
    active,
    at,
    dirtyCount,
    onCreateAd,
    onCreateCode,
    onCreateDocument,
    onExportPayments,
    onSaveSettings,
    onSaveTranslations,
    onSyncStats,
    settingsSaving,
    syncBusy,
    translationsDirtyCount,
    translationsSaving,
  }: Props = $props();
</script>

<div class="admin-header-actions">
  {#if active === "stats"}
    <AdminButton data-admin-action="sync-stats" onclick={onSyncStats} disabled={syncBusy}>
      <RefreshCw size={14} />
      <span class="admin-header-action-label"
        >{syncBusy
          ? at("btn_syncing", {}, "Synchronizing...")
          : at("btn_sync", {}, "Synchronize")}</span
      >
    </AdminButton>
  {/if}
  {#if active === "payments"}
    <AdminButton data-admin-action="export-payments" onclick={onExportPayments}>
      <Download size={14} /> CSV
    </AdminButton>
  {/if}
  {#if active === "promos"}
    <AdminButton data-admin-action="create-code" variant="primary" onclick={onCreateCode}>
      <Plus size={14} />
      <span class="admin-header-action-label">{at("promo_create_button", {}, "Create code")}</span>
    </AdminButton>
  {/if}
  {#if active === "ads"}
    <AdminButton data-admin-action="create-ad" variant="primary" onclick={onCreateAd}>
      <Plus size={14} />
      <span class="admin-header-action-label">{at("ads_create_button", {}, "Create campaign")}</span
      >
    </AdminButton>
  {/if}
  {#if active === "documents"}
    <AdminButton data-admin-action="create-document" variant="primary" onclick={onCreateDocument}>
      <Plus size={14} />
      <span class="admin-header-action-label"
        >{at("documents_create_button", {}, "Create document")}</span
      >
    </AdminButton>
  {/if}
  <!-- Every section creates from the page header with a verb + object label. -->
  {#if active === "gifts"}
    <AdminButton
      data-admin-action="create-gift"
      variant="primary"
      onclick={() => requestSectionAction("gifts", "create")}
    >
      <Plus size={14} />
      <span class="admin-header-action-label">{at("gifts_create", {}, "Create gift")}</span>
    </AdminButton>
  {/if}
  {#if active === "partners"}
    <AdminButton
      data-admin-action="add-partner"
      variant="primary"
      onclick={() => requestSectionAction("partners", "add")}
    >
      <Plus size={14} />
      <span class="admin-header-action-label">{at("partners_add", {}, "Add partner")}</span>
    </AdminButton>
  {/if}
  {#if active === "tariffs"}
    <AdminButton
      data-admin-action="create-tariff"
      variant="primary"
      onclick={() => requestSectionAction("tariffs", "create")}
    >
      <Plus size={14} />
      <span class="admin-header-action-label">{at("btn_create_tariff", {}, "Create tariff")}</span>
    </AdminButton>
  {/if}
  {#if active === "plugins"}
    <AdminButton
      data-admin-action="add-plugin"
      variant="primary"
      onclick={() => requestSectionAction("plugins", "add")}
    >
      <Plus size={14} />
      <span class="admin-header-action-label">{at("plugins_add", {}, "Add plugin")}</span>
    </AdminButton>
  {/if}
  {#if active === "settings"}
    {#if dirtyCount}
      <AdminBadge variant="warning">
        {at("settings_dirty_count", { count: dirtyCount }, "Changes: {count}")}
      </AdminBadge>
    {/if}
    <AdminButton
      variant="primary"
      onclick={onSaveSettings}
      disabled={!dirtyCount || settingsSaving}
    >
      <Save size={14} />
      <span class="admin-header-action-label"
        >{settingsSaving ? at("btn_saving", {}, "Saving...") : at("btn_save", {}, "Save")}</span
      >
    </AdminButton>
  {/if}
  {#if active === "translations"}
    {#if translationsDirtyCount}
      <AdminBadge variant="warning">
        {at("settings_dirty_count", { count: translationsDirtyCount }, "Changes: {count}")}
      </AdminBadge>
    {/if}
    <AdminButton
      variant="primary"
      onclick={onSaveTranslations}
      disabled={!translationsDirtyCount || translationsSaving}
    >
      <Save size={14} />
      <span class="admin-header-action-label"
        >{translationsSaving ? at("btn_saving", {}, "Saving...") : at("btn_save", {}, "Save")}</span
      >
    </AdminButton>
  {/if}
</div>
