<script lang="ts">
  import { onMount } from "svelte";
  import { getBroadcastStore } from "$lib/admin/context";
  import type { BroadcastHistoryItem } from "$lib/admin/stores/broadcastHistory";
  import { Input } from "$components/ui/index.js";
  import { CalendarDays, Trash2 } from "$components/ui/icons.js";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { supportMessageImageUrl } from "$lib/messageImage";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let { at, currentLang = "en" }: { at: TranslateFn; currentLang?: string } = $props();
  const broadcastStore = getBroadcastStore();
  let scheduleDrafts = $state<Record<number, string>>({});
  let scheduleNow = $state(Date.now());
  const history = $derived(broadcastStore.broadcastHistory);
  const loading = $derived(Boolean(broadcastStore.broadcastHistoryLoading));
  const minimumScheduledAt = $derived(datetimeLocalFromTimestamp(nextMinute(scheduleNow)));

  const ACTIVE_STATUSES = new Set(["scheduled", "queued", "running"]);

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

  function progress(item: BroadcastHistoryItem): number {
    if (!item.totalDeliveries) return item.status === "completed" ? 100 : 0;
    return Math.min(
      100,
      Math.round(((item.successfulDeliveries + item.failedDeliveries) / item.totalDeliveries) * 100)
    );
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
  <div class="admin-card-body">
    {#if !history.length && !loading}
      <div class="broadcast-history-empty">
        {at("broadcast_history_empty", {}, "No broadcasts yet")}
      </div>
    {:else}
      <div class="broadcast-history-grid">
        {#each history as item, index (item.broadcastId)}
          <article class="broadcast-history-card" style={`--history-index:${Math.min(index, 8)}`}>
            <div class="broadcast-history-card-head">
              <span class={`broadcast-status broadcast-status-${statusTone(item.status)}`}>
                {statusLabel(item.status)}
              </span>
              <span class="broadcast-history-id">#{item.broadcastId}</span>
            </div>

            <div class="broadcast-history-meta">
              <span
                >{at("broadcast_label_audience", {}, "Audience")}:
                <b>{targetLabel(item.target)}</b></span
              >
              <span
                >{at("broadcast_channels_label", {}, "Delivery channels")}:
                <b>{item.channels.join(" · ")}</b></span
              >
            </div>

            <div class="broadcast-history-texts">
              {#each Object.entries(item.texts) as [language, text]}
                <div class="broadcast-history-text">
                  <span class="broadcast-language-chip">{language.toUpperCase()}</span>
                  <p>{text}</p>
                </div>
              {/each}
            </div>

            {#if item.imageId}
              <img
                class="broadcast-history-image"
                src={supportMessageImageUrl(item.imageId, true)}
                alt={at("message_image_alt", {}, "Attached image")}
                loading="lazy"
              />
            {/if}

            {#if item.emailSubjects && Object.keys(item.emailSubjects).length}
              <div class="broadcast-history-subjects">
                <b>{at("broadcast_email_subject_label", {}, "Email subject")}</b>
                {#each Object.entries(item.emailSubjects) as [language, subject]}
                  <span>{language.toUpperCase()}: {subject}</span>
                {/each}
              </div>
            {/if}

            {#if item.buttons.length}
              <div class="broadcast-history-buttons">
                <b>{at("broadcast_buttons_label", {}, "Buttons")}</b>
                {#each item.buttons as button}
                  <span class="broadcast-history-button">
                    {buttonLabel(button)} <small>→ {buttonTarget(button)}</small>
                  </span>
                {/each}
              </div>
            {/if}

            <div class="broadcast-progress" class:is-running={item.status === "running"}>
              <div class="broadcast-progress-label">
                <span>{at("broadcast_progress", {}, "Delivery progress")}</span>
                <b>{item.successfulDeliveries + item.failedDeliveries}/{item.totalDeliveries}</b>
              </div>
              <div class="broadcast-progress-track">
                <span style={`width:${progress(item)}%`}></span>
              </div>
              <div class="broadcast-progress-stats">
                <span>{at("broadcast_recipients", {}, "Recipients")}: {item.recipientCount}</span>
                {#if item.channels.includes("telegram")}
                  <span>Telegram: {item.telegramSent} ✓ · {item.telegramFailed} ×</span>
                {/if}
                {#if item.channels.includes("email")}
                  <span>Email: {item.emailSent} ✓ · {item.emailFailed} ×</span>
                {/if}
              </div>
            </div>

            <dl class="broadcast-history-dates">
              <div>
                <dt>{at("broadcast_created_at", {}, "Created")}</dt>
                <dd>{formatDate(item.createdAt)}</dd>
              </div>
              <div>
                <dt>{at("broadcast_scheduled_at", {}, "Scheduled")}</dt>
                <dd>{formatDate(item.scheduledAt)}</dd>
              </div>
              {#if item.startedAt}
                <div>
                  <dt>{at("broadcast_started_at", {}, "Started")}</dt>
                  <dd>{formatDate(item.startedAt)}</dd>
                </div>
              {/if}
              {#if item.finishedAt}
                <div>
                  <dt>{at("broadcast_finished_at", {}, "Finished")}</dt>
                  <dd>{formatDate(item.finishedAt)}</dd>
                </div>
              {/if}
            </dl>

            {#if item.lastError}
              <div class="broadcast-history-error">{item.lastError}</div>
            {/if}

            {#if scheduleDrafts[item.broadcastId] !== undefined}
              <div class="broadcast-reschedule-row">
                <Input
                  class={scheduleDraftInvalid(scheduleDrafts[item.broadcastId])
                    ? "input-error"
                    : ""}
                  type="datetime-local"
                  value={scheduleDrafts[item.broadcastId]}
                  min={minimumScheduledAt}
                  aria-label={at("broadcast_scheduled_at", {}, "Scheduled")}
                  aria-invalid={scheduleDraftInvalid(scheduleDrafts[item.broadcastId])}
                  oninput={(event) =>
                    (scheduleDrafts[item.broadcastId] = (
                      event.currentTarget as HTMLInputElement
                    ).value)}
                />
                <AdminButton
                  size="sm"
                  variant="primary"
                  disabled={scheduleDraftInvalid(scheduleDrafts[item.broadcastId])}
                  onclick={() => saveSchedule(item)}
                >
                  {at("broadcast_reschedule_save", {}, "Update")}
                </AdminButton>
                <AdminButton
                  size="sm"
                  variant="ghost"
                  onclick={() => stopEditing(item.broadcastId)}
                >
                  {at("btn_cancel", {}, "Cancel")}
                </AdminButton>
                {#if scheduleDraftInvalid(scheduleDrafts[item.broadcastId])}
                  <small class="admin-field-error broadcast-reschedule-error" role="alert">
                    {at("broadcast_schedule_future", {}, "The send time must be in the future")}
                  </small>
                {/if}
              </div>
            {/if}

            <div class="broadcast-history-actions">
              {#if item.status === "scheduled" || item.status === "queued"}
                <AdminButton size="sm" variant="ghost" onclick={() => editSchedule(item)}>
                  <CalendarDays size={14} />
                  {at("broadcast_reschedule", {}, "Change time")}
                </AdminButton>
              {/if}
              <AdminButton size="sm" variant="ghost" onclick={() => remove(item)}>
                <Trash2 size={14} />
                {item.status === "scheduled"
                  ? at("broadcast_cancel_scheduled", {}, "Cancel and remove")
                  : at("btn_delete", {}, "Delete")}
              </AdminButton>
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </div>
</section>

<style>
  .broadcast-history-image {
    display: block;
    width: min(100%, 420px);
    max-height: 320px;
    border-radius: 10px;
    object-fit: contain;
  }

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

  .broadcast-history-empty {
    padding: 28px 16px;
    border: 1px dashed var(--admin-border);
    border-radius: 12px;
    color: var(--admin-text-muted);
    text-align: center;
  }

  .broadcast-history-grid {
    column-width: 330px;
    column-gap: 14px;
  }

  .broadcast-history-card {
    display: inline-grid;
    width: 100%;
    margin: 0 0 14px;
    padding: 14px;
    break-inside: avoid;
    gap: 12px;
    box-sizing: border-box;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface-2);
    box-shadow: 0 10px 28px color-mix(in srgb, #000 18%, transparent);
    animation: broadcast-card-in 0.34s ease both;
    animation-delay: calc(var(--history-index) * 32ms);
  }

  .broadcast-history-card-head,
  .broadcast-progress-label,
  .broadcast-history-actions,
  .broadcast-reschedule-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .broadcast-history-card-head,
  .broadcast-progress-label {
    justify-content: space-between;
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
  }

  .broadcast-status-active {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    color: var(--accent);
  }

  .broadcast-status-success {
    background: color-mix(in srgb, #34c77b 18%, transparent);
    color: #55d895;
  }

  .broadcast-status-warning {
    background: color-mix(in srgb, #f4b740 18%, transparent);
    color: #f4b740;
  }

  .broadcast-status-danger {
    background: color-mix(in srgb, #ff6577 17%, transparent);
    color: #ff7c8b;
  }

  .broadcast-history-id {
    color: var(--admin-text-dim);
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 11px;
  }

  .broadcast-history-meta,
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
    background: var(--admin-surface);
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
    background: var(--admin-surface);
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
    grid-template-columns: repeat(auto-fit, minmax(115px, 1fr));
  }

  .broadcast-history-dates {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 7px 10px;
    margin: 0;
  }

  .broadcast-history-dates div {
    min-width: 0;
  }

  .broadcast-history-dates dt {
    color: var(--admin-text-dim);
    font-size: 10px;
    text-transform: uppercase;
  }

  .broadcast-history-dates dd {
    margin: 2px 0 0;
    color: var(--admin-text-muted);
    font-size: 11px;
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
    padding-top: 3px;
    border-top: 1px solid var(--admin-border);
  }

  @keyframes broadcast-card-in {
    from {
      opacity: 0;
      transform: translateY(8px) scale(0.99);
    }
    to {
      opacity: 1;
      transform: none;
    }
  }

  @keyframes broadcast-progress-pulse {
    to {
      background-position: -180% 0;
    }
  }

  @media (max-width: 700px) {
    .broadcast-history-grid {
      column-count: 1;
      column-width: auto;
    }

    .broadcast-history-card {
      padding: 12px;
      border-radius: 12px;
    }

    .broadcast-history-dates {
      grid-template-columns: 1fr;
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
    .broadcast-history-card,
    .broadcast-progress.is-running .broadcast-progress-track span {
      animation: none;
    }

    .broadcast-progress-track span {
      transition: none;
    }
  }
</style>
