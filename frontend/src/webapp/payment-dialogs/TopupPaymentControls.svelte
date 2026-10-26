<script lang="ts">
  import Button from "$components/ui/button.svelte";
  import { CalendarDays, LockKeyhole } from "$components/ui/icons.js";
  import { PaymentMethodPicker } from "$components/patterns/webapp/index.js";
  import type { PartnerBalancePaymentOptions } from "$lib/webapp/billingActions.js";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import {
    SUBSCRIPTION_DAYS_METHOD,
    subscriptionDaysQuote,
    subscriptionDaysQuoteUsable,
  } from "$lib/webapp/subscriptionDays.js";
  import { methodSelectable } from "$lib/webapp/tariffs.js";
  import type { PaymentMethodView, PlanView, Translate } from "$lib/webapp/types.js";
  import CheckoutPromoRow from "../CheckoutPromoRow.svelte";
  import CheckoutPaymentFallback from "./CheckoutPaymentFallback.svelte";
  import PartnerBalanceDiscount from "./PartnerBalanceDiscount.svelte";
  import SubscriptionDaysQuote from "./SubscriptionDaysQuote.svelte";

  type PromoControls = {
    visible: boolean;
    input: string;
    code: string;
    isError: boolean;
    status: string;
    apply: () => unknown;
    clear: () => unknown;
    change: (value: string) => unknown;
  };

  let {
    api,
    open,
    plan,
    methods,
    selectedMethod = $bindable(""),
    t,
    currentLang = "ru",
    devices = false,
    busy = false,
    displayMode = "dropdown",
    createPayment,
    failedMethods = [],
    onProviderUnavailable,
    priceLabel = "",
    priceParts = null,
    promo,
    partnerAmount = 0,
    partnerCurrency = "",
    partnerEligible = false,
    partnerMinimum = 0,
    balanceSource = $bindable<"user" | "partner" | null>(null),
    partnerDiscount = $bindable(0),
    daysSelected = $bindable(false),
  }: {
    api: ApiClient["api"];
    open: boolean;
    plan: PlanView | null;
    methods: PaymentMethodView[];
    selectedMethod?: string;
    t: Translate;
    currentLang?: string;
    devices?: boolean;
    busy?: boolean;
    displayMode?: string;
    createPayment: (options?: PartnerBalancePaymentOptions) => unknown;
    failedMethods?: string[];
    onProviderUnavailable?: (method: string) => void;
    priceLabel?: string;
    priceParts?: { base: string; discounted: string } | null;
    promo: PromoControls;
    partnerAmount?: number;
    partnerCurrency?: string;
    partnerEligible?: boolean;
    partnerMinimum?: number;
    balanceSource?: "user" | "partner" | null;
    partnerDiscount?: number;
    daysSelected?: boolean;
  } = $props();

  const method = $derived(daysSelected ? SUBSCRIPTION_DAYS_METHOD : selectedMethod);
  const quote = $derived(subscriptionDaysQuote(plan));
  const quoteUsable = $derived(subscriptionDaysQuoteUsable(quote));
  const canPay = $derived(
    Boolean(plan) && !busy && (daysSelected ? quoteUsable : methodSelectable(methods, method))
  );
  const inputId = $derived(`webapp-${devices ? "device-topup" : "topup"}-checkout-code`);

  $effect(() => {
    if (!open || !quote) daysSelected = false;
    else if (
      quoteUsable &&
      !methods.some((item) => item.id !== SUBSCRIPTION_DAYS_METHOD && !item.disabled)
    )
      daysSelected = true;
  });

  function selectMethod(value: string): void {
    daysSelected = value === SUBSCRIPTION_DAYS_METHOD;
    if (!daysSelected) selectedMethod = value;
  }

  function submit(): void {
    if (!canPay) return;
    void createPayment({
      paymentMethod: method,
      balanceSource: daysSelected ? null : balanceSource,
      onProviderUnavailable,
    });
  }
</script>

<PaymentMethodPicker
  {methods}
  selectedMethod={method}
  mode={displayMode}
  disabled={busy}
  {t}
  onSelect={selectMethod}
/>
{#if quote && (daysSelected || !quoteUsable)}
  <SubscriptionDaysQuote {quote} {devices} {currentLang} {t} />
{/if}
{#if !daysSelected}
  <CheckoutPaymentFallback
    {methods}
    {failedMethods}
    {selectedMethod}
    disabled={busy}
    onSelect={selectMethod}
    {t}
  />
  {#if promo.visible}
    <CheckoutPromoRow
      {inputId}
      inputName={inputId}
      value={promo.input}
      appliedCode={promo.code}
      isError={promo.isError}
      status={promo.status}
      onApply={promo.apply}
      onClear={promo.clear}
      onValueChange={promo.change}
      {t}
    />
  {/if}
  <PartnerBalanceDiscount
    {api}
    {open}
    amount={partnerAmount}
    currency={partnerCurrency}
    eligible={partnerEligible}
    minimumExternalAmount={partnerMinimum}
    bind:source={balanceSource}
    bind:discount={partnerDiscount}
    {t}
  />
{/if}
<Button class="wide bottom-action payment-submit-button" onclick={submit} disabled={!canPay}>
  {#if daysSelected}
    {t("wa_subscription_days_submit", { days: quote?.days_to_charge ?? "—" })}
    <CalendarDays size={17} />
  {:else}
    {t(devices ? "wa_pay" : "wa_buy_traffic")}
    {#if priceParts}
      <span class="promo-price-pair"><s>{priceParts.base}</s><b>{priceParts.discounted}</b></span>
    {:else}
      {priceLabel}
    {/if}
    <LockKeyhole size={17} />
  {/if}
</Button>
