<script>
  import { getContext, onMount } from "svelte";
  import { AdminButton, AdminEmptyState, AdminPagination, AdminTable, AdminTableSkeleton } from "$components/patterns/admin/index.js";

  export let at;
  export let fmtDate;

  const logsStore = getContext("logsStore");

  $: ({
    logs,
    logsTotal,
    logsPage,
    logsUserFilter,
    logsLoading,
  } = $logsStore);

  $: logsHasMore = logs.length > 0 && logsTotal > (logsPage + 1) * 50; // 50 is LOGS_PAGE_SIZE
  $: logHeaders = [
    at("date", {}, "Дата"),
    at("event", {}, "Событие"),
    at("user_short", {}, "User"),
    at("target_short", {}, "Target"),
    at("content", {}, "Контент"),
  ];

  onMount(() => {
    logsStore.loadLogs();
  });
</script>

<div class="admin-toolbar admin-toolbar-card">
  <div class="admin-toolbar-search admin-toolbar-search-actions">
    <input
      type="search"
      class="input"
      placeholder={at("logs_user_filter_placeholder", {}, "Фильтр по ID пользователя")}
      value={logsUserFilter}
      on:input={(e) => logsStore.setFilter(e.target.value)}
      on:keydown={(e) => e.key === "Enter" && (logsStore.setPage(0))}
    />
    <AdminButton variant="primary" onclick={() => { logsStore.setPage(0); }}>{at("apply", {}, "Применить")}</AdminButton>
    <AdminButton variant="ghost" onclick={() => { logsStore.setFilter(""); logsStore.setPage(0); }}>{at("reset", {}, "Сбросить")}</AdminButton>
  </div>
  <div class="admin-toolbar-summary">
    <span class="admin-toolbar-field-label">{at("total", {}, "Всего")}</span>
    <strong>{logsTotal}</strong>
  </div>
</div>

<div class="admin-table-wrap">
  {#if logsLoading}
    <AdminTableSkeleton headers={logHeaders} rows={10} widths={["120px", "120px", "58px", "58px", "220px"]} />
  {:else if !logs.length}
    <AdminEmptyState tone="card"><span class="admin-muted">{at("logs_empty", {}, "Записей нет")}</span></AdminEmptyState>
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
            <td class="admin-cell-mono" data-label={at("event", {}, "Событие")}>{entry.event_type}</td>
            <td class="admin-cell-mono" data-label={at("user_short", {}, "User")}>{entry.user_id || "—"}</td>
            <td class="admin-cell-mono" data-label={at("target_short", {}, "Target")}>{entry.target_user_id || "—"}</td>
            <td class="admin-cell-wrap" data-label={at("content", {}, "Контент")}>{entry.content || ""}</td>
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {/if}
</div>

<AdminPagination
  meta={`${at("page_short", {}, "Стр.")} ${logsPage + 1}`}
  prevLabel={at("back", {}, "Назад")}
  nextLabel={at("next", {}, "Далее")}
  prevDisabled={logsPage === 0}
  nextDisabled={!logsHasMore}
  onPrev={() => { logsStore.setPage(Math.max(0, logsPage - 1)); }}
  onNext={() => { logsStore.setPage(logsPage + 1); }}
/>
