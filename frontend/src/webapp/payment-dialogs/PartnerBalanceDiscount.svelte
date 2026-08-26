<script lang="ts">
  import Checkbox from "$components/ui/checkbox.svelte";
  import { WalletCards } from "$components/ui/icons.js";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import {
    loadPartnerBalanceSnapshot,
    peekPartnerBalanceSnapshot,
  } from "$lib/webapp/partnerBalanceLookup.js";
  import {
    partnerBalanceLookupKey,
    shouldShowPartnerBalanceDiscount,
  } from "$lib/webapp/partnerUiPolicy.js";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import type { Translate } from "$lib/webapp/types.js";

  let {
    api,
    open = false,
    amount = 0,
    currency = "",
    eligible = false,
    minimumExternalAmount = 0,
    selected = $bindable(false),
    discount = $bindable(0),
    t = (key) => key,
  }: {
    api: ApiClient["api"];
    open?: boolean;
    amount?: number;
    currency?: string;
    eligible?: boolean;
    minimumExternalAmount?: number;
    selected?: boolean;
    discount?: number;
    t?: Translate;
  } = $props();

  function initialBalanceState() {
    const key = String(currency || "").toUpperCase();
    return { key, snapshot: peekPartnerBalanceSnapshot(api, key) };
  }

  const initialBalance = initialBalanceState();
  let available = $state(initialBalance.snapshot?.available || 0);
  let loading = $state(false);
  let requestKey = $state(initialBalance.snapshot ? initialBalance.key : "");

  const normalizedCurrency = $derived(String(currency || "").toUpperCase());
  const maximumDiscount = $derived.by(() => {
    const due = Math.max(0, Number(amount || 0));
    const balance = Math.max(0, Number(available || 0));
    const minimum = Math.max(0, Number(minimumExternalAmount || 0));
    if (!eligible || due <= 0 || balance <= 0) return 0;
    if (balance >= due) return due;
    return Math.min(balance, Math.max(0, due - minimum));
  });
  const appliedDiscount = $derived(selected ? maximumDiscount : 0);
  const remainder = $derived(Math.max(0, Number(amount || 0) - appliedDiscount));
  const visible = $derived(
    shouldShowPartnerBalanceDiscount({
      open,
      eligible,
      currency: normalizedCurrency,
      maximumDiscount,
    })
  );
  function previewAvailable(): number | null {
    if (typeof window === "undefined") return null;
    const scenario = String(
      new URLSearchParams(window.location.search).get("partner_checkout") || ""
    ).toLowerCase();
    if (!scenario) return null;
    if (scenario === "enabled") return Math.max(Number(amount || 0), 2840);
    if (scenario === "negative") return -237;
    return 120;
  }

  async function loadBalance(key: string): Promise<void> {
    loading = true;
    const preview = previewAvailable();
    if (preview !== null) {
      available = preview;
      loading = false;
      return;
    }
    try {
      const snapshot = await loadPartnerBalanceSnapshot(api, normalizedCurrency);
      if (requestKey !== key) return;
      available = snapshot.available;
    } catch {
      if (requestKey === key) available = 0;
    } finally {
      if (requestKey === key) loading = false;
    }
  }

  function setSelected(next: boolean) {
    selected = next && maximumDiscount > 0;
  }

  $effect(() => {
    const key = partnerBalanceLookupKey({ open, eligible, currency: normalizedCurrency });
    if (!key) {
      if (!eligible || !normalizedCurrency) {
        requestKey = "";
        available = 0;
        loading = false;
      }
      selected = false;
      discount = 0;
      return;
    }
    if (requestKey === key) return;
    const cached = peekPartnerBalanceSnapshot(api, key);
    requestKey = key;
    available = cached?.available || 0;
    void loadBalance(key);
  });

  $effect(() => {
    if (selected && maximumDiscount <= 0) selected = false;
    discount = selected ? maximumDiscount : 0;
  });
</script>

{#if visible}
  <label class="partner-balance-discount" class:selected aria-busy={loading}>
    <Checkbox
      checked={selected}
      disabled={loading || maximumDiscount <= 0}
      ariaLabel={t("wa_partner_balance_checkout_aria")}
      onCheckedChange={setSelected}
    />
    <span class="partner-balance-icon"><WalletCards size={19} /></span>
    <span class="partner-balance-copy">
      <strong>{t("wa_partner_balance_checkout_title")}</strong>
      <span class="partner-balance-meta">
        <small>
          {t("wa_partner_balance_checkout_available", {
            balance: formatMoney(available, normalizedCurrency),
          })}
        </small>
        <span class:visible={selected} class="partner-balance-result" aria-hidden={!selected}>
          <span class="partner-balance-prices">
            <s>{formatMoney(amount, normalizedCurrency)}</s>
            <b>{formatMoney(remainder, normalizedCurrency)}</b>
          </span>
          <small class="partner-balance-saving">
            {t("wa_partner_balance_checkout_discount", {
              discount: formatMoney(appliedDiscount, normalizedCurrency),
            })}
          </small>
        </span>
      </span>
    </span>
  </label>
{/if}

<style>
  .partner-balance-discount {
    display: grid;
    grid-template-columns: auto auto minmax(0, 1fr);
    align-items: center;
    gap: 10px;
    padding: 12px;
    border: 1px solid color-mix(in srgb, var(--accent) 36%, var(--border));
    border-radius: 13px;
    background: color-mix(in srgb, var(--accent) 8%, var(--panel-2));
    cursor: pointer;
  }

  .partner-balance-discount.selected {
    border-color: color-mix(in srgb, var(--accent) 68%, var(--border));
    background: color-mix(in srgb, var(--accent) 14%, var(--panel-2));
  }

  .partner-balance-icon {
    width: 38px;
    height: 38px;
    display: grid;
    place-items: center;
    border-radius: 11px;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 14%, var(--panel));
  }

  .partner-balance-copy {
    min-width: 0;
    display: grid;
    gap: 3px;
  }

  .partner-balance-copy small {
    color: var(--muted);
    font-size: 12px;
  }

  .partner-balance-meta {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px 14px;
    min-width: 0;
  }

  .partner-balance-result {
    display: inline-flex;
    flex: none;
    align-items: baseline;
    gap: 8px;
    visibility: hidden;
    opacity: 0;
  }

  .partner-balance-result.visible {
    visibility: visible;
    opacity: 1;
  }

  .partner-balance-prices {
    display: inline-flex;
    align-items: baseline;
    gap: 7px;
  }

  .partner-balance-prices s {
    color: var(--muted);
  }

  .partner-balance-prices b,
  .partner-balance-saving {
    color: var(--accent);
  }

  @media (max-width: 520px) {
    .partner-balance-meta {
      align-items: flex-start;
      flex-direction: column;
      gap: 3px;
    }
  }
</style>
