<script lang="ts">
  import { onDestroy } from "svelte";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { LockKeyhole, WalletCards } from "$components/ui/icons.js";
  import { EmptyCard, PaymentMethodPicker } from "$components/patterns/webapp/index.js";
  import AnimatedNumber from "$components/patterns/webapp/AnimatedNumber.svelte";
  import { asWebappRecord } from "$lib/webapp/types.js";
  import type {
    BalanceView,
    OpenLinkAction,
    PaymentMethodView,
    Translate,
  } from "$lib/webapp/types.js";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import { formatMoney } from "$lib/webapp/formatters.js";
  import { availableBalanceTopupMethods } from "$lib/webapp/balanceUiPolicy.js";

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

  const MANUAL_AMOUNT_DEBOUNCE_MS = 180;

  let amount = $state<number | undefined>(0);
  let selectedMethod = $state("");
  let busy = $state(false);
  let error = $state("");
  let buttonAnimatedAmount = $state(0);
  let inputAnimatedAmount = $state(0);
  let inputAnimationVisible = $state(false);
  let manualAmountTimer: number | undefined;

  const availableMethods = $derived(availableBalanceTopupMethods(methods));
  const minimum = $derived(Number(balance.topup_min_amount || 0));
  const maximum = $derived(Number(balance.topup_max_amount || 0));
  const presets = $derived(
    (Array.isArray(balance.topup_presets) ? balance.topup_presets : [])
      .map(Number)
      .filter((value) => Number.isFinite(value) && value >= minimum && value <= maximum)
  );
  const numericAmount = $derived(Number(amount || 0));
  const valid = $derived(
    numericAmount >= minimum && numericAmount <= maximum && !!selectedMethod && !busy
  );
  const currencySymbol = $derived(
    String(balance.currency || "")
      .trim()
      .toUpperCase() === "RUB"
      ? "₽"
      : balance.currency
  );
  const animatedNumberFormat = $derived({
    maximumFractionDigits: Math.max(0, Number(balance.currency_scale || 0)),
  });

  function selectMethod(methodId: string): void {
    selectedMethod = methodId;
    error = "";
  }

  function selectPreset(value: number): void {
    window.clearTimeout(manualAmountTimer);
    amount = value;
    buttonAnimatedAmount = value;
    inputAnimatedAmount = value;
    inputAnimationVisible = true;
    error = "";
  }

  function stopInputAnimation(): void {
    inputAnimationVisible = false;
  }

  function handleManualAmountInput(event: Event): void {
    stopInputAnimation();
    window.clearTimeout(manualAmountTimer);
    const nextValue = (event.currentTarget as HTMLInputElement).valueAsNumber;
    const safeValue = Number.isFinite(nextValue) ? nextValue : 0;
    manualAmountTimer = window.setTimeout(() => {
      buttonAnimatedAmount = safeValue;
      manualAmountTimer = undefined;
    }, MANUAL_AMOUNT_DEBOUNCE_MS);
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
          body: JSON.stringify({ method: selectedMethod, amount: numericAmount }),
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
    if (!open) {
      window.clearTimeout(manualAmountTimer);
      stopInputAnimation();
      return;
    }
    const initialAmount = presets[0] || minimum || 0;
    amount = initialAmount;
    buttonAnimatedAmount = initialAmount;
    inputAnimatedAmount = initialAmount;
    inputAnimationVisible = false;
    selectedMethod = String(
      availableMethods.find((method) => method.id === selectedMethod)?.id ||
        availableMethods[0]?.id ||
        ""
    );
    error = "";
  });

  onDestroy(() => {
    window.clearTimeout(manualAmountTimer);
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
  scrollType="scroll"
>
  <div class="balance-topup-body">
    <div class="balance-topup-current">
      <span><WalletCards size={22} /></span>
      <div>
        <small>{t("wa_balance_available", {}, "Available")}</small>
        <strong>{formatMoney(balance.amount, balance.currency)}</strong>
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
          class:amount-input-animating={inputAnimationVisible}
          oninput={handleManualAmountInput}
          onfocus={stopInputAnimation}
        />
        <span
          class:balance-amount-animation-visible={inputAnimationVisible}
          class="balance-amount-animation"
          aria-hidden="true"
        >
          <AnimatedNumber
            value={inputAnimatedAmount}
            format={animatedNumberFormat}
            replaceAnimations
          />
        </span>
        <b>{currencySymbol}</b>
      </div>
      <small>
        {t("wa_balance_topup_limits", { min: minimum, max: maximum }, "From {min} to {max}")}
      </small>
    </label>
    {#if presets.length}
      <div class="balance-presets">
        {#each presets as preset}
          <button
            type="button"
            class:active={amount === preset}
            onclick={() => selectPreset(preset)}
          >
            +{formatMoney(preset, balance.currency)}
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
    <Button class="wide bottom-action payment-submit-button" onclick={submit} disabled={!valid}>
      {t("wa_pay", {}, "Pay")}
      <strong>
        <AnimatedNumber
          value={buttonAnimatedAmount}
          suffix={` ${currencySymbol}`}
          ariaLabel={formatMoney(buttonAnimatedAmount, balance.currency)}
          format={animatedNumberFormat}
        />
      </strong>
      <LockKeyhole size={17} />
    </Button>
  </div>
</Dialog>

<style>
  .balance-topup-body {
    display: grid;
    gap: 13px;
  }
  .balance-topup-current {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 13px;
    border-radius: var(--radius-card);
    background: color-mix(in srgb, var(--accent) 12%, var(--panel-2));
  }
  .balance-topup-current > span {
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    border-radius: var(--radius-inner);
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
    border-radius: var(--radius-inner);
    color: var(--text);
    background: var(--panel-2);
    font: inherit;
    font-size: 18px;
    font-weight: 700;
  }
  .balance-amount-field input.amount-input-animating {
    color: transparent;
    caret-color: transparent;
  }
  .balance-amount-animation {
    position: absolute;
    top: 50%;
    left: 13px;
    z-index: 1;
    transform: translateY(-50%);
    color: var(--text);
    font-size: 18px;
    font-weight: 700;
    pointer-events: none;
    visibility: hidden;
    opacity: 0;
  }
  .balance-amount-animation-visible {
    visibility: visible;
    opacity: 1;
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
    border-radius: var(--radius-inner);
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
