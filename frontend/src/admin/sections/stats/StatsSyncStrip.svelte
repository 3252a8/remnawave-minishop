<script lang="ts">
  import * as Card from "$components/ui/card/index.js";
  import type { AdminStats } from "$lib/admin/statsDerivations";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type DateFormatterFn = (value: unknown) => string;

  let {
    at,
    stats,
    fmtDateShort,
  }: {
    at: TranslateFn;
    stats: AdminStats;
    fmtDateShort: DateFormatterFn;
  } = $props();

  function syncStatusLabel(status: unknown): string {
    const value = String(status ?? "").trim();
    const normalized = value.toLowerCase();
    if (!normalized) return "—";
    if (["ok", "success", "succeeded", "completed", "done"].includes(normalized)) {
      return at("stats_sync_status_ok", {}, "OK");
    }
    if (["failed", "error"].includes(normalized)) {
      return at("stats_sync_status_failed", {}, "Failed");
    }
    if (["running", "in_progress", "started"].includes(normalized)) {
      return at("stats_sync_status_running", {}, "Running");
    }
    if (normalized === "never_run") return at("stats_sync_status_never_run", {}, "Not run yet");
    return value;
  }
</script>

<Card.Root>
  <Card.Content class="admin-cn-card-content--flush" style="padding-top:12px;padding-bottom:12px;">
    <div class="admin-sync-strip" style="border:0;background:transparent;padding:0;">
      <span
        ><strong>{at("stats_sync_label", {}, "")}:</strong>
        {syncStatusLabel(stats.panel_sync?.status)}{#if stats.panel_sync?.last_sync_time}{" · "}{at(
            "stats_sync_last",
            {},
            ""
          )}: {fmtDateShort(stats.panel_sync.last_sync_time)}{/if}</span
      >
      {#if stats.panel_sync && (stats.panel_sync.users_processed > 0 || stats.panel_sync.subscriptions_synced > 0)}
        <span
          >{at(
            "stats_sync_processed",
            {
              users: stats.panel_sync.users_processed,
              subs: stats.panel_sync.subscriptions_synced,
            },
            ""
          )}</span
        >
      {/if}
      {#if stats.queue}
        <span
          ><strong>{at("stats_label_queue", {}, "")}:</strong>
          {at(
            "stats_queue_sizes",
            {
              users: stats.queue.user_queue_size ?? 0,
              groups: stats.queue.group_queue_size ?? 0,
            },
            "users {users} · groups {groups}"
          )}</span
        >
      {/if}
    </div>
  </Card.Content>
</Card.Root>
