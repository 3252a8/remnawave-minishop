<script lang="ts">
  import Checkbox from "$components/ui/checkbox.svelte";
  import { WalletCards } from "$components/ui/icons.js";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import type { ApiClient, BalanceResponse } from "$lib/webapp/publicApi.js";
  import type { Translate } from "$lib/webapp/types.js";

  type BalanceSource = "user" | "partner";
  type SourceView = { id: BalanceSource; available: number };

  let {
    api,
    open = false,
    amount = 0,
    currency = "",
    eligible = false,
    minimumExternalAmount = 0,
    source = $bindable<BalanceSource | null>(null),
    discount = $bindable(0),
    t = (key) => key,
  }: {
    api: ApiClient["api"];
    open?: boolean;
    amount?: number;
    currency?: string;
    eligible?: boolean;
    minimumExternalAmount?: number;
    source?: BalanceSource | null;
    discount?: number;
    t?: Translate;
  } = $props();

  let sources = $state<SourceView[]>([]);
  let loading = $state(false);
  let requestKey = $state("");

  const normalizedCurrency = $derived(
    String(currency || "")
      .trim()
      .toUpperCase()
  );
  const selectedSource = $derived(sources.find((item) => item.id === source) || null);
  const maximumDiscount = $derived.by(() => {
    const due = Math.max(0, Number(amount || 0));
    const available = Math.max(0, Number(selectedSource?.available || 0));
    const minimum = Math.max(0, Number(minimumExternalAmount || 0));
    if (!eligible || due <= 0 || available <= 0) return 0;
    if (available >= due) return due;
    return Math.min(available, Math.max(0, due - minimum));
  });
  const remainder = $derived(Math.max(0, Number(amount || 0) - maximumDiscount));
  const visible = $derived(open && eligible && Boolean(normalizedCurrency) && sources.length > 0);

  function normalizeSources(response: BalanceResponse): SourceView[] {
    if (!response.ok || String(response.currency || "").toUpperCase() !== normalizedCurrency) {
      return [];
    }
    return response.sources
      .filter((item) => item.available && Number(item.amount_minor || 0) > 0)
      .map((item) => ({
        id: item.id === "partner" ? "partner" : "user",
        available: Number(item.amount_minor || 0) / 10 ** Number(response.currency_scale || 0),
      }));
  }

  async function loadBalance(key: string): Promise<void> {
    loading = true;
    try {
      const response = (await api("/balance")) as BalanceResponse;
      if (requestKey !== key) return;
      sources = normalizeSources(response);
    } catch {
      if (requestKey === key) sources = [];
    } finally {
      if (requestKey === key) loading = false;
    }
  }

  function toggleSelected(next: boolean): void {
    source = next ? source || sources[0]?.id || null : null;
  }

  function selectSource(event: Event): void {
    const value = (event.currentTarget as HTMLSelectElement).value;
    source = value === "partner" ? "partner" : "user";
  }

  $effect(() => {
    const key = open && eligible && normalizedCurrency ? normalizedCurrency : "";
    if (!key) {
      requestKey = "";
      sources = [];
      source = null;
      discount = 0;
      return;
    }
    if (requestKey === key) return;
    requestKey = key;
    void loadBalance(key);
  });

  $effect(() => {
    if (source && !sources.some((item) => item.id === source)) source = null;
    if (source && maximumDiscount <= 0) source = null;
    discount = source ? maximumDiscount : 0;
  });
</script>

{#if visible}
  <div class="balance-discount" class:selected={Boolean(source)} aria-busy={loading}>
    <Checkbox
      checked={Boolean(source)}
      disabled={loading}
      ariaLabel={t("wa_balance_checkout_aria", {}, "Use balance for this payment")}
      onCheckedChange={toggleSelected}
    />
    <span class="balance-icon"><WalletCards size={19} /></span>
    <div class="balance-copy">
      <div class="balance-title-row">
        <strong>{t("wa_balance_checkout_title", {}, "Pay from balance")}</strong>
        {#if sources.length > 1 && source}
          <select value={source} onchange={selectSource} aria-label={t("wa_balance_source_label")}>
            {#each sources as item}
              <option value={item.id}>
                {item.id === "partner"
                  ? t("wa_balance_source_partner", {}, "Partner balance")
                  : t("wa_balance_source_user", {}, "Main balance")}
              </option>
            {/each}
          </select>
        {/if}
      </div>
      <small>
        {#if source && selectedSource}
          {t("wa_balance_checkout_available", {
            balance: formatMoney(selectedSource.available, normalizedCurrency),
          })}
        {:else if sources.length === 1}
          {t("wa_balance_checkout_available", {
            balance: formatMoney(sources[0].available, normalizedCurrency),
          })}
        {:else}
          {t("wa_balance_checkout_choose", {}, "Choose which balance to use")}
        {/if}
      </small>
      {#if source}
        <div class="balance-result">
          <span>
            <s>{formatMoney(amount, normalizedCurrency)}</s>
            <b>{formatMoney(remainder, normalizedCurrency)}</b>
          </span>
          <small>
            {t("wa_balance_checkout_discount", {
              discount: formatMoney(maximumDiscount, normalizedCurrency),
            })}
          </small>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .balance-discount {
    display: grid;
    grid-template-columns: auto auto minmax(0, 1fr);
    align-items: center;
    gap: 10px;
    padding: 12px;
    border: 1px solid color-mix(in srgb, var(--accent) 36%, var(--border));
    border-radius: 13px;
    background: color-mix(in srgb, var(--accent) 8%, var(--panel-2));
  }
  .balance-discount.selected {
    border-color: color-mix(in srgb, var(--accent) 68%, var(--border));
    background: color-mix(in srgb, var(--accent) 14%, var(--panel-2));
  }
  .balance-icon {
    width: 38px;
    height: 38px;
    display: grid;
    place-items: center;
    border-radius: 11px;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 14%, var(--panel));
  }
  .balance-copy {
    min-width: 0;
    display: grid;
    gap: 4px;
  }
  .balance-copy > small {
    color: var(--muted);
    font-size: 12px;
  }
  .balance-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .balance-title-row select {
    min-width: 0;
    max-width: 190px;
    padding: 5px 26px 5px 8px;
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    background: var(--panel);
    font: inherit;
    font-size: 12px;
  }
  .balance-result {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
  }
  .balance-result span {
    display: inline-flex;
    gap: 7px;
  }
  .balance-result s {
    color: var(--muted);
  }
  .balance-result b,
  .balance-result small {
    color: var(--accent);
  }
  @media (max-width: 520px) {
    .balance-title-row,
    .balance-result {
      align-items: flex-start;
      flex-direction: column;
    }
    .balance-title-row select {
      width: 100%;
      max-width: none;
    }
  }
</style>
