<script lang="ts">
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { ArrowRight, WalletCards } from "$components/ui/icons.js";
  import { EmptyCard, PaymentMethodPicker } from "$components/patterns/webapp/index.js";
  import { asWebappRecord } from "$lib/webapp/types.js";
  import type {
    BalanceView,
    OpenLinkAction,
    PaymentMethodView,
    Translate,
  } from "$lib/webapp/types.js";
  import type { ApiClient } from "$lib/webapp/publicApi.js";

  let {
    api,
    open = $bindable(false),
    balance = {} as BalanceView,
    methods = [],
    paymentMethodsDisplayMode = "dropdown",
    openExternalLink = () => {},
    t = (key) => key,
  }: {
    api: ApiClient["api"];
    open?: boolean;
    balance?: BalanceView;
    methods?: PaymentMethodView[];
    paymentMethodsDisplayMode?: "dropdown" | "buttons" | string;
    openExternalLink?: OpenLinkAction;
    t?: Translate;
  } = $props();

  let amount = $state(0);
  let selectedMethod = $state("");
  let busy = $state(false);
  let error = $state("");

  const availableMethods = $derived(
    methods.filter(
      (method) =>
        String(method.id || "").toLowerCase() !== "stars" && !method.price_managed_externally
    )
  );
  const minimum = $derived(Number(balance.topup_min_amount || 0));
  const maximum = $derived(Number(balance.topup_max_amount || 0));
  const presets = $derived(
    (Array.isArray(balance.topup_presets) ? balance.topup_presets : [])
      .map(Number)
      .filter((value) => Number.isFinite(value) && value >= minimum && value <= maximum)
  );
  const valid = $derived(amount >= minimum && amount <= maximum && !!selectedMethod && !busy);

  function selectMethod(methodId: string): void {
    selectedMethod = methodId;
    error = "";
  }

  function selectPreset(value: number): void {
    amount = value;
    error = "";
  }

  async function submit(): Promise<void> {
    if (!valid) return;
    busy = true;
    error = "";
    try {
      const response = asWebappRecord(
        await api("/balance/topup", {
          method: "POST",
          body: JSON.stringify({ method: selectedMethod, amount }),
        })
      );
      if (response.ok !== true) {
        throw new Error(String(response.message || response.error || "balance_topup_failed"));
      }
      const paymentUrl = String(
        response.payment_url || response.confirmation_url || response.url || ""
      ).trim();
      if (paymentUrl) {
        openExternalLink(paymentUrl);
        open = false;
        return;
      }
      if (response.paid === true || response.status === "succeeded") {
        open = false;
        return;
      }
      throw new Error("balance_topup_failed");
    } catch (cause) {
      error =
        cause instanceof Error && cause.message !== "balance_topup_failed"
          ? cause.message
          : t("wa_balance_topup_failed", {}, "Could not create a top-up payment");
    } finally {
      busy = false;
    }
  }

  $effect(() => {
    if (!open) return;
    amount = presets[0] || minimum || 0;
    selectedMethod = String(
      availableMethods.find((method) => method.id === selectedMethod)?.id ||
        availableMethods[0]?.id ||
        ""
    );
    error = "";
  });
</script>

<Dialog
  {open}
  title={t("wa_balance_topup_title", {}, "Top up balance")}
  description={t(
    "wa_balance_topup_description",
    {},
    "Choose an amount and a payment method. Funds will be credited after payment."
  )}
  closeLabel={t("wa_close")}
  onclose={() => (open = false)}
  class="balance-topup-dialog"
>
  <div class="balance-topup-current">
    <span><WalletCards size={22} /></span>
    <div>
      <small>{t("wa_balance_available", {}, "Available")}</small>
      <strong>{balance.amount} {balance.currency}</strong>
    </div>
  </div>
  <label class="balance-amount-field">
    <span>{t("wa_balance_topup_amount", {}, "Top-up amount")}</span>
    <div>
      <input
        type="number"
        bind:value={amount}
        min={minimum}
        max={maximum}
        step={1 / 10 ** Number(balance.currency_scale || 0)}
        inputmode="decimal"
      />
      <b>{balance.currency}</b>
    </div>
    <small>
      {t("wa_balance_topup_limits", { min: minimum, max: maximum }, "From {min} to {max}")}
    </small>
  </label>
  {#if presets.length}
    <div class="balance-presets">
      {#each presets as preset}
        <button type="button" class:active={amount === preset} onclick={() => selectPreset(preset)}>
          +{preset}
          {balance.currency}
        </button>
      {/each}
    </div>
  {/if}
  {#if availableMethods.length}
    <PaymentMethodPicker
      methods={availableMethods}
      {selectedMethod}
      mode={paymentMethodsDisplayMode}
      {t}
      onSelect={selectMethod}
    />
  {:else}
    <EmptyCard>{t("wa_payment_methods_not_configured")}</EmptyCard>
  {/if}
  {#if error}<small class="balance-topup-error">{error}</small>{/if}
  <Button class="wide bottom-action" onclick={submit} disabled={!valid}>
    {t("wa_balance_topup_continue", {}, "Continue to payment")}
    <ArrowRight size={17} />
  </Button>
</Dialog>

<style>
  .balance-topup-current {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 13px;
    border-radius: 14px;
    background: color-mix(in srgb, var(--accent) 12%, var(--panel-2));
  }
  .balance-topup-current > span {
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 15%, var(--panel));
  }
  .balance-topup-current div,
  .balance-amount-field {
    display: grid;
    gap: 3px;
  }
  .balance-topup-current small,
  .balance-amount-field > small {
    color: var(--muted);
  }
  .balance-topup-current strong {
    font-size: 20px;
  }
  .balance-amount-field > span {
    font-weight: 700;
  }
  .balance-amount-field > div {
    position: relative;
  }
  .balance-amount-field input {
    width: 100%;
    min-height: 48px;
    padding: 0 70px 0 13px;
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text);
    background: var(--panel-2);
    font: inherit;
    font-size: 18px;
    font-weight: 700;
  }
  .balance-amount-field b {
    position: absolute;
    top: 50%;
    right: 13px;
    transform: translateY(-50%);
    color: var(--muted);
  }
  .balance-presets {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .balance-presets button {
    flex: 1 1 100px;
    padding: 9px 10px;
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text);
    background: var(--panel-2);
    cursor: pointer;
  }
  .balance-presets button.active {
    border-color: var(--accent);
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 10%, var(--panel-2));
  }
  .balance-topup-error {
    color: var(--danger);
  }
</style>
