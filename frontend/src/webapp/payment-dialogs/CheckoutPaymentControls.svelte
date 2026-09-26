<script lang="ts">
  import Button from "$components/ui/button.svelte";
  import Input from "$components/ui/input.svelte";
  import { LockKeyhole } from "$components/ui/icons.js";
  import {
    AnimatedPrice,
    EmptyCard,
    PaymentMethodPicker,
  } from "$components/patterns/webapp/index.js";
  import CheckoutPromoRow from "../CheckoutPromoRow.svelte";
  import PartnerBalanceDiscount from "./PartnerBalanceDiscount.svelte";
  import type { ApiClient, BalanceResponse } from "$lib/webapp/publicApi.js";
  import type { PaymentMethodView, PlanView, StringAction, Translate } from "$lib/webapp/types.js";

  type LabelPricePair = { base: string; discounted: string };
  type PlanPricePair = { base: PlanView; discounted: PlanView };

  let {
    api,
    paymentModalOpen = false,
    partnerAmount = 0,
    partnerCurrency = "",
    partnerEligible = false,
    partnerMinimum = 0,
    prefetchedBalance,
    balancePreloadComplete = false,
    balanceSource = $bindable<"user" | "partner" | null>(null),
    partnerBalanceDiscount = $bindable(0),
    hasMethods = false,
    paymentMethods = [],
    selectedMethod = "",
    payerEmail = $bindable(""),
    payerPhone = $bindable(""),
    paymentMethodsDisplayMode = "dropdown",
    selectPaymentMethod = () => {},
    checkoutQuoteError = "",
    showCheckoutPromo = false,
    checkoutPromoInput = "",
    checkoutPromoAppliedCode = "",
    checkoutPromoIsError = false,
    checkoutPromoStatus = "",
    applyCheckoutPromo = () => {},
    clearCheckoutPromo = () => {},
    setCheckoutPromoInput = () => {},
    payDisabled = false,
    createPayment = () => {},
    partnerPrice = null,
    promoPrice = null,
    selectedPlan = null,
    quotedPlan = null,
    providerManagesPrice = false,
    fallbackPrice = "",
    replacePriceAnimations = false,
    priceUpdateIntervalMs = 0,
    t = (key) => key,
  }: {
    api: ApiClient["api"];
    paymentModalOpen?: boolean;
    partnerAmount?: number;
    partnerCurrency?: string;
    partnerEligible?: boolean;
    partnerMinimum?: number;
    prefetchedBalance?: BalanceResponse | null;
    balancePreloadComplete?: boolean;
    balanceSource?: "user" | "partner" | null;
    partnerBalanceDiscount?: number;
    hasMethods?: boolean;
    paymentMethods?: PaymentMethodView[];
    selectedMethod?: string;
    payerEmail?: string;
    payerPhone?: string;
    paymentMethodsDisplayMode?: "dropdown" | "buttons" | string;
    selectPaymentMethod?: (methodId: string) => void;
    checkoutQuoteError?: string;
    showCheckoutPromo?: boolean;
    checkoutPromoInput?: string;
    checkoutPromoAppliedCode?: string;
    checkoutPromoIsError?: boolean;
    checkoutPromoStatus?: string;
    applyCheckoutPromo?: () => unknown;
    clearCheckoutPromo?: () => unknown;
    setCheckoutPromoInput?: StringAction;
    payDisabled?: boolean;
    createPayment?: () => unknown;
    partnerPrice?: LabelPricePair | null;
    promoPrice?: PlanPricePair | null;
    selectedPlan?: PlanView | null;
    quotedPlan?: PlanView | null;
    providerManagesPrice?: boolean;
    fallbackPrice?: string;
    replacePriceAnimations?: boolean;
    priceUpdateIntervalMs?: number;
    t?: Translate;
  } = $props();
</script>

<div class="payment-divider" aria-hidden="true"></div>
{#if hasMethods}
  <PaymentMethodPicker
    methods={paymentMethods}
    {selectedMethod}
    mode={paymentMethodsDisplayMode}
    {t}
    onSelect={selectPaymentMethod}
  />
{:else}
  <EmptyCard>{t("wa_payment_methods_not_configured")}</EmptyCard>
{/if}
{#if String(selectedMethod || "").toLowerCase() === "wata_subscription"}
  <div class="wata-subscription-contacts">
    <p>{t("wa_wata_subscription_contacts_hint")}</p>
    <label>
      <span>{t("wa_wata_subscription_email")}</span>
      <Input
        bind:value={payerEmail}
        type="email"
        autocomplete="email"
        placeholder={t("wa_email_placeholder")}
        required
      />
    </label>
    <label>
      <span>{t("wa_wata_subscription_phone")}</span>
      <Input
        bind:value={payerPhone}
        type="tel"
        autocomplete="tel"
        inputmode="tel"
        placeholder="+79991234567"
        required
      />
    </label>
  </div>
{/if}
{#if checkoutQuoteError}
  <small class="checkout-quote-error">
    {t("wa_checkout_quote_failed", {}, "Could not confirm the price. Try again.")}
  </small>
{/if}
{#if showCheckoutPromo}
  <CheckoutPromoRow
    value={checkoutPromoInput}
    appliedCode={checkoutPromoAppliedCode}
    isError={checkoutPromoIsError}
    status={checkoutPromoStatus}
    onApply={applyCheckoutPromo}
    onClear={clearCheckoutPromo}
    onValueChange={setCheckoutPromoInput}
    {t}
  />
{/if}
<PartnerBalanceDiscount
  {api}
  open={paymentModalOpen}
  amount={partnerAmount}
  currency={partnerCurrency}
  eligible={partnerEligible}
  minimumExternalAmount={partnerMinimum}
  {prefetchedBalance}
  {balancePreloadComplete}
  bind:source={balanceSource}
  bind:discount={partnerBalanceDiscount}
  {t}
/>
<Button
  class="wide bottom-action payment-submit-button"
  onclick={createPayment}
  disabled={payDisabled}
>
  {t("wa_pay")}
  {#if partnerPrice}
    <span class="promo-price-pair">
      <s>{partnerPrice.base}</s>
      <b>{partnerPrice.discounted}</b>
    </span>
  {:else if selectedPlan && !providerManagesPrice}
    {#if promoPrice}
      <span class="promo-price-pair">
        <s
          ><AnimatedPrice
            plan={promoPrice.base}
            method={selectedMethod}
            replaceAnimations={replacePriceAnimations}
            updateIntervalMs={priceUpdateIntervalMs}
          /></s
        >
        <b
          ><AnimatedPrice
            plan={promoPrice.discounted}
            method={selectedMethod}
            replaceAnimations={replacePriceAnimations}
            updateIntervalMs={priceUpdateIntervalMs}
          /></b
        >
      </span>
    {:else}
      <AnimatedPrice
        plan={quotedPlan}
        method={selectedMethod}
        replaceAnimations={replacePriceAnimations}
        updateIntervalMs={priceUpdateIntervalMs}
      />
    {/if}
  {:else}
    {selectedPlan ? fallbackPrice : ""}
  {/if}
  <LockKeyhole size={17} />
</Button>

<style>
  .wata-subscription-contacts {
    display: grid;
    gap: 10px;
  }

  .wata-subscription-contacts p {
    margin: 0;
    color: var(--muted-foreground);
    font-size: 13px;
    line-height: 1.4;
  }

  .wata-subscription-contacts label {
    display: grid;
    gap: 6px;
  }

  .wata-subscription-contacts label > span {
    font-size: 13px;
    font-weight: 700;
  }
</style>
