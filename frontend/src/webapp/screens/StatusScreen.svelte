<script lang="ts">
  import {
    Activity,
    ArrowLeft,
    ExternalLink,
    RefreshCw,
    TriangleAlert,
  } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { AttentionDot } from "$components/ui/index.js";
  import type { ServerStatusStore } from "$lib/webapp/stores/serverStatusStore.svelte";
  import type { OpenLinkAction, Translate, VoidAction } from "$lib/webapp/types.js";

  let {
    currentLang = "ru",
    statusStore,
    goHome,
    openExternalLink,
    t,
  }: {
    currentLang?: string;
    statusStore: ServerStatusStore;
    goHome: VoidAction;
    openExternalLink: OpenLinkAction;
    t: Translate;
  } = $props();

  const status = $derived(statusStore.data);
  const items = $derived((status?.groups || []).flatMap((group) => group.items));
  const onlineCount = $derived(items.filter((item) => item.status === "online").length);

  function goBack(): void {
    if (typeof window !== "undefined" && window.history.length > 1) window.history.back();
    else goHome();
  }

  function formattedDate(value: string | null | undefined): string {
    if (!value) return t("wa_server_status_unknown", {}, "Unknown");
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(currentLang, { dateStyle: "medium", timeStyle: "short" }).format(
      date
    );
  }

  function percent(value: number): string {
    return `${new Intl.NumberFormat(currentLang, { maximumFractionDigits: 2 }).format(value)}%`;
  }

  function historyFor(itemId: string) {
    const history = statusStore.history[itemId] || [];
    return Array.from({ length: 5 }, (_, index) => history[index] || null);
  }
</script>

<main class="content with-nav status-layout">
  <div class="status-topbar">
    <Button variant="secondary" size="icon" onclick={goBack} aria-label={t("wa_back", {}, "Back")}>
      <ArrowLeft size={21} />
    </Button>
    <div>
      <h1>{t("wa_server_status_title", {}, "Server status")}</h1>
      <p>{t("wa_server_status_subtitle", {}, "Live service availability")}</p>
    </div>
    <Button
      variant="secondary"
      size="icon"
      onclick={() => statusStore.refresh(true)}
      disabled={statusStore.refreshing}
      aria-label={t("wa_server_status_refresh", {}, "Refresh")}
    >
      <RefreshCw size={18} class={statusStore.refreshing ? "status-spinning" : ""} />
    </Button>
  </div>

  {#if statusStore.loading && !status}
    <div class="status-skeleton" aria-label={t("wa_loading", {}, "Loading")}>
      <span></span><span></span><span></span>
    </div>
  {:else if statusStore.error && !status}
    <Card class="status-message status-error">
      <TriangleAlert size={25} />
      <strong>{t("wa_server_status_error_title", {}, "Status unavailable")}</strong>
      <p>
        {t("wa_server_status_error_description", {}, "Could not load service status. Try again.")}
      </p>
      <Button variant="secondary" onclick={() => statusStore.refresh(true)}
        >{t("wa_server_status_retry", {}, "Try again")}</Button
      >
    </Card>
  {:else if !status?.enabled}
    <Card class="status-message">
      <Activity size={25} />
      <strong>{t("wa_server_status_disabled_title", {}, "Status is not enabled")}</strong>
      <p>
        {t("wa_server_status_disabled_description", {}, "Service status is currently unavailable.")}
      </p>
    </Card>
  {:else}
    {#if status.stale}
      <div class="status-stale">
        <TriangleAlert size={17} />
        {t("wa_server_status_stale", {}, "Showing the latest cached update")}
      </div>
    {/if}

    <Card compact class="status-overview status-tone-{status.status}">
      <div class="status-overview-icon"><Activity size={22} /></div>
      <div class="status-overview-line">
        <h2>{t(`wa_server_status_state_${status.status}`, {}, status.status)}</h2>
        <p>
          {t(
            "wa_server_status_online_count",
            { online: onlineCount, total: items.length },
            `${onlineCount} of ${items.length} online`
          )}
        </p>
      </div>
    </Card>

    {#if status.incidents?.length}
      <section class="status-section">
        <h2>{t("wa_server_status_incidents", {}, "Incidents")}</h2>
        {#each status.incidents as incident}
          <Card class="status-incident">
            <div>
              <strong>{incident.title}</strong><span
                >{t(`wa_server_status_state_${incident.status}`, {}, incident.status)}</span
              >
            </div>
            {#if incident.content}<p>{incident.content}</p>{/if}
            {#if incident.createdAt}<small>{formattedDate(incident.createdAt)}</small>{/if}
          </Card>
        {/each}
      </section>
    {/if}

    {#if status.groups?.length}
      {#each status.groups as group}
        <section class="status-section">
          <h2>{group.name}</h2>
          <Card class="status-group">
            {#each group.items as item}
              <div class="status-item">
                <AttentionDot position="inline" class="status-dot status-item-{item.status}" />
                <span class="status-item-name"
                  ><strong>{item.name}</strong><small
                    >{t(`wa_server_status_item_${item.status}`, {}, item.status)}</small
                  ></span
                >
                <span class="status-metrics">
                  <small
                    >{item.latencyMs != null
                      ? `${Math.round(item.latencyMs)} ms`
                      : t("wa_server_status_latency_unavailable", {}, "n/a")}</small
                  >
                  {#if item.provider === "xray-checker"}
                    <span
                      class="status-history"
                      aria-label={t("wa_server_status_history", { count: 5 }, "Last 5 checks")}
                    >
                      {#each historyFor(item.id) as historyEntry}
                        <span
                          class:status-history-empty={!historyEntry}
                          class="status-history-point status-item-{historyEntry?.status || 'unknown'}"
                          aria-hidden="true"
                        ></span>
                      {/each}
                    </span>
                  {/if}
                  {#if item.uptime24h != null}<small
                      >{t(
                        "wa_server_status_uptime_24h",
                        { value: percent(item.uptime24h) },
                        `${percent(item.uptime24h)} / 24h`
                      )}</small
                    >{/if}
                </span>
              </div>
            {/each}
          </Card>
        </section>
      {/each}
    {:else}
      <Card class="status-message"
        ><strong>{t("wa_server_status_empty_title", {}, "No services to show")}</strong>
        <p>
          {t("wa_server_status_empty_description", {}, "The provider returned no service details.")}
        </p></Card
      >
    {/if}

    <footer class="status-footer">
      <small
        >{t(
          "wa_server_status_last_updated",
          { date: formattedDate(status.updatedAt) },
          `Updated ${formattedDate(status.updatedAt)}`
        )}</small
      >
      {#if status.externalUrl}
        <Button variant="secondary" onclick={() => openExternalLink(status.externalUrl || "")}
          ><ExternalLink size={16} />{t(
            "wa_server_status_details_link",
            {},
            "Detailed status"
          )}</Button
        >
      {/if}
    </footer>
  {/if}
</main>

<style>
  .status-layout {
    gap: 14px;
  }
  .status-topbar {
    display: grid;
    grid-template-columns: 42px 1fr 42px;
    align-items: center;
    gap: 10px;
  }
  .status-topbar h1,
  :global(.status-overview) h2,
  .status-section h2 {
    margin: 0;
  }
  .status-topbar p,
  :global(.status-overview) p,
  :global(.status-message) p,
  :global(.status-incident) p {
    margin: 3px 0 0;
    opacity: 0.68;
  }
  .status-topbar > div {
    min-width: 0;
  }
  .status-topbar h1 {
    font-size: 1.2rem;
  }
  .status-topbar p {
    font-size: 0.82rem;
  }
  .status-skeleton {
    display: grid;
    gap: 12px;
  }
  .status-skeleton span {
    height: 96px;
    border-radius: 18px;
    background: linear-gradient(
      100deg,
      var(--card, #fff) 25%,
      color-mix(in srgb, var(--text, #111) 7%, transparent) 45%,
      var(--card, #fff) 65%
    );
    background-size: 220% 100%;
    animation: status-shimmer 1.4s infinite;
  }
  :global(.status-overview.card) {
    display: grid;
    grid-template-columns: 38px minmax(0, 1fr);
    align-items: center;
    gap: 10px;
    border-color: color-mix(in srgb, var(--accent, #00b86b) 35%, transparent);
  }
  .status-overview-icon {
    width: 38px;
    height: 38px;
    border-radius: 12px;
    display: grid;
    place-items: center;
    color: var(--accent, #00b86b);
    background: color-mix(in srgb, var(--accent, #00b86b) 13%, transparent);
  }
  .status-overview-line {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    min-width: 0;
  }
  .status-overview-line h2 {
    min-width: 0;
    font-size: 1rem;
    line-height: 1.15;
  }
  .status-overview-line p {
    flex: 0 0 auto;
    margin: 0;
    font-size: 0.76rem;
    white-space: nowrap;
  }
  :global(.status-overview.status-tone-degraded),
  :global(.status-overview.status-tone-partial_outage),
  :global(.status-overview.status-tone-maintenance) {
    border-color: color-mix(in srgb, #f59e0b 45%, transparent);
  }
  :global(.status-overview.status-tone-major_outage),
  :global(.status-overview.status-tone-unknown) {
    border-color: color-mix(in srgb, #ef4444 45%, transparent);
  }
  .status-stale {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 12px;
    color: #9a6700;
    background: color-mix(in srgb, #f59e0b 13%, transparent);
    font-size: 0.84rem;
  }
  .status-section {
    display: grid;
    gap: 8px;
  }
  .status-section > h2 {
    padding-left: 3px;
    font-size: 0.9rem;
    opacity: 0.72;
  }
  :global(.status-group.card) {
    padding: 0;
    overflow: hidden;
  }
  .status-item {
    display: grid;
    grid-template-columns: 10px minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
  }
  .status-item + .status-item {
    border-top: 1px solid color-mix(in srgb, currentColor 9%, transparent);
  }
  :global(.status-dot.attention-dot) {
    --attention-dot-color: #94a3b8;
    width: 8px;
    min-width: 8px;
    height: 8px;
  }
  :global(.status-dot.status-item-online) {
    --attention-dot-color: #22c55e;
  }
  :global(.status-dot.status-item-offline) {
    --attention-dot-color: #ef4444;
  }
  :global(.status-dot.status-item-degraded),
  :global(.status-dot.status-item-maintenance) {
    --attention-dot-color: #f59e0b;
  }
  .status-item-name,
  .status-metrics {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  .status-item-name strong {
    font-family:
      var(--font-country-flags), var(--font-sans), "Apple Color Emoji", "Segoe UI Emoji", sans-serif;
    font-variant-emoji: text;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status-item-name small,
  .status-metrics small,
  .status-footer small {
    opacity: 0.62;
    font-size: 0.75rem;
  }
  .status-metrics {
    text-align: right;
  }
  .status-history {
    display: flex;
    justify-content: flex-end;
    gap: 3px;
  }
  .status-history-point {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #94a3b8;
  }
  .status-history-point.status-item-online {
    background: #22c55e;
  }
  .status-history-point.status-item-offline {
    background: #ef4444;
  }
  .status-history-point.status-item-degraded,
  .status-history-point.status-item-maintenance {
    background: #f59e0b;
  }
  .status-history-empty {
    opacity: 0.28;
  }
  :global(.status-incident) div {
    display: flex;
    justify-content: space-between;
    gap: 10px;
  }
  :global(.status-incident) span {
    font-size: 0.75rem;
    opacity: 0.65;
  }
  :global(.status-message.card) {
    min-height: 160px;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 8px;
    text-align: center;
  }
  :global(.status-error.card) {
    color: #b42318;
  }
  .status-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 2px;
  }
  :global(.status-spinning) {
    animation: status-spin 0.8s linear infinite;
  }
  @keyframes status-spin {
    to {
      transform: rotate(360deg);
    }
  }
  @keyframes status-shimmer {
    to {
      background-position: -220% 0;
    }
  }
  @media (max-width: 390px) {
    .status-layout {
      gap: 12px;
    }
    .status-footer {
      align-items: stretch;
      flex-direction: column;
    }
  }
</style>
