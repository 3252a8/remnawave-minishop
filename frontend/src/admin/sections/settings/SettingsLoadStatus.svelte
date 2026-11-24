<script lang="ts">
  import { AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { getSettingsStore } from "$lib/admin/context";

  let {
    at,
    currentLang,
    empty,
  }: {
    at: (key: string, vars?: Record<string, unknown>, fallback?: string) => string;
    currentLang: string;
    empty: boolean;
  } = $props();

  const store = getSettingsStore();
</script>

{#if store.settingsLoadError}
  <AdminEmptyState>
    <p role="alert">
      {store.settingsLoadError}
      {#if store.settingsRetryAt}
        {@const time = new Date(store.settingsRetryAt).toLocaleTimeString(currentLang)}
        {at("settings_retry_at", { time }, `Try again at ${time}.`)}
      {/if}
    </p>
    <AdminButton variant="ghost" onclick={() => store.loadSettings({ refresh: true })}>
      {at("retry", {}, "Retry")}
    </AdminButton>
  </AdminEmptyState>
{:else if empty}
  <AdminEmptyState
    >{store.settingsLoading
      ? at("loading", {}, "Loading…")
      : at("no_data", {}, "No data")}</AdminEmptyState
  >
{/if}
