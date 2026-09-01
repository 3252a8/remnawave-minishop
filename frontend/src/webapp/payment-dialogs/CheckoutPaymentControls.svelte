<script lang="ts">
  import Button from "$components/ui/button.svelte";
  import { LockKeyhole } from "$components/ui/icons.js";
  import {
    AnimatedPrice,
    EmptyCard,
    PaymentMethodPicker,
  } from "$components/patterns/webapp/index.js";
  import CheckoutPromoRow from "../CheckoutPromoRow.svelte";
  import PartnerBalanceDiscount from "./PartnerBalanceDiscount.svelte";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
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
    balanceSource = $bindable<"user" | "partner" | null>(null),
    partnerBalanceDiscount = $bindable(0),
    hasMethods = false,
    paymentMethods = [],
    selectedMethod = "",
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
    t = (key) => key,
  }: {
    api: ApiClient["api"];
    paymentModalOpen?: boolean;
    partnerAmount?: number;
    partnerCurrency?: string;
    partnerEligible?: boolean;
    partnerMinimum?: number;
    balanceSource?: "user" | "partner" | null;
    partnerBalanceDiscount?: number;
    hasMethods?: boolean;
    paymentMethods?: PaymentMethodView[];
    selectedMethod?: string;
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
          /></s
        >
        <b
          ><AnimatedPrice
            plan={promoPrice.discounted}
            method={selectedMethod}
            replaceAnimations={replacePriceAnimations}
          /></b
        >
      </span>
    {:else}
      <AnimatedPrice
        plan={quotedPlan}
        method={selectedMethod}
        replaceAnimations={replacePriceAnimations}
      />
    {/if}
  {:else}
    {selectedPlan ? fallbackPrice : ""}
  {/if}
  <LockKeyhole size={17} />
</Button>
