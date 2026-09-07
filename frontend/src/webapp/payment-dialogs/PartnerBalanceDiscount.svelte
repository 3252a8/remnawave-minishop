<script lang="ts">
  import Checkbox from "$components/ui/checkbox.svelte";
  import { Check, WalletCards } from "$components/ui/icons.js";
  import { Select } from "$components/ui/primitives.js";
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
    prefetchedBalance,
    balancePreloadComplete = false,
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
    prefetchedBalance?: BalanceResponse | null;
    balancePreloadComplete?: boolean;
    source?: BalanceSource | null;
    discount?: number;
    t?: Translate;
  } = $props();

  let loadedSources = $state<SourceView[]>([]);
  let loading = $state(false);
  let requestKey = $state("");

  const normalizedCurrency = $derived(
    String(currency || "")
      .trim()
      .toUpperCase()
  );
  const sources = $derived(
    prefetchedBalance !== undefined
      ? balancePreloadComplete && prefetchedBalance
        ? normalizeSources(prefetchedBalance)
        : []
      : loadedSources
  );
  const selectedSource = $derived(sources.find((item) => item.id === source) || null);
  const preferredSource = $derived(
    sources.find((item) => item.id === "user") || sources[0] || null
  );
  const displayedSource = $derived(selectedSource || preferredSource);
  const maximumDiscount = $derived.by(() => {
    const due = Math.max(0, Number(amount || 0));
    const available = Math.max(0, Number(selectedSource?.available || 0));
    const minimum = Math.max(0, Number(minimumExternalAmount || 0));
    if (!eligible || due <= 0 || available <= 0) return 0;
    if (available >= due) return due;
    return Math.min(available, Math.max(0, due - minimum));
  });
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
      loadedSources = normalizeSources(response);
    } catch {
      if (requestKey === key) loadedSources = [];
    } finally {
      if (requestKey === key) loading = false;
    }
  }

  function toggleSelected(next: boolean): void {
    source = next ? source || preferredSource?.id || null : null;
  }

  function selectSource(value: string): void {
    source = value === "partner" ? "partner" : "user";
  }

  function sourceLabel(id: BalanceSource): string {
    return id === "partner"
      ? t("wa_balance_source_partner", {}, "Partner balance")
      : t("wa_balance_source_user", {}, "Main balance");
  }

  function inlineSourceLabel(id: BalanceSource | undefined): string {
    return id === "partner"
      ? t("wa_balance_source_partner_inline", {}, "partner balance")
      : t("wa_balance_source_user_inline", {}, "balance");
  }

  $effect(() => {
    if (prefetchedBalance !== undefined) {
      requestKey = "";
      loadedSources = [];
      loading = false;
      return;
    }
    const key = open && eligible && normalizedCurrency ? normalizedCurrency : "";
    if (!key) {
      requestKey = "";
      loadedSources = [];
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
        <strong>{t("wa_balance_checkout_prefix", {}, "Pay from")}</strong>
        {#if sources.length > 1}
          <Select.Root
            type="single"
            value={displayedSource?.id || "user"}
            items={sources.map((item) => ({ value: item.id, label: sourceLabel(item.id) }))}
            onValueChange={selectSource}
          >
            <Select.Trigger
              class="balance-source-trigger"
              aria-label={t("wa_balance_source_label", {}, "Funds source")}
            >
              {inlineSourceLabel(displayedSource?.id)}
            </Select.Trigger>
            <Select.Portal>
              <Select.Content
                class="balance-source-select-content"
                side="bottom"
                align="start"
                sideOffset={6}
                collisionPadding={12}
              >
                <Select.Viewport class="balance-source-select-viewport">
                  {#each sources as item (item.id)}
                    <Select.Item
                      class="balance-source-select-item"
                      value={item.id}
                      label={sourceLabel(item.id)}
                    >
                      <Check size={15} class="balance-source-select-check" />
                      <span>{sourceLabel(item.id)}</span>
                      <small>{formatMoney(item.available, normalizedCurrency)}</small>
                    </Select.Item>
                  {/each}
                </Select.Viewport>
              </Select.Content>
            </Select.Portal>
          </Select.Root>
        {:else}
          <strong>{inlineSourceLabel(displayedSource?.id)}</strong>
        {/if}
      </div>
      {#if displayedSource}
        <small>
          {t("wa_balance_checkout_available", {
            balance: formatMoney(displayedSource.available, normalizedCurrency),
          })}
        </small>
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
    line-height: 1.25;
  }
  :global(.balance-source-trigger) {
    appearance: none;
    padding: 0 0 1px;
    border: 0;
    border-bottom: 1px dashed currentColor;
    border-radius: 0;
    color: var(--text);
    background: transparent;
    font: inherit;
    font-weight: 700;
    line-height: inherit;
    vertical-align: baseline;
    cursor: pointer;
  }
  :global(.balance-source-trigger:hover) {
    color: var(--accent);
  }
  :global(.balance-source-select-content) {
    z-index: 1200;
    min-width: 230px;
    overflow: hidden;
    padding: 5px;
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text);
    background: var(--panel);
    box-shadow: 0 16px 42px rgb(0 0 0 / 18%);
  }
  :global(.balance-source-select-viewport) {
    display: grid;
    gap: 2px;
  }
  :global(.balance-source-select-item) {
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr) auto;
    align-items: center;
    gap: 7px;
    padding: 8px 9px;
    border-radius: 8px;
    font-size: 12px;
    outline: none;
    cursor: pointer;
  }
  :global(.balance-source-select-item[data-highlighted]) {
    background: var(--panel-2);
  }
  :global(.balance-source-select-item small) {
    color: var(--muted);
    font-size: 11px;
  }
  :global(.balance-source-select-check) {
    opacity: 0;
    color: var(--accent);
  }
  :global(.balance-source-select-item[data-selected] .balance-source-select-check) {
    opacity: 1;
  }
</style>
