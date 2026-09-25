<script lang="ts">
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import type { BroadcastHistoryItem } from "$lib/admin/stores/broadcastHistory";
  import {
    broadcastFailureKind,
    type BroadcastFailure,
    type BroadcastFailuresPage,
  } from "$lib/admin/stores/broadcastFailures";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  let {
    open,
    broadcast,
    currentLang,
    at,
    loadFailures,
    onclose,
  }: {
    open: boolean;
    broadcast: BroadcastHistoryItem | null;
    currentLang: string;
    at: TranslateFn;
    loadFailures: (broadcastId: number, offset: number) => Promise<BroadcastFailuresPage>;
    onclose: () => void;
  } = $props();

  let failures = $state<BroadcastFailure[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let failedToLoad = $state(false);
  let requestVersion = 0;

  $effect(() => {
    const broadcastId = open ? broadcast?.broadcastId : null;
    const version = ++requestVersion;
    failures = [];
    total = 0;
    failedToLoad = false;
    if (broadcastId) void loadPage(broadcastId, 0, version);
  });

  async function loadPage(broadcastId: number, offset: number, version: number): Promise<void> {
    loading = true;
    failedToLoad = false;
    try {
      const page = await loadFailures(broadcastId, offset);
      if (version !== requestVersion) return;
      failures = offset === 0 ? page.failures : [...failures, ...page.failures];
      total = page.total;
    } catch {
      if (version === requestVersion) failedToLoad = true;
    } finally {
      if (version === requestVersion) loading = false;
    }
  }

  function loadMore(): void {
    if (!broadcast || loading) return;
    void loadPage(broadcast.broadcastId, failures.length, requestVersion);
  }

  function reasonTitle(failure: BroadcastFailure): string {
    const kind = broadcastFailureKind(failure.error, failure.channel);
    const titles = {
      blocked: ["broadcast_failure_blocked", "Bot blocked by recipient"],
      unavailable: ["broadcast_failure_unavailable", "Telegram chat unavailable"],
      rate_limit: ["broadcast_failure_rate_limit", "Telegram rate limit"],
      content: ["broadcast_failure_content", "Message rejected"],
      email: ["broadcast_failure_email", "Email delivery failed"],
      telegram: ["broadcast_failure_telegram", "Telegram delivery failed"],
    } as const;
    const [key, fallback] = titles[kind];
    return at(key, {}, fallback);
  }

  function reasonHint(failure: BroadcastFailure): string {
    const kind = broadcastFailureKind(failure.error, failure.channel);
    const hints = {
      blocked: [
        "broadcast_failure_blocked_hint",
        "Telegram reported a block during this send. The bot cannot deliver to this recipient.",
      ],
      unavailable: [
        "broadcast_failure_unavailable_hint",
        "The chat cannot receive this message; the recipient may need to start the bot again.",
      ],
      rate_limit: [
        "broadcast_failure_rate_limit_hint",
        "Telegram rejected this attempt because of a sending limit.",
      ],
      content: [
        "broadcast_failure_content_hint",
        "Telegram rejected the rendered message. Check its length and formatting.",
      ],
      email: [
        "broadcast_failure_email_hint",
        "The email service did not accept this delivery. Check its response below.",
      ],
      telegram: [
        "broadcast_failure_telegram_hint",
        "Telegram did not accept this delivery. Check its response below.",
      ],
    } as const;
    const [key, fallback] = hints[kind];
    return at(key, {}, fallback);
  }

  function formatDate(value: string | null): string {
    if (!value) return "";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleString(currentLang);
  }
</script>

<Dialog
  {open}
  title={broadcast
    ? at(
        "broadcast_failures_title",
        { id: broadcast.broadcastId },
        `Delivery errors for #${broadcast.broadcastId}`
      )
    : ""}
  description={broadcast
    ? at(
        "broadcast_failures_count",
        { count: broadcast.failedDeliveries },
        `${broadcast.failedDeliveries} failed deliveries`
      )
    : ""}
  closeLabel={at("close", {}, "Close")}
  {onclose}
  class="admin-dialog admin-broadcast-failures-dialog"
>
  {#if broadcast}
    <div class="broadcast-failures-content">
      <p class="broadcast-failures-note">
        {at(
          "broadcast_failures_attempts_hint",
          {},
          "Counts are delivery attempts across channels, not unique recipients. A successful send does not mean the message was read."
        )}
      </p>
      {#if broadcast.channels.includes("telegram") && broadcast.excludeBlockedTelegram}
        <p class="broadcast-failures-note">
          {at(
            "broadcast_failures_blocked_hint",
            {},
            "The option excludes recipients already known to have blocked the bot before sending. Telegram may reveal a new block only during delivery; that attempt is counted as failed and the recipient status is updated for future sends. Email delivery is independent."
          )}
        </p>
      {/if}
      {#if broadcast.lastError}
        <section
          class="broadcast-failures-item"
          aria-label={at("broadcast_failures_global", {}, "Broadcast error")}
        >
          <strong>{at("broadcast_failures_global", {}, "Broadcast error")}</strong>
          <code>{broadcast.lastError}</code>
        </section>
      {/if}
      {#if failures.length}
        <ol class="broadcast-failures-list">
          {#each failures as failure (failure.deliveryId)}
            <li class="broadcast-failures-item">
              <div class="broadcast-failures-item-head">
                <strong
                  >{failure.channel === "email" ? "Email" : "Telegram"} · {at(
                    "broadcast_failures_user",
                    { id: failure.userId },
                    `User #${failure.userId}`
                  )}</strong
                >
                {#if failure.finishedAt}<small>{formatDate(failure.finishedAt)}</small>{/if}
              </div>
              <b>{reasonTitle(failure)}</b>
              <p>{reasonHint(failure)}</p>
              <code>{failure.error}</code>
            </li>
          {/each}
        </ol>
      {:else if !loading && !failedToLoad && !broadcast.lastError}
        <p class="broadcast-failures-note">
          {at(
            "broadcast_failures_unavailable",
            {},
            "No error details were saved for this broadcast."
          )}
        </p>
      {/if}
      {#if failedToLoad}
        <p class="broadcast-failures-load-error" role="alert">
          {at("broadcast_failures_load_failed", {}, "Could not load delivery errors.")}
        </p>
      {/if}
      {#if loading}
        <p class="broadcast-failures-note" role="status">{at("loading", {}, "Loading…")}</p>
      {:else if failedToLoad || failures.length < total}
        <AdminButton size="sm" variant="ghost" onclick={loadMore}>
          {failedToLoad
            ? at("broadcast_failures_retry", {}, "Retry")
            : at("broadcast_failures_more", {}, "Show more errors")}
        </AdminButton>
      {/if}
    </div>
  {/if}
</Dialog>

<style>
  :global(.admin-broadcast-failures-dialog) {
    width: min(680px, calc(100vw - 24px));
  }
  .broadcast-failures-content {
    display: grid;
    gap: 12px;
    padding: 16px;
  }
  .broadcast-failures-note,
  .broadcast-failures-item p {
    margin: 0;
    color: var(--admin-text-muted);
    font-size: 12px;
    line-height: 1.45;
  }
  .broadcast-failures-list {
    display: grid;
    gap: 10px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .broadcast-failures-item {
    display: grid;
    gap: 7px;
    min-width: 0;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 10px;
    background: var(--admin-surface-2);
    color: var(--admin-text);
    font-size: 12px;
  }
  .broadcast-failures-item-head {
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 4px 10px;
  }
  .broadcast-failures-item-head small {
    color: var(--admin-text-dim);
  }
  .broadcast-failures-item code {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    color: var(--admin-text-muted);
  }
  .broadcast-failures-load-error {
    margin: 0;
    color: var(--danger-text);
    font-size: 12px;
  }
  @media (max-width: 700px) {
    .broadcast-failures-content {
      padding: 12px;
    }
  }
</style>
