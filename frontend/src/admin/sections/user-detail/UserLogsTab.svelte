<script lang="ts">
  import { getUsersStore } from "$lib/admin/context";
  import { Tabs } from "$components/ui/primitives.js";
  import { ScrollArea } from "$components/ui/index.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import { RefreshCw } from "$components/ui/icons.js";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { DateFormatter, TranslateFn, UserLogRow } from "./userDetailTypes";

  type Props = {
    at: TranslateFn;
    fmtDate: DateFormatter;
    openedUser?: AdminUser | null;
    userLogsRows?: readonly UserLogRow[];
    userLogsTotal?: number;
    userLogsPage?: number;
    userLogsPageCount?: number;
    userLogsPageSize?: number;
    userLogsLoading?: boolean;
    userLogsLoaded?: boolean;
  };

  let {
    at,
    fmtDate,
    openedUser = null,
    userLogsRows = [],
    userLogsTotal = 0,
    userLogsPage = 0,
    userLogsPageCount = 1,
    userLogsPageSize = 20,
    userLogsLoading = false,
    userLogsLoaded = false,
  }: Props = $props();

  const usersStore = getUsersStore();
</script>

<Tabs.Content value="logs" class="admin-tabs-content admin-user-logs-tab">
  <div class="admin-user-logs-head">
    <div class="admin-subsection-title">
      {at("user_logs_section_title", {}, "User logs")}
    </div>
    <div class="admin-user-logs-meta">
      <span class="admin-muted">{at("total", {}, "Total")}</span>
      <strong>{userLogsTotal}</strong>
      <AdminButton
        size="sm"
        variant="ghost"
        disabled={userLogsLoading}
        onclick={() => usersStore.loadUserLogs(userLogsPage)}
        title={at("refresh", {}, "Refresh")}
      >
        <RefreshCw size={14} />
        {at("refresh", {}, "Refresh")}
      </AdminButton>
    </div>
  </div>

  <ScrollArea class="admin-user-logs-wrap" maxHeight="min(52vh, 460px)">
    {#if userLogsLoading}
      <AdminTableSkeleton
        headers={[at("date", {}, "Date"), at("event", {}, "Event"), at("content", {}, "Content")]}
        rows={6}
        rowHeight={58}
        widths={["140px", "140px", "60%"]}
      />
    {:else if !userLogsRows.length}
      <AdminEmptyState tone="card">
        <span class="admin-muted">{at("logs_empty", {}, "No entries")}</span>
      </AdminEmptyState>
    {:else}
      <AdminTable>
        <thead>
          <tr>
            <th>{at("date", {}, "Date")}</th>
            <th>{at("event", {}, "Event")}</th>
            <th>{at("content", {}, "Content")}</th>
          </tr>
        </thead>
        <tbody>
          {#each userLogsRows as entry (entry.log_id)}
            <tr>
              <td data-label={at("date", {}, "Date")}>{fmtDate(entry.timestamp)}</td>
              <td class="admin-cell-mono" data-label={at("event", {}, "Event")}>
                <span class="admin-user-log-event">
                  <span>{entry.event_type || "—"}</span>
                  {#if entry.is_admin_event}
                    <AdminBadge variant="warning"
                      >{at("user_logs_admin_event", {}, "Admin")}</AdminBadge
                    >
                  {/if}
                  {#if entry.target_user_id && entry.target_user_id !== openedUser?.user_id}
                    <small class="admin-muted">→ {entry.target_user_id}</small>
                  {/if}
                </span>
              </td>
              <td
                class="admin-cell-wrap admin-user-log-content"
                data-label={at("content", {}, "Content")}
              >
                {entry.content || ""}
              </td>
            </tr>
          {/each}
        </tbody>
      </AdminTable>
    {/if}
  </ScrollArea>

  {#if userLogsLoaded && userLogsTotal > userLogsPageSize}
    <AdminPagination
      page={userLogsPage}
      pageCount={userLogsPageCount}
      total={userLogsTotal}
      pageLabel={at("page_short", {}, "Page")}
      ofLabel={at("pagination_of", {}, "of")}
      totalLabel={at("total", {}, "Total")}
      jumpLabel={at("page_short", {}, "Page")}
      jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
      goLabel={at("pagination_go", {}, "Go")}
      prevLabel={at("back", {}, "Back")}
      nextLabel={at("next", {}, "Next")}
      disabled={userLogsLoading}
      onPageChange={(page) => usersStore.setUserLogsPage(page)}
    />
  {/if}
</Tabs.Content>
