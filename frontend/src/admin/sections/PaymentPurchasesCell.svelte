<script lang="ts">
  import { Crown, SatelliteDish, Smartphone, Tag } from "$components/ui/icons.js";
  import { paymentPurchaseDisplay, type PaymentPurchasesRow } from "$lib/admin/paymentTable.js";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  let {
    payment,
    at = (key) => key,
    mode = "table",
  }: {
    payment: PaymentPurchasesRow;
    at?: TranslateFn;
    mode?: "table" | "mobile" | "detail";
  } = $props();

  const items = $derived(paymentPurchaseDisplay(payment, at));
  const hasFlexibleLimits = $derived(items.some((item) => item.mode === "limit"));
</script>

{#if items.length}
  {#if mode === "detail"}
    <div class="admin-payment-purchases-detail" data-payment-purchases={mode}>
      <ul class="admin-payment-purchases-detail-list">
        {#each items as item (item.key)}
          <li class={`admin-payment-purchase-detail admin-payment-purchase-${item.tone}`}>
            <span class="admin-payment-purchase-detail-icon" aria-hidden="true">
              {#if item.tone === "premium"}
                <Crown size={16} />
              {:else if item.tone === "devices"}
                <Smartphone size={16} />
              {:else if item.tone === "regular"}
                <SatelliteDish size={16} />
              {:else}
                <Tag size={16} />
              {/if}
            </span>
            <span class="admin-payment-purchase-detail-copy">
              <small>
                {item.mode === "limit"
                  ? at("payment_detail_purchase_mode_limit", {}, "Flexible limit")
                  : at("payment_detail_purchase_mode_topup", {}, "Add-on")}
              </small>
              <strong>{item.label}</strong>
            </span>
          </li>
        {/each}
      </ul>
      <p class="admin-payment-purchases-detail-note">
        {hasFlexibleLimits
          ? at(
              "payment_detail_purchases_flexible_note",
              {},
              "Flexible limits show the traffic and devices included for the paid period; separate add-ons are labeled accordingly."
            )
          : at(
              "payment_detail_purchases_topup_note",
              {},
              "Additional items included in this payment."
            )}
      </p>
    </div>
  {:else}
    <div
      class:admin-payment-purchases-mobile={mode === "mobile"}
      class:admin-payment-purchases-table={mode === "table"}
      data-payment-purchases={mode}
    >
      {#if mode === "mobile"}
        <span class="admin-payment-purchases-title"
          >{at("payments_col_purchases", {}, "Add-ons")}</span
        >
      {/if}
      <ul class="admin-payment-purchases-list">
        {#each items as item (item.key)}
          <li class={`admin-payment-purchase admin-payment-purchase-${item.tone}`}>{item.label}</li>
        {/each}
      </ul>
    </div>
  {/if}
{:else if mode === "table"}
  <span class="admin-payment-purchases-empty">—</span>
{/if}

<style>
  .admin-payment-purchases-table,
  .admin-payment-purchases-mobile {
    min-width: 0;
  }

  .admin-payment-purchases-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    min-width: 0;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .admin-payment-purchases-table .admin-payment-purchases-list {
    display: grid;
    align-content: center;
    justify-items: start;
    gap: 3px;
  }

  .admin-payment-purchase {
    max-width: 100%;
    padding: 2px 6px;
    overflow: hidden;
    border: 1px solid color-mix(in srgb, var(--purchase-color) 25%, var(--admin-border));
    border-radius: 999px;
    background: color-mix(in srgb, var(--purchase-color) 9%, transparent);
    color: color-mix(in srgb, var(--purchase-color) 76%, var(--admin-text));
    font-size: 10px;
    font-weight: 650;
    line-height: 1.35;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .admin-payment-purchase-regular {
    --purchase-color: #2f9f86;
  }

  .admin-payment-purchase-premium {
    --purchase-color: #8b5cf6;
  }

  .admin-payment-purchase-devices {
    --purchase-color: #3b82f6;
  }

  .admin-payment-purchase-other {
    --purchase-color: var(--admin-muted);
  }

  .admin-payment-purchases-empty {
    color: var(--admin-muted);
  }

  .admin-payment-purchases-mobile {
    display: grid;
    gap: 6px;
    padding: 8px 9px;
    border-radius: 8px;
    background: color-mix(in srgb, var(--admin-bg) 58%, transparent);
  }

  .admin-payment-purchases-title {
    color: var(--admin-muted);
    font-size: 10px;
    font-weight: 650;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .admin-payment-purchases-mobile .admin-payment-purchase {
    padding: 3px 7px;
    font-size: 11px;
  }

  .admin-payment-purchases-detail {
    display: grid;
    gap: 8px;
    min-width: 0;
  }

  .admin-payment-purchase-detail-icon {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    color: var(--purchase-color, var(--accent));
  }

  .admin-payment-purchase-detail-copy {
    display: grid;
    gap: 3px;
    min-width: 0;
  }

  .admin-payment-purchases-detail-list {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    min-width: 0;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .admin-payment-purchase-detail {
    display: grid;
    grid-template-columns: 32px minmax(0, 1fr);
    align-items: center;
    gap: 9px;
    min-width: 0;
    padding: 8px 0;
    border-bottom: 1px solid var(--admin-border);
  }

  .admin-payment-purchase-detail:last-child {
    border-bottom: 0;
  }

  .admin-payment-purchase-detail-icon {
    width: 32px;
    height: 32px;
    border-radius: 9px;
    background: color-mix(in srgb, var(--purchase-color) 14%, var(--admin-surface));
  }

  .admin-payment-purchase-detail-copy small {
    color: color-mix(in srgb, var(--purchase-color) 76%, var(--admin-muted));
    font-size: 9px;
    font-weight: 750;
    letter-spacing: 0.055em;
    text-transform: uppercase;
  }

  .admin-payment-purchase-detail-copy strong {
    min-width: 0;
    color: var(--admin-text);
    font-size: 11px;
    font-weight: 700;
    line-height: 1.35;
    overflow-wrap: anywhere;
  }

  .admin-payment-purchases-detail-note {
    margin: 0;
    color: var(--admin-muted);
    font-size: 11px;
    line-height: 1.45;
  }
</style>
