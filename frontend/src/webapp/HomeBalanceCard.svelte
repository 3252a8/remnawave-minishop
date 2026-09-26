<script lang="ts">
  import { Plus, WalletCards } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import type { BalanceView, Translate, VoidAction } from "$lib/webapp/types.js";
  let {
    balance,
    openBalanceTopup,
    t,
  }: {
    balance: BalanceView;
    openBalanceTopup: VoidAction;
    t: Translate;
  } = $props();
</script>

<Card class="home-balance-card">
  <div class="home-balance-summary">
    <WalletCards size={22} />
    <span>
      <small>{t("wa_balance_title", {}, "Balance")}:</small>
      <strong>{formatMoney(balance.amount, balance.currency)}</strong>
    </span>
  </div>
  {#if balance.enabled}
    <Button
      data-webapp-action="open-balance-topup"
      class="home-balance-topup"
      type="button"
      size="sm"
      variant="outline"
      onclick={openBalanceTopup}
      aria-label={t("wa_balance_topup_short", {}, "Top up")}
      title={t("wa_balance_topup_short", {}, "Top up")}
    >
      <Plus size={16} />
    </Button>
  {/if}
</Card>

<style>
  :global(section.home-balance-card) {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 11px;
    padding: 8px 11px;
  }
  .home-balance-summary {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 11px;
  }
  .home-balance-summary > :global(svg) {
    flex: 0 0 auto;
    color: var(--accent);
  }
  .home-balance-summary > span {
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 5px;
  }
  .home-balance-summary small {
    color: var(--muted);
    font-size: 12px;
  }
  .home-balance-summary strong {
    font-size: 17px;
  }
  :global(section.home-balance-card .home-balance-topup) {
    position: relative;
    width: 32px;
    min-width: 32px;
    min-height: 32px;
    height: 32px;
    flex: 0 0 auto;
    padding: 0;
    border-color: var(--accent);
    color: var(--accent);
    background: transparent;
  }
  :global(section.home-balance-card .home-balance-topup::after) {
    content: "";
    position: absolute;
    inset: -6px;
  }
  :global(section.home-balance-card .home-balance-topup:hover) {
    border-color: var(--accent);
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 9%, transparent);
  }
  @media (max-width: 520px) {
    :global(section.home-balance-card) {
      padding: 7px 11px;
    }
    .home-balance-summary {
      gap: 8px;
    }
  }
</style>
