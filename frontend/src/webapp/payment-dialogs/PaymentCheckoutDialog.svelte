<script lang="ts">
  import { ArrowLeft, ArrowRight, CheckCircle2, LockKeyhole } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import Checkbox from "$components/ui/checkbox.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { EmptyCard, PaymentMethodGrid } from "$components/patterns/webapp/index.js";
  import CheckoutPromoRow from "../CheckoutPromoRow.svelte";
  import {
    planKey as planKeyFn,
    planDisplayTitle as planDisplayTitleFn,
    planSubtitle as planSubtitleFn,
    planUnitHint as planUnitHintFn,
    tariffLimitLabel as tariffLimitLabelFn,
    priceLabel as priceLabelFn,
    firstAvailableMethod,
    methodSelectable,
    methodsForPlan,
  } from "$lib/webapp/tariffs.js";
  import type {
    PaymentMethodView,
    PlanView,
    SubscriptionView,
    TariffView,
    TermUnitLabel,
    Translate,
    VoidAction,
  } from "$lib/webapp/types.js";

  let {
    createPayment = () => {},
    hasMultipleTariffs = false,
    methods = [],
    payBusy = false,
    paymentModalOpen = $bindable(false),
    paymentStep = $bindable("tariff"),
    plans = [],
    selectedMethod = $bindable(""),
    selectedPlan = $bindable(null),
    selectedTariff = null,
    selectedTariffKey = $bindable(""),
    selectedTariffPlans = [],
    renewHwidDevices = $bindable(true),
    singleTariffMode = false,
    subscription = {},
    subscriptionPurchaseDescription = "",
    tariffCatalog = [],
    tariffMode = false,
    trafficMode = false,
    closePaymentModal = () => {},
    checkoutPromoAppliedCode = "",
    checkoutPromoInput = $bindable(""),
    checkoutPromoIsError = false,
    checkoutPromoPriceText = "",
    checkoutPromoStatus = "",
    checkoutPromoDiscountPercent = 0,
    checkoutPromoAppliesTo = "all",
    checkoutPromoMinSubscriptionMonths = null,
    checkoutPromoMinTrafficGb = null,
    applyCheckoutPromo = () => {},
    backToTariffList = () => {},
    clearCheckoutPromo = () => {},
    continueWithSelectedTariff = () => {},
    selectTariff = () => {},
    t = (key) => key,
    termUnitLabel = () => "",
  }: {
    createPayment?: VoidAction;
    hasMultipleTariffs?: boolean;
    methods?: PaymentMethodView[];
    payBusy?: boolean;
    paymentModalOpen?: boolean;
    paymentStep?: string;
    plans?: PlanView[];
    selectedMethod?: string;
    selectedPlan?: PlanView | null;
    selectedTariff?: TariffView | null;
    selectedTariffKey?: string;
    selectedTariffPlans?: PlanView[];
    renewHwidDevices?: boolean;
    singleTariffMode?: boolean;
    subscription?: SubscriptionView;
    subscriptionPurchaseDescription?: string;
    tariffCatalog?: TariffView[];
    tariffMode?: boolean;
    trafficMode?: boolean;
    closePaymentModal?: VoidAction;
    checkoutPromoAppliedCode?: string;
    checkoutPromoInput?: string;
    checkoutPromoIsError?: boolean;
    checkoutPromoPriceText?: string;
    checkoutPromoStatus?: string;
    checkoutPromoDiscountPercent?: number;
    checkoutPromoAppliesTo?: string;
    checkoutPromoMinSubscriptionMonths?: number | null;
    checkoutPromoMinTrafficGb?: number | null;
    applyCheckoutPromo?: VoidAction;
    backToTariffList?: VoidAction;
    clearCheckoutPromo?: VoidAction;
    continueWithSelectedTariff?: VoidAction;
    selectTariff?: (tariff: TariffView) => void;
    t?: Translate;
    termUnitLabel?: TermUnitLabel;
  } = $props();

  function priceLabel(plan: PlanView | null) {
    return priceLabelFn(plan, selectedMethod);
  }
  function methodUsesStars() {
    return String(selectedMethod || "")
      .toLowerCase()
      .includes("stars");
  }
  function hwidRenewalFor(plan: PlanView | null) {
    return plan?.hwid_renewal?.available ? plan.hwid_renewal : null;
  }
  function isSubscriptionPlan(plan: PlanView | null) {
    const saleMode = String(plan?.sale_mode || "subscription").toLowerCase();
    return saleMode === "subscription";
  }
  function hwidRenewalAvailableForMethod(plan: PlanView | null) {
    const renewal = hwidRenewalFor(plan);
    if (!subscription?.active || !isSubscriptionPlan(plan) || !renewal) return false;
    if (methodUsesStars()) return Number(renewal.stars_price || 0) > 0;
    return Number(renewal.price || 0) > 0;
  }
  function planWithSelectedHwidRenewal(plan: PlanView | null) {
    if (!plan || !renewHwidDevices || !hwidRenewalAvailableForMethod(plan)) return plan;
    const renewal = hwidRenewalFor(plan);
    if (!renewal) return plan;
    const withRenewal: PlanView = {
      ...plan,
      price: Number(plan.price || 0) + Number(renewal.price || 0),
    };
    if (Number(plan.stars_price || 0) > 0 && Number(renewal.stars_price || 0) > 0) {
      withRenewal.stars_price = Number(plan.stars_price || 0) + Number(renewal.stars_price || 0);
    }
    return withRenewal;
  }
  function paymentPriceLabel(plan: PlanView | null) {
    return priceLabelFn(planWithSelectedHwidRenewal(plan), selectedMethod);
  }
  function checkoutPaymentPriceLabel(plan: PlanView | null) {
    const promoPrice = checkoutPromoPriceParts(planWithSelectedHwidRenewal(plan));
    if (promoPrice) return promoPrice.discounted;
    if (checkoutPromoAppliedCode && checkoutPromoPriceText) return checkoutPromoPriceText;
    return paymentPriceLabel(plan);
  }
  function checkoutPromoDiscount() {
    const value = Number(checkoutPromoDiscountPercent || 0);
    if (!checkoutPromoAppliedCode || !Number.isFinite(value) || value <= 0) return 0;
    return Math.min(100, value);
  }
  function planSaleModeBase(plan: PlanView | null) {
    const fallback =
      Number(plan?.device_count || 0) > 0
        ? "hwid_devices"
        : Number(plan?.traffic_gb || 0) > 0
          ? "traffic"
          : "subscription";
    const saleMode = String(plan?.sale_mode || fallback).toLowerCase();
    if (["traffic", "traffic_package"].includes(saleMode)) return "traffic";
    if (["topup", "premium_topup"].includes(saleMode)) return "traffic_topup";
    if (["hwid_device", "hwid_devices", "hwid_devices_renewal"].includes(saleMode)) return "hwid";
    return "subscription";
  }
  function checkoutPromoScopeMatches(plan: PlanView | null) {
    const scope = String(checkoutPromoAppliesTo || "all").toLowerCase();
    const base = planSaleModeBase(plan);
    return scope === "all" || scope === base;
  }
  function checkoutPromoThresholdMatches(plan: PlanView | null) {
    const base = planSaleModeBase(plan);
    const minMonths = Number(checkoutPromoMinSubscriptionMonths || 0);
    const minTrafficGb = Number(checkoutPromoMinTrafficGb || 0);
    if (base === "subscription" && minMonths > 0) {
      return Number(plan?.months || 0) >= minMonths;
    }
    if ((base === "traffic" || base === "traffic_topup") && minTrafficGb > 0) {
      return Number(plan?.traffic_gb || plan?.months || 0) >= minTrafficGb;
    }
    return true;
  }
  function checkoutPromoAffectsPlan(plan: PlanView | null) {
    return (
      checkoutPromoDiscount() > 0 &&
      checkoutPromoScopeMatches(plan) &&
      checkoutPromoThresholdMatches(plan)
    );
  }
  function discountedCheckoutPlan(plan: PlanView | null) {
    const discount = checkoutPromoDiscount();
    if (!plan || discount <= 0) return plan;
    const multiplier = Math.max(0, 1 - discount / 100);
    const next: PlanView = { ...plan };
    if (Number(plan.price || 0) > 0) {
      next.price = Math.round(Number(plan.price || 0) * multiplier * 100) / 100;
    }
    if (Number(plan.stars_price || 0) > 0) {
      next.stars_price = Math.max(1, Math.round(Number(plan.stars_price || 0) * multiplier));
    }
    return next;
  }
  function checkoutPromoPriceParts(plan: PlanView | null) {
    if (!checkoutPromoAffectsPlan(plan)) return null;
    return {
      base: priceLabelFn(plan, selectedMethod),
      discounted: priceLabelFn(discountedCheckoutPlan(plan), selectedMethod),
    };
  }
  const selectedPlanForPayment = $derived(planWithSelectedHwidRenewal(selectedPlan));
  const paymentMethods = $derived(methodsForPlan(methods, selectedPlanForPayment));
  const paymentMethodSelected = $derived(methodSelectable(paymentMethods, selectedMethod));

  $effect(() => {
    if (!paymentModalOpen || paymentStep !== "checkout" || !selectedPlan) return;
    const firstMethod = firstAvailableMethod(paymentMethods);
    if (firstMethod && !methodSelectable(paymentMethods, selectedMethod)) {
      selectedMethod = firstMethod;
    }
  });
  function hwidRenewalPriceLabel(plan: PlanView | null = selectedPlan) {
    const renewal = hwidRenewalFor(plan);
    if (!renewal) return "";
    return priceLabelFn(
      {
        price: renewal.price || 0,
        stars_price: renewal.stars_price,
        currency: renewal.currency || plan?.currency,
      },
      selectedMethod
    );
  }
  function showHwidRenewalBlock() {
    return hwidRenewalAvailableForMethod(selectedPlan);
  }
  function showHwidRenewalUnavailableNote() {
    return Boolean(
      subscription?.active &&
      Number(subscription?.extra_hwid_devices || 0) > 0 &&
      isSubscriptionPlan(selectedPlan) &&
      !showHwidRenewalBlock()
    );
  }
  function hwidRenewalCount(plan: PlanView | null = selectedPlan) {
    return Number(hwidRenewalFor(plan)?.device_count || subscription?.extra_hwid_devices || 0);
  }
  function hwidRenewalBonusLabel(plan: PlanView | null = selectedPlan) {
    const renewal = hwidRenewalFor(plan);
    const bonusGb = Number(renewal?.traffic_bonus_gb || 0);
    if (!(bonusGb > 0)) return "";
    return t("wa_hwid_devices_traffic_bonus", { gb: String(bonusGb) });
  }
  function hwidRenewalHint(plan: PlanView | null = selectedPlan) {
    const renewal = hwidRenewalFor(plan);
    if (renewal?.valid_from_text && renewal?.valid_until_text) {
      return t("wa_hwid_devices_renewal_checkbox_hint", {
        from: renewal.valid_from_text,
        to: renewal.valid_until_text,
      });
    }
    return t("wa_hwid_devices_renewal_checkbox_hint_short");
  }
  function showHwidDesyncNotice() {
    return Boolean(
      subscription?.device_topup_renewal_available &&
      subscription?.extra_hwid_devices_valid_until_text
    );
  }
  function planKey(plan: PlanView | null) {
    return planKeyFn(plan);
  }
  function planDisplayTitle(plan: PlanView | null) {
    return planDisplayTitleFn(plan, { trafficMode, t });
  }
  function planSubtitle(plan: PlanView | null) {
    return planSubtitleFn(plan, { t, termUnitLabel });
  }
  function planUnitHint(plan: PlanView | null) {
    return planUnitHintFn(plan, { trafficMode, selectedMethod, t });
  }
  function tariffLimitLabel(tariff: TariffView) {
    return tariffLimitLabelFn(tariff, { t });
  }

  function checkoutPromoBlock() {
    return Boolean(checkoutPromoAppliedCode || checkoutPromoStatus || selectedPlan);
  }

  function paymentTitle() {
    if (singleTariffMode) {
      return selectedTariff?.billing_model === "traffic"
        ? t("wa_traffic_packages_title")
        : t("wa_subscription_title");
    }
    if (tariffMode) return t("wa_tariffs_title");
    return trafficMode ? t("wa_traffic_packages_title") : t("wa_subscription_title");
  }

  function paymentDescription() {
    if (tariffMode) {
      if (singleTariffMode) {
        return selectedTariff?.billing_model === "traffic"
          ? t("wa_traffic_packages_choose")
          : t("wa_subscription_choose_period");
      }
      return paymentStep === "checkout" && selectedTariff
        ? t("wa_tariff_choose_period_payment", { tariff: selectedTariff.title })
        : t("wa_tariffs_choose");
    }
    return trafficMode ? t("wa_traffic_packages_choose") : t("wa_subscription_choose_period");
  }

  function showSubscriptionPurchaseDescription() {
    if (!subscriptionPurchaseDescription || trafficMode) return false;
    if (!tariffMode) return true;
    if (paymentStep === "tariff") return false;
    return String(selectedTariff?.billing_model || "period").toLowerCase() !== "traffic";
  }
</script>

<Dialog
  open={paymentModalOpen}
  title={paymentTitle()}
  description={paymentDescription()}
  closeLabel={t("wa_close")}
  onclose={closePaymentModal}
  class="payment-dialog-card webapp-payment-dialog"
>
  <div class="payment-dialog-body">
    {#if tariffMode && !singleTariffMode && paymentStep === "tariff"}
      {#if tariffCatalog.length}
        <div class="option-list tariff-list">
          {#each tariffCatalog as tariff}
            <button
              class:active={selectedTariffKey === tariff.key}
              class="option-row tariff-row"
              type="button"
              onclick={() => selectTariff(tariff)}
            >
              <span class="option-row-main">
                <strong>{tariff.title}</strong>
                <small>{tariff.description || t("wa_tariff_no_description")}</small>
              </span>
              <span class="option-row-meta">
                <em>{tariffLimitLabel(tariff)}</em>
                {#if selectedTariffKey === tariff.key}
                  <CheckCircle2 size={18} />
                {:else}
                  <ArrowRight size={17} />
                {/if}
              </span>
            </button>
          {/each}
        </div>
        <Button
          class="wide bottom-action payment-submit-button"
          onclick={continueWithSelectedTariff}
          disabled={!selectedTariffKey}
        >
          {t("wa_next")}
          <ArrowRight size={17} />
        </Button>
      {:else}
        <EmptyCard>{t("wa_no_tariff_change_options")}</EmptyCard>
      {/if}
    {:else if tariffMode}
      {#if !singleTariffMode && !(subscription?.active && subscription?.tariff_key && tariffCatalog.some((t) => t.key === subscription.tariff_key))}
        <button class="back-inline" type="button" onclick={backToTariffList}>
          <ArrowLeft size={16} />
          {t("wa_back_to_tariffs")}
        </button>
      {/if}
      {#if hasMultipleTariffs && selectedTariff}
        <p class="tariff-step-caption">
          {t("wa_selected_tariff", { tariff: selectedTariff.title })}
        </p>
      {/if}
      {#if selectedTariffPlans.length}
        {#if showSubscriptionPurchaseDescription()}
          <div class="subscription-purchase-description">
            <p>{subscriptionPurchaseDescription}</p>
          </div>
        {/if}
        {#if showHwidRenewalBlock()}
          <label class="hwid-renewal-option">
            <Checkbox
              checked={renewHwidDevices}
              ariaLabel={t("wa_hwid_devices_renewal_checkbox_aria")}
              onCheckedChange={(checked) => (renewHwidDevices = checked)}
            />
            <span>
              <strong>
                {t("wa_hwid_devices_renewal_checkbox", {
                  count: hwidRenewalCount(),
                  price: hwidRenewalPriceLabel(),
                })}
              </strong>
              <small>{hwidRenewalHint()}</small>
              {#if hwidRenewalBonusLabel()}
                <small class="hwid-renewal-bonus">{hwidRenewalBonusLabel()}</small>
              {/if}
              {#if showHwidDesyncNotice()}
                <small class="hwid-renewal-warning">
                  {t("wa_hwid_devices_desync_notice", {
                    date: subscription.extra_hwid_devices_valid_until_text,
                  })}
                </small>
              {/if}
            </span>
          </label>
        {:else if showHwidRenewalUnavailableNote()}
          <div class="subscription-purchase-description">
            <p>
              {t("wa_hwid_devices_renewal_unavailable", {
                count: Number(subscription.extra_hwid_devices || 0),
                date: subscription.extra_hwid_devices_valid_until_text || "",
              })}
            </p>
          </div>
        {/if}
        <div class="period-grid period-grid-two-columns">
          {#each selectedTariffPlans as plan}
            {@const promoPrice = checkoutPromoPriceParts(plan)}
            <button
              class:active={planKey(selectedPlan) === planKey(plan)}
              class="period-card"
              type="button"
              onclick={() => (selectedPlan = plan)}
            >
              <strong>{planSubtitle(plan) || planDisplayTitle(plan)}</strong>
              {#if promoPrice}
                <span class="promo-price-pair">
                  <s>{promoPrice.base}</s>
                  <b>{promoPrice.discounted}</b>
                </span>
              {:else}
                <span>{priceLabel(plan)}</span>
              {/if}
              {#if planUnitHint(plan)}
                <small>{planUnitHint(plan)}</small>
              {/if}
              {#if planKey(selectedPlan) === planKey(plan)}
                <CheckCircle2 size={18} />
              {/if}
            </button>
          {/each}
        </div>
        <div class="payment-divider" aria-hidden="true"></div>
        {#if methods.length}
          <PaymentMethodGrid
            methods={paymentMethods}
            {selectedMethod}
            {t}
            onSelect={(id) => (selectedMethod = id)}
          />
        {:else}
          <EmptyCard>{t("wa_payment_methods_not_configured")}</EmptyCard>
        {/if}
        {#if checkoutPromoBlock()}
          <CheckoutPromoRow
            bind:value={checkoutPromoInput}
            appliedCode={checkoutPromoAppliedCode}
            isError={checkoutPromoIsError}
            status={checkoutPromoStatus}
            onApply={applyCheckoutPromo}
            onClear={clearCheckoutPromo}
            {t}
          />
        {/if}
        <Button
          class="wide bottom-action payment-submit-button"
          onclick={createPayment}
          disabled={!selectedPlan || !paymentMethodSelected || payBusy}
        >
          {t("wa_pay")}
          {selectedPlan ? checkoutPaymentPriceLabel(selectedPlan) : ""}
          <LockKeyhole size={17} />
        </Button>
      {:else}
        <EmptyCard>{t("wa_no_tariff_change_options")}</EmptyCard>
      {/if}
    {:else}
      <!--
        Legacy / non-tariff mode (no JSON tariffs catalog OR traffic-only).
        Previously this block was also reached *in addition* to the tariff
        branch above, so users on legacy mode saw the period grid, payment
        method grid and pay button duplicated.
      -->
      {#if showSubscriptionPurchaseDescription()}
        <div class="subscription-purchase-description">
          <p>{subscriptionPurchaseDescription}</p>
        </div>
      {/if}
      {#if showHwidRenewalBlock()}
        <label class="hwid-renewal-option">
          <Checkbox
            checked={renewHwidDevices}
            ariaLabel={t("wa_hwid_devices_renewal_checkbox_aria")}
            onCheckedChange={(checked) => (renewHwidDevices = checked)}
          />
          <span>
            <strong>
              {t("wa_hwid_devices_renewal_checkbox", {
                count: hwidRenewalCount(),
                price: hwidRenewalPriceLabel(),
              })}
            </strong>
            <small>{hwidRenewalHint()}</small>
            {#if hwidRenewalBonusLabel()}
              <small class="hwid-renewal-bonus">{hwidRenewalBonusLabel()}</small>
            {/if}
            {#if showHwidDesyncNotice()}
              <small class="hwid-renewal-warning">
                {t("wa_hwid_devices_desync_notice", {
                  date: subscription.extra_hwid_devices_valid_until_text,
                })}
              </small>
            {/if}
          </span>
        </label>
      {:else if showHwidRenewalUnavailableNote()}
        <div class="subscription-purchase-description">
          <p>
            {t("wa_hwid_devices_renewal_unavailable", {
              count: Number(subscription.extra_hwid_devices || 0),
              date: subscription.extra_hwid_devices_valid_until_text || "",
            })}
          </p>
        </div>
      {/if}
      <div class="period-grid period-grid-two-columns">
        {#each plans as plan}
          {@const promoPrice = checkoutPromoPriceParts(plan)}
          <button
            class:active={planKey(selectedPlan) === planKey(plan)}
            class="period-card"
            type="button"
            onclick={() => (selectedPlan = plan)}
          >
            <strong>{planDisplayTitle(plan)}</strong>
            {#if planSubtitle(plan)}
              <em>{planSubtitle(plan)}</em>
            {/if}
            {#if promoPrice}
              <span class="promo-price-pair">
                <s>{promoPrice.base}</s>
                <b>{promoPrice.discounted}</b>
              </span>
            {:else}
              <span>{priceLabel(plan)}</span>
            {/if}
            {#if planUnitHint(plan)}
              <small>{planUnitHint(plan)}</small>
            {/if}
            {#if planKey(selectedPlan) === planKey(plan)}
              <CheckCircle2 size={18} />
            {/if}
          </button>
        {/each}
      </div>
      <div class="payment-divider" aria-hidden="true"></div>
      {#if methods.length}
        <PaymentMethodGrid
          methods={paymentMethods}
          {selectedMethod}
          {t}
          onSelect={(id) => (selectedMethod = id)}
        />
      {:else}
        <EmptyCard>{t("wa_payment_methods_not_configured")}</EmptyCard>
      {/if}
      {#if checkoutPromoBlock()}
        <CheckoutPromoRow
          bind:value={checkoutPromoInput}
          appliedCode={checkoutPromoAppliedCode}
          isError={checkoutPromoIsError}
          status={checkoutPromoStatus}
          onApply={applyCheckoutPromo}
          onClear={clearCheckoutPromo}
          {t}
        />
      {/if}
      <Button
        class="wide bottom-action payment-submit-button"
        onclick={createPayment}
        disabled={!selectedPlan || !paymentMethodSelected || payBusy}
      >
        {t("wa_pay")}
        {selectedPlan ? checkoutPaymentPriceLabel(selectedPlan) : ""}
        <LockKeyhole size={17} />
      </Button>
    {/if}
  </div>
</Dialog>
