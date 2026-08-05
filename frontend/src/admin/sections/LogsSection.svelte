<script lang="ts">
  import { getLogsStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import { onMount } from "svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
    VirtualTableRows,
  } from "$components/patterns/admin/index.js";
  import { RefreshCw, TriangleAlert, User, X } from "$components/ui/icons.js";
  import { TableHandler } from "@vincjo/datatables";
  import type { components } from "../../lib/api/openapi.generated";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type LogEntry = components["schemas"]["LogOut"];
  type UserKind = "user" | "target";

  let {
    at,
    fmtDate,
    onOpenUserCard = () => {},
  }: {
    at: TranslateFn;
    fmtDate: (value: string) => string;
    onOpenUserCard?: (userId: number | string | null | undefined) => void;
  } = $props();

  const logsStore = getLogsStore();
  const logsTable = new TableHandler<LogEntry>();
  const LOGS_PAGE_SIZE = 50;

  const logsState = $derived(logsStore);
  const logs = $derived(logsState.logs as LogEntry[]);
  const logsTotal = $derived(Number(logsState.logsTotal || 0));
  const logsPage = $derived(Number(logsState.logsPage || 0));
  const logsUserFilter = $derived(String(logsState.logsUserFilter || ""));
  const logsLoading = $derived(Boolean(logsState.logsLoading));
  const logsError = $derived(String(logsState.logsError || ""));
  const logRows = $derived(logsTable.rows as LogEntry[]);

  $effect(() => logsTable.setRows(logs));

  const logsPageCount = $derived(Math.max(1, Math.ceil(Number(logsTotal || 0) / LOGS_PAGE_SIZE)));
  const logHeaders = $derived([
    at("date", {}, "Date"),
    at("event", {}, "Event"),
    at("user_short", {}, "User"),
    at("target_short", {}, "Target"),
    at("content", {}, "Content"),
  ]);

  function userDisplay(entry: LogEntry, kind: UserKind): string | number {
    const id = kind === "target" ? entry.target_user_id : entry.user_id;
    const label = kind === "target" ? entry.target_user_label : entry.user_label;
    if (label) return label;
    if (kind !== "target") {
      if (entry.telegram_first_name) return entry.telegram_first_name;
      if (entry.telegram_username) {
        const username = String(entry.telegram_username);
        return username.startsWith("@") ? username : `@${username}`;
      }
      if (entry.email) return entry.email;
    }
    return id || "—";
  }

  function userId(entry: LogEntry, kind: UserKind): number | null {
    return kind === "target" ? entry.target_user_id : entry.user_id;
  }

  function applyLogsFilter(): void {
    logsStore.setPage(0);
  }

  function clearLogsFilter(): void {
    if (!logsUserFilter) return;
    logsStore.setFilter("");
    logsStore.setPage(0);
  }

  onMount(() => {
    logsStore.loadLogs({ refresh: true });
  });
</script>

<div class="admin-toolbar admin-toolbar-card admin-logs-toolbar">
  <div class="admin-toolbar-search admin-logs-toolbar-search">
    <div class="admin-logs-filter-input">
      <Input
        type="search"
        class="input"
        placeholder={at("logs_user_filter_placeholder", {}, "Filter by user ID")}
        value={logsUserFilter}
        oninput={(e) => logsStore.setFilter((e.currentTarget as HTMLInputElement).value)}
        onkeydown={(e) => e.key === "Enter" && applyLogsFilter()}
      />
      {#if logsUserFilter}
        <button
          type="button"
          class="admin-logs-filter-clear"
          title={at("reset", {}, "Reset")}
          aria-label={at("reset", {}, "Reset")}
          onclick={clearLogsFilter}
        >
          <X size={14} />
        </button>
      {/if}
    </div>
    <AdminButton variant="primary" onclick={applyLogsFilter}>{at("apply", {}, "Apply")}</AdminButton
    >
    <AdminButton
      class="admin-logs-refresh"
      variant="ghost"
      size="icon"
      disabled={logsLoading}
      title={at("btn_refresh", {}, "Refresh")}
      aria-label={at("btn_refresh", {}, "Refresh")}
      onclick={() => logsStore.loadLogs({ refresh: true })}
    >
      <RefreshCw size={14} />
    </AdminButton>
  </div>
</div>

<div class="admin-table-wrap">
  {#if logsLoading}
    <AdminTableSkeleton
      headers={logHeaders}
      rows={10}
      rowHeight={72}
      widths={["120px", "120px", "160px", "160px", "220px"]}
    />
  {:else if logsError}
    <AdminEmptyState tone="card" class="admin-logs-error-state">
      <TriangleAlert size={18} />
      <span>{logsError}</span>
      <AdminButton variant="ghost" onclick={() => logsStore.loadLogs({ refresh: true })}>
        <RefreshCw size={14} />
        {at("btn_refresh", {}, "Refresh")}
      </AdminButton>
    </AdminEmptyState>
  {:else if !logRows.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("logs_empty", {}, "No entries")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable>
      <thead>
        <tr>
          <th>{at("date", {}, "Date")}</th>
          <th>{at("event", {}, "Event")}</th>
          <th>{at("user_short", {}, "User")}</th>
          <th>{at("target_short", {}, "Target")}</th>
          <th>{at("content", {}, "Content")}</th>
        </tr>
      </thead>
      <VirtualTableRows
        rows={logRows}
        colspan={5}
        rowHeight={72}
        getKey={(entry, index) => entry.log_id ?? index}
      >
        {#snippet children(entry)}
          <tr>
            <td data-label={at("date", {}, "Date")}
              >{entry.timestamp ? fmtDate(entry.timestamp) : "—"}</td
            >
            <td class="admin-cell-mono" data-label={at("event", {}, "Event")}>{entry.event_type}</td
            >
            <td class="admin-logs-user-cell" data-label={at("user_short", {}, "User")}>
              {#if userId(entry, "user")}
                <span class="admin-logs-user">
                  <AdminButton
                    class="admin-logs-user-btn"
                    variant="ghost"
                    size="icon"
                    title={at("payments_open_user", {}, "Open user card")}
                    aria-label={at("payments_open_user", {}, "Open user card")}
                    onclick={() => onOpenUserCard(userId(entry, "user"))}
                  >
                    <User size={14} />
                  </AdminButton>
                  <span class="admin-logs-user-meta">
                    <span class="admin-logs-user-name">{userDisplay(entry, "user")}</span>
                    <span class="admin-logs-user-id">ID {userId(entry, "user")}</span>
                  </span>
                </span>
              {:else}
                <span class="admin-muted">—</span>
              {/if}
            </td>
            <td class="admin-logs-user-cell" data-label={at("target_short", {}, "Target")}>
              {#if userId(entry, "target")}
                <span class="admin-logs-user">
                  <AdminButton
                    class="admin-logs-user-btn"
                    variant="ghost"
                    size="icon"
                    title={at("payments_open_user", {}, "Open user card")}
                    aria-label={at("payments_open_user", {}, "Open user card")}
                    onclick={() => onOpenUserCard(userId(entry, "target"))}
                  >
                    <User size={14} />
                  </AdminButton>
                  <span class="admin-logs-user-meta">
                    <span class="admin-logs-user-name">{userDisplay(entry, "target")}</span>
                    <span class="admin-logs-user-id">ID {userId(entry, "target")}</span>
                  </span>
                </span>
              {:else}
                <span class="admin-muted">—</span>
              {/if}
            </td>
            <td class="admin-cell-wrap" data-label={at("content", {}, "Content")}
              >{entry.content || ""}</td
            >
          </tr>
        {/snippet}
      </VirtualTableRows>
    </AdminTable>
  {/if}
</div>

<AdminPagination
  page={logsPage}
  pageCount={logsPageCount}
  total={logsTotal}
  pageLabel={at("page_short", {}, "Page")}
  ofLabel={at("pagination_of", {}, "of")}
  totalLabel={at("total", {}, "Total")}
  jumpLabel={at("page_short", {}, "Page")}
  jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
  goLabel={at("pagination_go", {}, "Go")}
  prevLabel={at("back", {}, "Back")}
  nextLabel={at("next", {}, "Next")}
  onPageChange={(page) => logsStore.setPage(page)}
/>

<style>
  :global(.admin-logs-toolbar.admin-toolbar-card) {
    grid-template-columns: minmax(0, 1fr);
  }

  .admin-logs-toolbar-search {
    grid-template-columns: minmax(0, 1fr) auto 36px;
  }

  .admin-logs-filter-input {
    position: relative;
    min-width: 0;
  }

  .admin-logs-filter-input :global(.input) {
    width: 100%;
    padding-right: 38px;
  }

  .admin-logs-filter-input :global(input[type="search"]::-webkit-search-cancel-button) {
    appearance: none;
  }

  .admin-logs-filter-clear {
    position: absolute;
    top: 50%;
    right: 6px;
    display: inline-grid;
    width: 26px;
    height: 26px;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 7px;
    background: transparent;
    color: var(--admin-muted);
    cursor: pointer;
    transform: translateY(-50%);
  }

  .admin-logs-filter-clear:hover,
  .admin-logs-filter-clear:focus-visible {
    background: var(--surface-hover);
    color: var(--admin-text);
    outline: none;
  }

  .admin-logs-filter-clear:focus-visible {
    box-shadow: 0 0 0 2px var(--admin-ring);
  }

  :global(.admin-logs-refresh.admin-btn) {
    width: 36px;
    min-width: 36px;
    height: 36px;
    padding: 0;
  }

  .admin-logs-user-cell {
    min-width: 150px;
  }

  .admin-logs-user {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .admin-logs-user-meta {
    display: grid;
    gap: 2px;
    min-width: 0;
  }

  .admin-logs-user-name {
    min-width: 0;
    overflow: hidden;
    color: var(--admin-text);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-logs-user-id {
    color: var(--admin-dim);
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.2;
    white-space: nowrap;
  }

  .admin-logs-user-cell :global(.admin-logs-user-btn.admin-btn) {
    width: 30px;
    height: 30px;
    min-width: 30px;
    min-height: 30px;
    flex-shrink: 0;
    padding: 0;
    border-radius: 7px;
  }

  .admin-logs-user-cell :global(.admin-logs-user-btn svg) {
    width: 14px;
    height: 14px;
  }

  :global(.admin-logs-error-state) {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--admin-text);
  }

  :global(.admin-logs-error-state svg) {
    flex-shrink: 0;
    color: var(--admin-warning);
  }

  @media (max-width: 560px) {
    .admin-logs-toolbar-search {
      grid-template-columns: minmax(0, 1fr) 36px;
    }

    .admin-logs-filter-input {
      grid-column: 1 / -1;
    }
  }
</style>
