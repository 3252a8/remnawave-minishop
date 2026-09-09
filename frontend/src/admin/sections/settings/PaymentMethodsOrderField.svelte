<script lang="ts">
  import { Sortable } from "$components/ui/index.js";
  import { Switch } from "$components/ui/primitives.js";
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import {
    paymentMethodOrderItems,
    reorderVisiblePaymentMethods,
    serializePaymentMethodOrder,
    type PaymentMethodOrderItem,
  } from "$lib/admin/paymentMethodsOrder";
  import type { PaymentMethodOrderOption } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    at,
    value = "",
    options = [],
    onValueChange = () => {},
  }: {
    at: TranslateFn;
    value?: unknown;
    options?: PaymentMethodOrderOption[];
    onValueChange?: (value: string) => void;
  } = $props();

  let hideDisabled = $state(false);
  const items = $derived(paymentMethodOrderItems(value, options));
  const disabledCount = $derived(items.filter((item) => item.known && !item.enabled).length);
  const visibleItems = $derived(
    hideDisabled ? items.filter((item) => !item.known || item.enabled) : items
  );

  function itemKey(item: PaymentMethodOrderItem): string {
    return item.id;
  }

  function reorder(from: number, to: number): void {
    const reordered = reorderVisiblePaymentMethods(items, visibleItems, from, to);
    onValueChange(serializePaymentMethodOrder(reordered));
  }

  function statusLabel(item: PaymentMethodOrderItem): string {
    if (!item.known) return at("settings_payment_order_unknown", {}, "Unknown method");
    if (item.admin_only) return at("settings_payment_order_admin_only", {}, "Admins only");
    return item.enabled ? at("enabled", {}, "Enabled") : at("disabled", {}, "Disabled");
  }
</script>

<div class="payment-method-order">
  <label class="payment-method-order-filter">
    <Switch.Root
      aria-label={at("settings_payment_order_hide_disabled", {}, "Hide disabled provider buttons")}
      checked={hideDisabled}
      disabled={!disabledCount}
      onCheckedChange={(checked) => (hideDisabled = checked)}
      class="admin-switch-root"
    >
      <Switch.Thumb class="admin-switch-thumb" />
    </Switch.Root>
    <span>
      {at("settings_payment_order_hide_disabled", {}, "Hide disabled provider buttons")}
      {#if disabledCount}
        <small
          >{at(
            "settings_payment_order_disabled_count",
            { count: disabledCount },
            `{count} disabled`
          )}</small
        >
      {/if}
    </span>
  </label>

  {#if visibleItems.length}
    <div class="payment-method-order-list">
      <Sortable
        items={visibleItems}
        class="payment-method-order-row"
        getKey={itemKey}
        handleLabel={at("settings_payment_order_drag", {}, "Drag to reorder payment button")}
        onReorder={reorder}
      >
        {#snippet children(item: PaymentMethodOrderItem)}
          <div class="payment-method-order-copy">
            <strong>{item.label}</strong>
            <small>{item.provider_label} · <code>{item.id}</code></small>
          </div>
          <AdminBadge variant={item.enabled ? "success" : item.known ? "muted" : "warning"}>
            {statusLabel(item)}
          </AdminBadge>
        {/snippet}
      </Sortable>
    </div>
  {:else}
    <p class="payment-method-order-empty">
      {at("settings_payment_order_empty", {}, "All disabled provider buttons are hidden.")}
    </p>
  {/if}
</div>

<style>
  .payment-method-order {
    display: grid;
    flex: 1 1 100%;
    gap: 10px;
    width: 100%;
    min-width: 0;
  }

  .payment-method-order-filter {
    display: flex;
    align-items: center;
    gap: 9px;
    width: fit-content;
    max-width: 100%;
    color: var(--admin-text);
    font-size: 12px;
    cursor: pointer;
  }

  .payment-method-order-filter > span {
    display: flex;
    align-items: baseline;
    gap: 7px;
    min-width: 0;
  }

  .payment-method-order-filter small {
    color: var(--admin-muted);
    white-space: nowrap;
  }

  .payment-method-order-list {
    min-width: 0;
  }

  .payment-method-order-list :global(.payment-method-order-row) {
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    min-height: 48px;
    padding: 7px 9px;
    border: 1px solid var(--admin-border);
    background: color-mix(in srgb, var(--admin-surface-2) 70%, transparent);
  }

  .payment-method-order-copy {
    display: grid;
    gap: 2px;
    min-width: 0;
  }

  .payment-method-order-copy strong {
    color: var(--admin-text);
    font-size: 12px;
    line-height: 1.3;
  }

  .payment-method-order-copy small {
    min-width: 0;
    color: var(--admin-muted);
    font-size: 11px;
    overflow-wrap: anywhere;
  }

  .payment-method-order-copy code {
    color: var(--admin-dim);
    font-family: var(--font-mono);
  }

  .payment-method-order-empty {
    margin: 0;
    padding: 12px;
    border: 1px dashed var(--admin-border-strong);
    border-radius: 8px;
    color: var(--admin-muted);
    font-size: 12px;
    text-align: center;
  }

  @media (max-width: 520px) {
    .payment-method-order-list :global(.payment-method-order-row) {
      grid-template-columns: 24px minmax(0, 1fr);
    }

    .payment-method-order-list :global(.payment-method-order-row > .admin-badge) {
      grid-column: 2;
      justify-self: start;
    }
  }
</style>
