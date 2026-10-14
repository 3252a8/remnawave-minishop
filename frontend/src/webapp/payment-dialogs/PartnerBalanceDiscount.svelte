<script lang="ts">
  import { prefersReducedMotion } from "svelte/motion";
  import { slide } from "svelte/transition";
  import Checkbox from "$components/ui/checkbox.svelte";
  import { Check, CircleQuestionMark, WalletCards } from "$components/ui/icons.js";
  import { Popover, Select, Switch } from "$components/ui/primitives.js";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import type { ApiClient, BalanceResponse } from "$lib/webapp/publicApi.js";
  import type { Translate } from "$lib/webapp/types.js";

  type BalanceSource = "user" | "partner";
  type SourceView = { id: BalanceSource; available: number; recurringAvailable: boolean };

  let {
    api,
    open = false,
    amount = 0,
    currency = "",
    eligible = false,
    minimumExternalAmount = 0,
    prefetchedBalance,
    balancePreloadComplete = false,
    recurringEligible = false,
    autoRenew = $bindable(true),
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
    recurringEligible?: boolean;
    autoRenew?: boolean;
    source?: BalanceSource | null;
    discount?: number;
    t?: Translate;
  } = $props();

  let loadedSources = $state<SourceView[]>([]);
  let loading = $state(false);
  let requestKey = $state("");
  let loadedRecurringEnabled = $state(false);

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
  const recurringEnabled = $derived(
    prefetchedBalance !== undefined
      ? Boolean(balancePreloadComplete && prefetchedBalance?.recurring_enabled)
      : loadedRecurringEnabled
  );
  const fullyFunded = $derived(Boolean(source) && maximumDiscount > 0 && maximumDiscount >= amount);

  const canRenew = $derived(fullyFunded && Boolean(selectedSource?.recurringAvailable));

  function normalizeSources(response: BalanceResponse): SourceView[] {
    if (!response.ok || String(response.currency || "").toUpperCase() !== normalizedCurrency) {
      return [];
    }
    return response.sources
      .filter((item) => item.available && Number(item.amount_minor || 0) > 0)
      .map((item) => ({
        id: item.id === "partner" ? "partner" : "user",
        available: Number(item.amount_minor || 0) / 10 ** Number(response.currency_scale || 0),
        recurringAvailable: Boolean(item.recurring_available),
      }));
  }

  async function loadBalance(key: string): Promise<void> {
    loading = true;
    try {
      const response = (await api("/balance")) as BalanceResponse;
      if (requestKey !== key) return;
      loadedSources = normalizeSources(response);
      loadedRecurringEnabled = Boolean(response.ok && response.recurring_enabled);
    } catch {
      if (requestKey === key) loadedSources = [];
      if (requestKey === key) loadedRecurringEnabled = false;
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
    {#if source && recurringEligible && recurringEnabled}
      <div
        class="balance-recurring-row"
        transition:slide={{ duration: prefersReducedMotion.current ? 0 : 220 }}
      >
        <div class="balance-recurring-copy">
          <label for="balance-checkout-recurring">{t("wa_balance_recurring_label")}</label>
          <Popover.Root>
            <Popover.Trigger
              class="balance-recurring-help"
              aria-label={t("wa_balance_recurring_help_label")}
            >
              <CircleQuestionMark size={16} />
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content
                class="balance-recurring-popover"
                side="top"
                sideOffset={8}
                collisionPadding={12}
              >
                <strong>{t("wa_balance_recurring_label")}</strong>
                <p>{t("wa_balance_recurring_help")}</p>
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
          {#if !selectedSource?.recurringAvailable}
            <small>{t("wa_balance_recurring_source_unavailable")}</small>
          {:else if !fullyFunded}
            <small>{t("wa_balance_recurring_full_payment_required")}</small>
          {/if}
        </div>
        <Switch.Root
          id="balance-checkout-recurring"
          class="balance-recurring-switch"
          checked={canRenew && autoRenew}
          disabled={!canRenew || loading}
          aria-label={t("wa_balance_recurring_label")}
          onCheckedChange={(checked) => (autoRenew = checked)}
        >
          <Switch.Thumb class="balance-recurring-thumb" />
        </Switch.Root>
      </div>
    {/if}
  </div>
{/if}

<style>
  .balance-discount {
    display: grid;
    grid-template-columns: auto auto minmax(0, 1fr);
    align-items: center;
    column-gap: 10px;
    padding: 12px;
    border: 1px solid color-mix(in srgb, var(--accent) 36%, var(--border));
    border-radius: var(--radius-control);
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
    border-radius: var(--radius-control);
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
  .balance-recurring-row {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 10px;
    padding-top: 11px;
    border-top: 1px solid var(--border);
  }
  .balance-recurring-copy {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    min-width: 0;
    font-size: 13px;
    font-weight: 600;
  }
  .balance-recurring-copy small {
    flex-basis: 100%;
    color: var(--muted);
    font-size: 12px;
    font-weight: 400;
  }
  :global(.balance-recurring-help) {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 4px;
    border: 0;
    border-radius: var(--radius-inner);
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  :global(.balance-recurring-help:hover) {
    color: var(--accent);
  }
  :global(.balance-recurring-switch) {
    display: inline-flex;
    align-items: center;
    flex: 0 0 38px;
    width: 38px;
    height: 22px;
    padding: 2px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--panel-2);
    transition:
      background-color 160ms,
      border-color 160ms;
    cursor: pointer;
  }
  :global(.balance-recurring-switch[data-state="checked"]) {
    background: var(--accent);
    border-color: var(--accent);
  }
  :global(.balance-recurring-switch:disabled) {
    opacity: 0.5;
    cursor: not-allowed;
  }
  :global(.balance-recurring-thumb) {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--text);
    transform: translateX(0);
    transition:
      transform 160ms,
      background-color 160ms;
  }
  :global(.balance-recurring-thumb[data-state="checked"]) {
    background: var(--accent-contrast, var(--panel));
    transform: translateX(16px);
  }
  :global(.balance-recurring-popover) {
    z-index: 1200;
    width: min(340px, calc(100vw - 24px));
    padding: 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius-control);
    color: var(--text);
    background: var(--panel);
    box-shadow: 0 16px 42px rgb(0 0 0 / 18%);
    font-size: 13px;
    line-height: 1.5;
  }
  :global(.balance-recurring-popover p) {
    margin: 7px 0 0;
    color: var(--muted);
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
    border-radius: var(--radius-control);
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
    border-radius: var(--radius-inner);
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
  @media (prefers-reduced-motion: reduce) {
    :global(.balance-recurring-switch),
    :global(.balance-recurring-thumb) {
      transition: none;
    }
  }
</style>
