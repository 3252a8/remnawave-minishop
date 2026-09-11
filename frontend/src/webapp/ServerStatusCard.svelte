<script lang="ts">
  import { Activity, ArrowRight, ExternalLink } from "$components/ui/icons.js";
  import Card from "$components/ui/card.svelte";
  import {
    statusProvider,
    type ServerStatusStore,
  } from "$lib/webapp/stores/serverStatusStore.svelte";
  import type { OpenLinkAction, Translate, VoidAction } from "$lib/webapp/types.js";

  let {
    statusStore,
    goStatus,
    openExternalLink,
    t,
  }: {
    statusStore: ServerStatusStore;
    goStatus: VoidAction;
    openExternalLink: OpenLinkAction;
    t: Translate;
  } = $props();

  const status = $derived(statusStore.data);
  const itemCount = $derived(
    (status?.groups || []).reduce((total, group) => total + group.items.length, 0)
  );
  const provider = $derived(statusProvider(status));
  const isExternalLink = $derived(provider === "url");

  function openStatus(): void {
    if (provider === "url" && status?.externalUrl) openExternalLink(status.externalUrl);
    else goStatus();
  }
</script>

{#if status?.enabled}
  <Card compact class="server-status-card">
    <button type="button" class="server-status-card-action" onclick={openStatus}>
      <span
        class:status-problem={!isExternalLink && status.status !== "operational"}
        class="server-status-card-icon"
      >
        <Activity size={19} />
      </span>
      <span class="server-status-card-copy">
        <strong>{t("wa_server_status_title", {}, "Server status")}</strong>
        <small>
          {#if isExternalLink}
            {t("wa_server_status_external_link", {}, "Open status page")}
          {:else}
            {t(`wa_server_status_state_${status.status}`, {}, status.status)}
          {/if}
          {#if itemCount && !isExternalLink}
            · {t(
              "wa_server_status_services_count",
              { count: itemCount },
              `${itemCount} services`
            )}{/if}
        </small>
      </span>
      {#if provider === "url"}<ExternalLink size={17} />{:else}<ArrowRight size={17} />{/if}
    </button>
  </Card>
{/if}

<style>
  :global(.server-status-card.card) {
    padding: 0;
    overflow: hidden;
  }
  .server-status-card-action {
    width: 100%;
    border: 0;
    background: transparent;
    color: inherit;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 15px;
    text-align: left;
    cursor: pointer;
  }
  .server-status-card-icon {
    width: 34px;
    height: 34px;
    border-radius: var(--radius-inner);
    display: grid;
    place-items: center;
    color: var(--accent, #00b86b);
    background: color-mix(in srgb, var(--accent, #00b86b) 13%, transparent);
  }
  .server-status-card-icon.status-problem {
    color: #d97706;
    background: color-mix(in srgb, #f59e0b 14%, transparent);
  }
  .server-status-card-copy {
    min-width: 0;
    flex: 1;
    display: grid;
    gap: 2px;
  }
  .server-status-card-copy small {
    opacity: 0.68;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
