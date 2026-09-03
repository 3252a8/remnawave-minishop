<script lang="ts">
  import { onMount } from "svelte";
  import { TableHandler } from "@vincjo/datatables";
  import { getBroadcastStore } from "$lib/admin/context";
  import type { BroadcastHistoryItem } from "$lib/admin/stores/broadcastHistory";
  import { sortAdminRows, type AdminSortColumn } from "$lib/admin/tableSort.js";
  import { Input } from "$components/ui/index.js";
  import { CalendarDays, Trash2 } from "$components/ui/icons.js";
  import {
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminSortableHeader,
    AdminTable,
    AdminTableSkeleton,
  } from "$components/patterns/admin/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { supportMessageImageUrl } from "$lib/messageImage";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { at, currentLang = "en" }: { at: TranslateFn; currentLang?: string } = $props();
  const broadcastStore = getBroadcastStore();
  const HISTORY_PAGE_SIZE = 10;
  const ACTIVE_STATUSES = new Set(["scheduled", "queued", "running"]);
  const historyTable = new TableHandler<BroadcastHistoryItem>([], {
    rowsPerPage: HISTORY_PAGE_SIZE,
  });

  let scheduleDrafts = $state<Record<number, string>>({});
  let scheduleNow = $state(Date.now());
  let selectedBroadcastId = $state<number | null>(null);
  let historySort = $state("created_desc");
  const history = $derived(broadcastStore.broadcastHistory);
  const loading = $derived(Boolean(broadcastStore.broadcastHistoryLoading));
  const selectedBroadcast = $derived(
    history.find((item) => item.broadcastId === selectedBroadcastId) || null
  );
  const minimumScheduledAt = $derived(datetimeLocalFromTimestamp(nextMinute(scheduleNow)));
  const historySortColumns = [
    {
      asc: "id_asc",
      desc: "id_desc",
      defaultDirection: "desc",
      value: (item) => item.broadcastId,
    },
    {
      asc: "status_asc",
      desc: "status_desc",
      defaultDirection: "asc",
      value: (item) => item.status,
    },
    {
      asc: "message_asc",
      desc: "message_desc",
      defaultDirection: "asc",
      value: (item) => messagePreview(item),
    },
    {
      asc: "audience_asc",
      desc: "audience_desc",
      defaultDirection: "asc",
      value: (item) => targetLabel(item.target),
    },
    {
      asc: "channels_asc",
      desc: "channels_desc",
      defaultDirection: "asc",
      value: (item) => item.channels.join(" "),
    },
    {
      asc: "scheduled_asc",
      desc: "scheduled_desc",
      defaultDirection: "desc",
      value: (item) => item.scheduledAt,
    },
    {
      asc: "progress_asc",
      desc: "progress_desc",
      defaultDirection: "desc",
      value: (item) => progress(item),
    },
    {
      asc: "created_asc",
      desc: "created_desc",
      defaultDirection: "desc",
      value: (item) => item.createdAt,
    },
  ] satisfies AdminSortColumn<BroadcastHistoryItem>[];
  const sortedHistory = $derived(sortAdminRows(history, historySort, historySortColumns));
  const historyRows = $derived(historyTable.rows as BroadcastHistoryItem[]);
  const historyHeaders = $derived([
    "ID",
    at("status", {}, "Status"),
    at("broadcast_label_text", {}, "Message Text"),
    at("broadcast_label_audience", {}, "Audience"),
    at("broadcast_channels_label", {}, "Delivery channels"),
    at("broadcast_scheduled_at", {}, "Scheduled"),
    at("broadcast_progress", {}, "Delivery progress"),
    at("broadcast_created_at", {}, "Created"),
  ]);
  const historyMeta = $derived.by(() => {
    const { start, end, total } = historyTable.rowCount;
    return `${start}-${end} / ${total}`;
  });

  $effect(() => {
    historyTable.setRows(sortedHistory);
    if (historyTable.currentPage > (historyTable.pageCount || 1)) {
      historyTable.setPage(historyTable.pageCount || 1);
    }
  });

  $effect(() => {
    if (selectedBroadcastId !== null && !selectedBroadcast) closeDetails();
  });

  onMount(() => {
    void broadcastStore.loadHistory();
    const timer = window.setInterval(() => {
      scheduleNow = Date.now();
      if (document.visibilityState !== "visible") return;
      if (broadcastStore.broadcastHistory.some((item) => ACTIVE_STATUSES.has(item.status))) {
        void broadcastStore.loadHistory();
      }
    }, 3000);
    return () => window.clearInterval(timer);
  });

  function statusLabel(status: string): string {
    const labels: Record<string, [string, string]> = {
      scheduled: ["broadcast_status_scheduled", "Scheduled"],
      queued: ["broadcast_status_queued", "Queued"],
      running: ["broadcast_status_running", "Sending"],
      completed: ["broadcast_status_completed", "Completed"],
      completed_with_errors: ["broadcast_status_completed_with_errors", "Completed with errors"],
      failed: ["broadcast_status_failed", "Failed"],
      cancelled: ["broadcast_status_cancelled", "Cancelled"],
    };
    const [key, fallback] = labels[status] || ["broadcast_status_unknown", status];
    return at(key, {}, fallback);
  }

  function statusTone(status: string): string {
    if (status === "completed") return "success";
    if (status === "failed" || status === "cancelled") return "danger";
    if (status === "completed_with_errors") return "warning";
    return "active";
  }

  function formatDate(value: string | null): string {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString(currentLang);
  }

  function datetimeLocalValue(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return datetimeLocalFromTimestamp(date.getTime());
  }

  function datetimeLocalFromTimestamp(timestamp: number): string {
    const date = new Date(timestamp);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 16);
  }

  function nextMinute(timestamp: number): number {
    return Math.ceil((timestamp + 1) / 60_000) * 60_000;
  }

  function scheduleDraftInvalid(value: string): boolean {
    const date = new Date(value);
    return !value || Number.isNaN(date.getTime()) || date.getTime() <= scheduleNow;
  }

  function editSchedule(item: BroadcastHistoryItem): void {
    scheduleDrafts = {
      ...scheduleDrafts,
      [item.broadcastId]: datetimeLocalValue(item.scheduledAt),
    };
  }

  function stopEditing(broadcastId: number): void {
    const next = { ...scheduleDrafts };
    delete next[broadcastId];
    scheduleDrafts = next;
  }

  async function saveSchedule(item: BroadcastHistoryItem): Promise<void> {
    const value = scheduleDrafts[item.broadcastId] || "";
    if (scheduleDraftInvalid(value)) return;
    if (await broadcastStore.rescheduleBroadcast(item.broadcastId, value)) {
      stopEditing(item.broadcastId);
    }
  }

  async function remove(item: BroadcastHistoryItem): Promise<void> {
    const message =
      item.status === "scheduled"
        ? at(
            "broadcast_delete_scheduled_confirm",
            {},
            "Remove this broadcast and cancel its scheduled delivery?"
          )
        : at("broadcast_delete_confirm", {}, "Remove this broadcast from history?");
    if (typeof window !== "undefined" && !window.confirm(message)) return;
    await broadcastStore.deleteBroadcast(item.broadcastId);
    if (!broadcastStore.broadcastHistory.some((entry) => entry.broadcastId === item.broadcastId)) {
      closeDetails();
    }
  }

  function targetLabel(target: string): string {
    return (
      broadcastStore.BROADCAST_TARGET_OPTIONS.find((option) => option.value === target)?.label ||
      target
    );
  }

  function buttonLabel(button: BroadcastHistoryItem["buttons"][number]): string {
    return button.label || Object.values(button.labels)[0] || button.kind;
  }

  function buttonTarget(button: BroadcastHistoryItem["buttons"][number]): string {
    return button.url || button.promoCode || button.section || "—";
  }

  function completedDeliveries(item: BroadcastHistoryItem): number {
    return item.successfulDeliveries + item.failedDeliveries;
  }

  function progress(item: BroadcastHistoryItem): number {
    if (!item.totalDeliveries) return item.status === "completed" ? 100 : 0;
    return Math.min(100, Math.round((completedDeliveries(item) / item.totalDeliveries) * 100));
  }

  function progressText(item: BroadcastHistoryItem): string {
    return `${completedDeliveries(item)}/${item.totalDeliveries} · ${progress(item)}%`;
  }

  function messagePreview(item: BroadcastHistoryItem): string {
    return Object.values(item.texts).find((text) => text.trim()) || "—";
  }

  function setHistorySort(sort: string): void {
    historySort = sort;
    historyTable.setPage(1);
  }

  function openDetails(item: BroadcastHistoryItem): void {
    selectedBroadcastId = item.broadcastId;
  }

  function closeDetails(): void {
    if (selectedBroadcastId !== null) stopEditing(selectedBroadcastId);
    selectedBroadcastId = null;
  }

  function handleRowKeydown(event: KeyboardEvent, item: BroadcastHistoryItem): void {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openDetails(item);
  }

  function reschedulable(item: BroadcastHistoryItem): boolean {
    return (item.status === "scheduled" || item.status === "queued") && !item.startedAt;
  }
</script>

<section class="admin-card broadcast-history" aria-live="polite">
  <header class="admin-card-head broadcast-history-head">
    <div>
      <h3>{at("broadcast_history_title", {}, "Broadcast history")}</h3>
      <small
        >{at("broadcast_history_subtitle", {}, "Content, schedule and live delivery status")}</small
      >
    </div>
    {#if loading}
      <span class="broadcast-history-sync"
        >{at("broadcast_history_refreshing", {}, "Updating…")}</span
      >
    {/if}
  </header>
  <div class="admin-card-body broadcast-history-body">
    {#if loading && !history.length}
      <div class="admin-table-wrap">
        <AdminTableSkeleton
          headers={historyHeaders}
          rows={5}
          rowHeight={64}
          widths={[
            "64px",
            "130px",
            "minmax(220px, 1fr)",
            "150px",
            "130px",
            "170px",
            "130px",
            "170px",
          ]}
        />
      </div>
    {:else if !history.length}
      <AdminEmptyState tone="card">
        <span class="admin-muted">{at("broadcast_history_empty", {}, "No broadcasts yet")}</span>
      </AdminEmptyState>
    {:else}
      <div class="admin-table-wrap">
        <AdminTable class="broadcast-history-table">
          <thead>
            <tr>
              <AdminSortableHeader
                label="ID"
                column={historySortColumns[0]}
                currentSort={historySort}
                {at}
                onSort={setHistorySort}
              />
              <AdminSortableHeader
                label={at("status", {}, "Status")}
                column={historySortColumns[1]}
                currentSort={historySort}
                {at}
                onSort={setHistorySort}
              />
              <AdminSortableHeader
                label={at("broadcast_label_text", {}, "Message Text")}
                column={historySortColumns[2]}
                currentSort={historySort}
                {at}
                onSort={setHistorySort}
              />
              <AdminSortableHeader
                label={at("broadcast_label_audience", {}, "Audience")}
                column={historySortColumns[3]}
                currentSort={historySort}
                {at}
                onSort={setHistorySort}
              />
              <AdminSortableHeader
                label={at("broadcast_channels_label", {}, "Delivery channels")}
                column={historySortColumns[4]}
                currentSort={historySort}
                {at}
                onSort={setHistorySort}
              />
              <AdminSortableHeader
                label={at("broadcast_scheduled_at", {}, "Scheduled")}
                column={historySortColumns[5]}
                currentSort={historySort}
                {at}
                onSort={setHistorySort}
              />
              <AdminSortableHeader
                label={at("broadcast_progress", {}, "Delivery progress")}
                column={historySortColumns[6]}
                currentSort={historySort}
                {at}
                onSort={setHistorySort}
              />
              <AdminSortableHeader
                label={at("broadcast_created_at", {}, "Created")}
                column={historySortColumns[7]}
                currentSort={historySort}
                {at}
                onSort={setHistorySort}
              />
            </tr>
          </thead>
          <tbody>
            {#each historyRows as item (item.broadcastId)}
              <tr
                class="broadcast-history-row"
                role="button"
                tabindex="0"
                aria-haspopup="dialog"
                aria-label={at(
                  "broadcast_details_open",
                  { id: item.broadcastId },
                  `Open details for broadcast #${item.broadcastId}`
                )}
                onclick={() => openDetails(item)}
                onkeydown={(event) => handleRowKeydown(event, item)}
              >
                <td class="admin-cell-id" data-label="ID">#{item.broadcastId}</td>
                <td data-label={at("status", {}, "Status")}
                  ><span class={`broadcast-status broadcast-status-${statusTone(item.status)}`}
                    >{statusLabel(item.status)}</span
                  ></td
                >
                <td
                  class="admin-cell-wrap broadcast-history-message-preview"
                  data-label={at("broadcast_label_text", {}, "Message Text")}
                  title={messagePreview(item)}>{messagePreview(item)}</td
                >
                <td data-label={at("broadcast_label_audience", {}, "Audience")}
                  >{targetLabel(item.target)}</td
                >
                <td data-label={at("broadcast_channels_label", {}, "Delivery channels")}
                  >{item.channels.join(" · ") || "—"}</td
                >
                <td data-label={at("broadcast_scheduled_at", {}, "Scheduled")}
                  >{formatDate(item.scheduledAt)}</td
                >
                <td data-label={at("broadcast_progress", {}, "Delivery progress")}
                  >{progressText(item)}</td
                >
                <td data-label={at("broadcast_created_at", {}, "Created")}
                  >{formatDate(item.createdAt)}</td
                >
              </tr>
            {/each}
          </tbody>
        </AdminTable>
      </div>
      {#if history.length > HISTORY_PAGE_SIZE}
        <AdminPagination
          meta={historyMeta}
          table={historyTable}
          pageLabel={at("page_short", {}, "Page")}
          ofLabel={at("pagination_of", {}, "of")}
          jumpLabel={at("page_short", {}, "Page")}
          jumpAriaLabel={at("pagination_jump_aria", {}, "Go to page")}
          goLabel={at("pagination_go", {}, "Go")}
          prevLabel={at("pagination_prev", {}, "Back")}
          nextLabel={at("pagination_next", {}, "Next")}
        />
      {/if}
    {/if}
  </div>
</section>

<Dialog
  open={Boolean(selectedBroadcast)}
  title={selectedBroadcast
    ? at(
        "broadcast_details_title",
        { id: selectedBroadcast.broadcastId },
        `Broadcast #${selectedBroadcast.broadcastId}`
      )
    : ""}
  description={selectedBroadcast
    ? `${statusLabel(selectedBroadcast.status)} · ${targetLabel(selectedBroadcast.target)}`
    : ""}
  closeLabel={at("close", {}, "Close")}
  onclose={closeDetails}
  class="admin-dialog admin-broadcast-dialog"
>
  {#if selectedBroadcast}
    <div class="broadcast-detail-card">
      <div class="broadcast-detail-status-row">
        <span class={`broadcast-status broadcast-status-${statusTone(selectedBroadcast.status)}`}
          >{statusLabel(selectedBroadcast.status)}</span
        >
        <span class="broadcast-history-id">#{selectedBroadcast.broadcastId}</span>
      </div>

      <dl class="broadcast-detail-meta">
        <div>
          <dt>{at("broadcast_label_audience", {}, "Audience")}</dt>
          <dd>{targetLabel(selectedBroadcast.target)}</dd>
        </div>
        <div>
          <dt>{at("broadcast_channels_label", {}, "Delivery channels")}</dt>
          <dd>{selectedBroadcast.channels.join(" · ") || "—"}</dd>
        </div>
        <div>
          <dt>{at("broadcast_recipients", {}, "Recipients")}</dt>
          <dd>{selectedBroadcast.recipientCount}</dd>
        </div>
        {#if selectedBroadcast.channels.includes("telegram")}
          <div>
            <dt>
              {at("broadcast_exclude_blocked_telegram", {}, "Skip users who blocked the bot")}
            </dt>
            <dd>
              {selectedBroadcast.excludeBlockedTelegram ? at("yes", {}, "Yes") : at("no", {}, "No")}
            </dd>
          </div>
        {/if}
        <div>
          <dt>{at("broadcast_created_at", {}, "Created")}</dt>
          <dd>{formatDate(selectedBroadcast.createdAt)}</dd>
        </div>
        <div>
          <dt>{at("broadcast_scheduled_at", {}, "Scheduled")}</dt>
          <dd>{formatDate(selectedBroadcast.scheduledAt)}</dd>
        </div>
        {#if selectedBroadcast.startedAt}
          <div>
            <dt>{at("broadcast_started_at", {}, "Started")}</dt>
            <dd>{formatDate(selectedBroadcast.startedAt)}</dd>
          </div>
        {/if}
        {#if selectedBroadcast.finishedAt}
          <div>
            <dt>{at("broadcast_finished_at", {}, "Finished")}</dt>
            <dd>{formatDate(selectedBroadcast.finishedAt)}</dd>
          </div>
        {/if}
      </dl>

      <div class="broadcast-progress" class:is-running={selectedBroadcast.status === "running"}>
        <div class="broadcast-progress-label">
          <span>{at("broadcast_progress", {}, "Delivery progress")}</span><b
            >{progressText(selectedBroadcast)}</b
          >
        </div>
        <div class="broadcast-progress-track">
          <span style={`width:${progress(selectedBroadcast)}%`}></span>
        </div>
        <div class="broadcast-progress-stats">
          {#if selectedBroadcast.channels.includes("telegram")}
            <span
              >Telegram: {selectedBroadcast.telegramSent} ✓ · {selectedBroadcast.telegramFailed} ×</span
            >
          {/if}
          {#if selectedBroadcast.channels.includes("email")}
            <span>Email: {selectedBroadcast.emailSent} ✓ · {selectedBroadcast.emailFailed} ×</span>
          {/if}
        </div>
      </div>

      <div class="broadcast-history-texts">
        {#each Object.entries(selectedBroadcast.texts) as [language, text]}
          <div class="broadcast-history-text">
            <span class="broadcast-language-chip">{language.toUpperCase()}</span>
            <p>{text}</p>
          </div>
        {/each}
      </div>

      {#if selectedBroadcast.imageId}
        <img
          class="broadcast-history-image"
          src={supportMessageImageUrl(selectedBroadcast.imageId, true)}
          alt={at("message_image_alt", {}, "Attached image")}
          loading="lazy"
        />
      {/if}

      {#if selectedBroadcast.emailSubjects && Object.keys(selectedBroadcast.emailSubjects).length}
        <div class="broadcast-history-subjects">
          <b>{at("broadcast_email_subject_label", {}, "Email subject")}</b>
          {#each Object.entries(selectedBroadcast.emailSubjects) as [language, subject]}
            <span>{language.toUpperCase()}: {subject}</span>
          {/each}
        </div>
      {/if}

      {#if selectedBroadcast.buttons.length}
        <div class="broadcast-history-buttons">
          <b>{at("broadcast_buttons_label", {}, "Buttons")}</b>
          {#each selectedBroadcast.buttons as button}
            <span class="broadcast-history-button"
              >{buttonLabel(button)} <small>→ {buttonTarget(button)}</small></span
            >
          {/each}
        </div>
      {/if}

      {#if selectedBroadcast.lastError}
        <div class="broadcast-history-error">{selectedBroadcast.lastError}</div>
      {/if}

      {#if reschedulable(selectedBroadcast) && scheduleDrafts[selectedBroadcast.broadcastId] !== undefined}
        <div class="broadcast-reschedule-row">
          <Input
            class={scheduleDraftInvalid(scheduleDrafts[selectedBroadcast.broadcastId])
              ? "input-error"
              : ""}
            type="datetime-local"
            value={scheduleDrafts[selectedBroadcast.broadcastId]}
            min={minimumScheduledAt}
            aria-label={at("broadcast_scheduled_at", {}, "Scheduled")}
            aria-invalid={scheduleDraftInvalid(scheduleDrafts[selectedBroadcast.broadcastId])}
            oninput={(event) =>
              (scheduleDrafts[selectedBroadcast.broadcastId] = (
                event.currentTarget as HTMLInputElement
              ).value)}
          />
          <AdminButton
            size="sm"
            variant="primary"
            disabled={scheduleDraftInvalid(scheduleDrafts[selectedBroadcast.broadcastId])}
            onclick={() => saveSchedule(selectedBroadcast)}
            >{at("broadcast_reschedule_save", {}, "Update")}</AdminButton
          >
          <AdminButton
            size="sm"
            variant="ghost"
            onclick={() => stopEditing(selectedBroadcast.broadcastId)}
            >{at("btn_cancel", {}, "Cancel")}</AdminButton
          >
          {#if scheduleDraftInvalid(scheduleDrafts[selectedBroadcast.broadcastId])}
            <small class="admin-field-error broadcast-reschedule-error" role="alert"
              >{at("broadcast_schedule_future", {}, "The send time must be in the future")}</small
            >
          {/if}
        </div>
      {/if}

      <div class="broadcast-history-actions">
        {#if reschedulable(selectedBroadcast)}
          <AdminButton size="sm" variant="ghost" onclick={() => editSchedule(selectedBroadcast)}
            ><CalendarDays size={14} />{at("broadcast_reschedule", {}, "Change time")}</AdminButton
          >
        {/if}
        <AdminButton size="sm" variant="ghost" onclick={() => remove(selectedBroadcast)}
          ><Trash2 size={14} />{selectedBroadcast.status === "scheduled"
            ? at("broadcast_cancel_scheduled", {}, "Cancel and remove")
            : at("btn_delete", {}, "Delete")}</AdminButton
        >
      </div>
    </div>
  {/if}
</Dialog>

<style>
  .broadcast-history {
    margin-top: 16px;
  }
  .broadcast-history-head {
    align-items: flex-start;
  }
  .broadcast-history-head > div {
    display: grid;
    gap: 3px;
  }
  .broadcast-history-sync {
    color: var(--accent);
    font-size: 12px;
  }
  .broadcast-history-body {
    display: grid;
    gap: 12px;
  }
  :global(.broadcast-history-table) {
    min-width: 1120px;
  }
  :global(.broadcast-history-table tbody tr.broadcast-history-row) {
    cursor: pointer;
  }
  :global(.broadcast-history-table tbody tr.broadcast-history-row:hover),
  :global(.broadcast-history-table tbody tr.broadcast-history-row:focus-visible) {
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }
  :global(.broadcast-history-table tbody tr.broadcast-history-row:focus-visible) {
    outline: 2px solid var(--admin-ring);
    outline-offset: -2px;
  }
  .broadcast-history-message-preview {
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .broadcast-status,
  .broadcast-language-chip {
    display: inline-flex;
    width: fit-content;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }
  .broadcast-status {
    padding: 4px 8px;
    white-space: nowrap;
  }
  .broadcast-status-active {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    color: var(--accent);
  }
  .broadcast-status-success {
    background: var(--success-soft);
    color: var(--success-text);
  }
  .broadcast-status-warning {
    background: var(--warning-soft);
    color: var(--warning-text);
  }
  .broadcast-status-danger {
    background: var(--danger-soft);
    color: var(--danger-text);
  }
  :global(.admin-broadcast-dialog) {
    width: min(760px, calc(100vw - 24px));
  }
  .broadcast-detail-card {
    display: grid;
    gap: 16px;
    padding: 16px;
  }
  .broadcast-detail-status-row,
  .broadcast-progress-label,
  .broadcast-history-actions,
  .broadcast-reschedule-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .broadcast-detail-status-row,
  .broadcast-progress-label {
    justify-content: space-between;
  }
  .broadcast-history-id {
    color: var(--admin-text-dim);
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 11px;
  }
  .broadcast-detail-meta {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px 16px;
    margin: 0;
  }
  .broadcast-detail-meta div {
    min-width: 0;
  }
  .broadcast-detail-meta dt {
    color: var(--admin-text-dim);
    font-size: 10px;
    text-transform: uppercase;
  }
  .broadcast-detail-meta dd {
    margin: 3px 0 0;
    color: var(--admin-text);
    font-size: 13px;
    overflow-wrap: anywhere;
  }
  .broadcast-history-image {
    display: block;
    width: min(100%, 420px);
    max-height: 320px;
    border-radius: 10px;
    object-fit: contain;
  }
  .broadcast-history-subjects,
  .broadcast-history-buttons,
  .broadcast-progress-stats {
    display: grid;
    gap: 5px;
    color: var(--admin-text-muted);
    font-size: 12px;
  }
  .broadcast-history-texts {
    display: grid;
    gap: 8px;
  }
  .broadcast-history-text {
    display: grid;
    gap: 5px;
    padding: 10px;
    border-radius: 10px;
    background: var(--admin-surface-2);
  }
  .broadcast-language-chip {
    padding: 2px 6px;
    background: color-mix(in srgb, var(--accent) 14%, transparent);
    color: var(--accent);
  }
  .broadcast-history-text p {
    max-height: 16rem;
    margin: 0;
    overflow: auto;
    color: var(--admin-text);
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .broadcast-history-button {
    padding: 6px 8px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
    color: var(--admin-text);
    overflow-wrap: anywhere;
  }
  .broadcast-history-button small {
    color: var(--admin-text-muted);
  }
  .broadcast-progress {
    display: grid;
    gap: 7px;
  }
  .broadcast-progress-label {
    font-size: 12px;
  }
  .broadcast-progress-track {
    height: 6px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--admin-surface-2);
  }
  .broadcast-progress-track span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--accent);
    transition: width 0.3s ease;
  }
  .broadcast-progress.is-running .broadcast-progress-track span {
    background: linear-gradient(90deg, var(--accent), color-mix(in srgb, var(--accent) 35%, white));
    background-size: 180% 100%;
    animation: broadcast-progress-pulse 1.2s linear infinite;
  }
  .broadcast-progress-stats {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  }
  .broadcast-history-error {
    padding: 8px 10px;
    border-radius: 8px;
    background: color-mix(in srgb, #ff6577 10%, transparent);
    color: #ff8794;
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  .broadcast-reschedule-row,
  .broadcast-history-actions {
    flex-wrap: wrap;
  }
  .broadcast-reschedule-row {
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    background: var(--admin-surface-2);
  }
  .broadcast-reschedule-row :global(input) {
    width: auto;
    min-width: 190px;
    flex: 1 1 190px;
  }
  .broadcast-reschedule-error {
    width: 100%;
    flex: 1 0 100%;
    line-height: 1.35;
  }
  .broadcast-history-actions {
    justify-content: flex-end;
    padding-top: 12px;
    border-top: 1px solid var(--admin-border);
  }
  @keyframes broadcast-progress-pulse {
    to {
      background-position: -180% 0;
    }
  }

  @media (max-width: 700px) {
    :global(.broadcast-history-table) {
      min-width: 0;
    }
    .broadcast-history-message-preview {
      max-width: none;
      white-space: normal;
    }
    .broadcast-detail-card {
      padding: 12px;
    }
    .broadcast-detail-meta {
      grid-template-columns: minmax(0, 1fr);
    }
    .broadcast-reschedule-row :global(input) {
      min-width: 0;
      flex-basis: 100%;
    }
    .broadcast-history-actions :global(button) {
      flex: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .broadcast-progress.is-running .broadcast-progress-track span {
      animation: none;
    }
    .broadcast-progress-track span {
      transition: none;
    }
  }
</style>
