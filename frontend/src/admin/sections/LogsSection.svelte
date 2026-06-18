<script>
  import { Input } from "$components/ui/index.js";
  import { getContext, onMount } from "svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { RefreshCw, TriangleAlert, User } from "$components/ui/icons.js";

  export let at;
  export let fmtDate;
  export let onOpenUserCard = () => {};

  const logsStore = getContext("logsStore");
  const LOGS_PAGE_SIZE = 50;

  $: ({ logs, logsTotal, logsPage, logsUserFilter, logsLoading, logsError } = $logsStore);

  $: logsPageCount = Math.max(1, Math.ceil(Number(logsTotal || 0) / LOGS_PAGE_SIZE));
  $: logHeaders = [
    at("date", {}, "Дата"),
    at("event", {}, "Событие"),
    at("user_short", {}, "User"),
    at("target_short", {}, "Target"),
    at("content", {}, "Контент"),
  ];

  function userDisplay(entry, kind) {
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

  function userId(entry, kind) {
    return kind === "target" ? entry.target_user_id : entry.user_id;
  }

  onMount(() => {
    logsStore.loadLogs({ refresh: true });
  });
</script>

<div class="admin-toolbar admin-toolbar-card">
  <div class="admin-toolbar-search admin-toolbar-search-actions">
    <Input
      type="search"
      class="input"
      placeholder={at("logs_user_filter_placeholder", {}, "Фильтр по ID пользователя")}
      value={logsUserFilter}
      on:input={(e) => logsStore.setFilter(e.target.value)}
      on:keydown={(e) => e.key === "Enter" && logsStore.setPage(0)}
    />
    <AdminButton
      variant="primary"
      onclick={() => {
        logsStore.setPage(0);
      }}>{at("apply", {}, "Применить")}</AdminButton
    >
    <AdminButton variant="ghost" onclick={() => logsStore.loadLogs({ refresh: true })}>
      <RefreshCw size={14} />
      {at("btn_refresh", {}, "Обновить")}
    </AdminButton>
    <AdminButton
      variant="ghost"
      onclick={() => {
        logsStore.setFilter("");
        logsStore.setPage(0);
      }}>{at("reset", {}, "Сбросить")}</AdminButton
    >
  </div>
  <div class="admin-toolbar-summary">
    <span class="admin-toolbar-field-label">{at("total", {}, "Всего")}</span>
    <strong>{logsTotal}</strong>
  </div>
</div>

<div class="admin-table-wrap">
  {#if logsLoading}
    <AdminTableSkeleton
      headers={logHeaders}
      rows={10}
      widths={["120px", "120px", "160px", "160px", "220px"]}
    />
  {:else if logsError}
    <AdminEmptyState tone="card" class="admin-logs-error-state">
      <TriangleAlert size={18} />
      <span>{logsError}</span>
      <AdminButton variant="ghost" onclick={() => logsStore.loadLogs({ refresh: true })}>
        <RefreshCw size={14} />
        {at("btn_refresh", {}, "Обновить")}
      </AdminButton>
    </AdminEmptyState>
  {:else if !logs.length}
    <AdminEmptyState tone="card"
      ><span class="admin-muted">{at("logs_empty", {}, "Записей нет")}</span></AdminEmptyState
    >
  {:else}
    <AdminTable>
      <thead>
        <tr>
          <th>{at("date", {}, "Дата")}</th>
          <th>{at("event", {}, "Событие")}</th>
          <th>{at("user_short", {}, "User")}</th>
          <th>{at("target_short", {}, "Target")}</th>
          <th>{at("content", {}, "Контент")}</th>
        </tr>
      </thead>
      <tbody>
        {#each logs as entry}
          <tr>
            <td data-label={at("date", {}, "Дата")}>{fmtDate(entry.timestamp)}</td>
            <td class="admin-cell-mono" data-label={at("event", {}, "Событие")}
              >{entry.event_type}</td
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
            <td class="admin-cell-wrap" data-label={at("content", {}, "Контент")}
              >{entry.content || ""}</td
            >
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {/if}
</div>

<AdminPagination
  page={logsPage}
  pageCount={logsPageCount}
  total={logsTotal}
  pageLabel={at("page_short", {}, "Стр.")}
  ofLabel={at("pagination_of", {}, "из")}
  totalLabel={at("total", {}, "Всего")}
  jumpLabel={at("page_short", {}, "Стр.")}
  jumpAriaLabel={at("pagination_jump_aria", {}, "Перейти к странице")}
  goLabel={at("pagination_go", {}, "Перейти")}
  prevLabel={at("back", {}, "Назад")}
  nextLabel={at("next", {}, "Далее")}
  onPageChange={(page) => logsStore.setPage(page)}
/>

<style>
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
</style>
