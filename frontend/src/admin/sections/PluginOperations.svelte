<script lang="ts">
  import { untrack } from "svelte";
  import { AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { Dialog, Input, Switch } from "$components/ui/index.js";
  import type { components } from "$lib/api/openapi.generated";
  import { builtApiPath, unwrap } from "$lib/webapp/publicApi";
  import type { AdminApi } from "../adminStores";

  type Data = components["schemas"]["ExtensionAdminOut"];
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  let { api, owner, at }: { api: AdminApi; owner: string; at: Translate } = $props();
  let data = $state<Data>({ operations: [], orders: [], presentation: [] });
  let busy = $state(false);
  let error = $state("");
  let cursor = $state("");
  let ordersCursor = $state("");
  let reason = $state("");
  let action = $state<{ id: string; action: "retry" | "refund" } | null>(null);
  let dialogOpen = $state(false);
  let revision = 0;

  async function load() {
    const token = ++revision;
    busy = true;
    error = "";
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/extensions">(
            `/api/admin/extensions?${new URLSearchParams({ owner, cursor, orders_cursor: ordersCursor })}`
          )
        )
      );
      if (token === revision) data = result;
    } catch {
      if (token === revision) error = at("plugins_operation_failed");
    } finally {
      if (token === revision) busy = false;
    }
  }
  $effect(() => {
    const currentOwner = owner;
    if (currentOwner) {
      cursor = "";
      ordersCursor = "";
      data = { operations: [], orders: [], presentation: [] };
      untrack(() => void load());
    }
    return () => {
      revision++;
    };
  });
  async function save(target: Data["presentation"][number]) {
    busy = true;
    error = "";
    try {
      unwrap(
        await api(
          builtApiPath<"/api/admin/extensions/presentation">("/api/admin/extensions/presentation"),
          {
            method: "POST",
            body: JSON.stringify({
              owner,
              target: target.target,
              enabled: target.enabled,
              position: Number(target.position),
            }),
          }
        )
      );
      await load();
    } catch {
      error = at("plugins_operation_failed");
      busy = false;
    }
  }
  function choose(id: string, kind: "retry" | "refund") {
    action = { id, action: kind };
    reason = "";
    dialogOpen = true;
  }
  async function submit() {
    if (!action || reason.trim().length < 3) return;
    busy = true;
    error = "";
    try {
      unwrap(
        await api(builtApiPath<"/api/admin/extensions/action">("/api/admin/extensions/action"), {
          method: "POST",
          body: JSON.stringify({ owner, ...action, reason }),
        })
      );
      dialogOpen = false;
      await load();
    } catch {
      error = at("plugins_operation_failed");
      busy = false;
    }
  }
</script>

<section class="plugin-operations">
  <AdminButton disabled={busy} onclick={() => void load()}>{at("plugins_refresh")}</AdminButton>
  {#if error}<p role="alert">{error}</p>{/if}
  {#each data.presentation as item (item.target)}
    <div class="operation-row">
      <label
        ><Switch.Root bind:checked={item.enabled} aria-label={item.label} class="admin-switch-root"
          ><Switch.Thumb class="admin-switch-thumb" /></Switch.Root
        >{item.label}</label
      >
      <label
        >{at("plugins_position")}<Input
          class="operation-position"
          type="number"
          min={-10000}
          max={10000}
          bind:value={item.position}
        /></label
      >
      <AdminButton disabled={busy} onclick={() => void save(item)}
        >{at("plugins_save_presentation")}</AdminButton
      >
    </div>
  {/each}
  {#each data.orders as order (order.id)}
    <div class="operation-row">
      <div>
        <strong>{order.title}</strong>
        <p>{order.id} · {order.user_minishop_id || "—"}</p>
        <p>
          {(order.amount_minor / 10 ** order.currency_scale).toFixed(order.currency_scale)}
          {order.currency}
        </p>
        <p>
          {at(`plugins_state_${order.payment_state}`)} / {at(
            `plugins_state_${order.fulfillment_state}`
          )}
        </p>
      </div>
      {#if order.can_refund}
        <AdminButton disabled={busy} onclick={() => choose(order.id, "refund")}
          >{at("plugins_refund_balance")}</AdminButton
        >
      {/if}
    </div>
  {/each}
  {#if data.orders.length === 100}
    <AdminButton
      disabled={busy}
      onclick={() => {
        ordersCursor = data.orders.at(-1)?.id || "";
        void load();
      }}>{at("plugins_next_page")}</AdminButton
    >
  {/if}
  {#each data.operations as operation (operation.id)}
    <div class="operation-row">
      <div>
        <strong>{operation.kind}</strong>
        <p>{operation.id} · {operation.user_minishop_id || "—"}</p>
        <p>
          {at(`plugins_state_${operation.state}`)} · {operation.attempts}
          {operation.error || ""}
        </p>
      </div>
      {#if operation.state === "failed" || operation.state === "blocked"}
        <AdminButton disabled={busy} onclick={() => choose(operation.id, "retry")}
          >{at("plugins_retry")}</AdminButton
        >
      {/if}
    </div>
  {:else}<AdminEmptyState title={at("plugins_no_operations")} />{/each}
  {#if data.operations.length === 100}
    <AdminButton
      disabled={busy}
      onclick={() => {
        cursor = data.operations.at(-1)?.id || "";
        void load();
      }}>{at("plugins_next_page")}</AdminButton
    >
  {/if}
</section>
<Dialog
  open={dialogOpen}
  title={at(action?.action === "refund" ? "plugins_refund_balance" : "plugins_retry")}
  description={at(action?.action === "refund" ? "plugins_refund_notice" : "plugins_retry_notice")}
  closeLabel={at("close")}
  onclose={() => (dialogOpen = false)}
  class="admin-dialog"
>
  <label>{at("plugins_action_reason")}<Input bind:value={reason} maxlength={500} /></label>
  <AdminButton disabled={busy || reason.trim().length < 3} onclick={() => void submit()}
    >{at("plugins_confirm_action")}</AdminButton
  >
</Dialog>

<style>
  .plugin-operations {
    display: grid;
    gap: 1rem;
  }
  .operation-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    border-bottom: 1px solid var(--border);
    padding: 0.75rem 0;
    overflow-wrap: anywhere;
  }
  label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    white-space: nowrap;
  }
  :global(.operation-position) {
    width: 6rem;
  }
  p {
    font-size: 0.8rem;
  }
</style>
