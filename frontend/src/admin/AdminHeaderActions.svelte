<script lang="ts">
  import { Download, Plus, RefreshCw, Save } from "$components/ui/icons.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type ActionCallback = () => unknown | Promise<unknown>;
  type Props = {
    active: string;
    at: TranslateFn;
    dirtyCount: number;
    onCreateAd: ActionCallback;
    onCreateCode: ActionCallback;
    onCreateTariff: ActionCallback;
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
    onCreateTariff,
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
      {syncBusy
        ? at("btn_syncing", {}, "Синхронизация...")
        : at("btn_sync", {}, "Синхронизировать")}
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
      {at("btn_create", {}, "Создать")}
    </AdminButton>
  {/if}
  {#if active === "ads"}
    <AdminButton data-admin-action="create-ad" variant="primary" onclick={onCreateAd}>
      <Plus size={14} />
      {at("btn_campaign", {}, "Кампания")}
    </AdminButton>
  {/if}
  {#if active === "tariffs"}
    <AdminButton data-admin-action="create-tariff" variant="primary" onclick={onCreateTariff}>
      <Plus size={14} />
      {at("btn_tariff", {}, "Тариф")}
    </AdminButton>
  {/if}
  {#if active === "settings"}
    {#if dirtyCount}
      <AdminBadge variant="warning">
        {at("settings_dirty_count", { count: dirtyCount }, "Изменений: " + dirtyCount)}
      </AdminBadge>
    {/if}
    <AdminButton
      variant="primary"
      onclick={onSaveSettings}
      disabled={!dirtyCount || settingsSaving}
    >
      <Save size={14} />
      {settingsSaving ? at("btn_saving", {}, "Сохранение...") : at("btn_save", {}, "Сохранить")}
    </AdminButton>
  {/if}
  {#if active === "translations"}
    {#if translationsDirtyCount}
      <AdminBadge variant="warning">
        {at(
          "settings_dirty_count",
          { count: translationsDirtyCount },
          "Изменений: " + translationsDirtyCount
        )}
      </AdminBadge>
    {/if}
    <AdminButton
      variant="primary"
      onclick={onSaveTranslations}
      disabled={!translationsDirtyCount || translationsSaving}
    >
      <Save size={14} />
      {translationsSaving ? at("btn_saving", {}, "Сохранение...") : at("btn_save", {}, "Сохранить")}
    </AdminButton>
  {/if}
</div>
