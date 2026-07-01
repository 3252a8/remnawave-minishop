<script lang="ts">
  import {
    ArrowLeft,
    ArrowRight,
    CheckCircle2,
    CircleX,
    LockKeyhole,
    TriangleAlert,
  } from "$components/ui/icons.js";
  import { Tooltip } from "$components/ui/primitives.js";

  import Button from "$components/ui/button.svelte";
  import Checkbox from "$components/ui/checkbox.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import EmailCodeScreen from "./auth/EmailCodeScreen.svelte";
  import Input from "$components/ui/input.svelte";
  import {
    EmptyCard,
    PaymentMethodGrid,
    StatusMessage,
  } from "$components/patterns/webapp/index.js";
  import CheckoutPromoRow from "./CheckoutPromoRow.svelte";
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
  } from "../lib/webapp/tariffs.js";

  type AnyRecord = Record<string, any>;
  type DeviceToDisconnect = {
    display_name?: string | null;
    index?: number | string | null;
  };
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type VoidAction = () => void;

  let {
    createPayment = () => {},
    deviceConfirmOpen = false,
    deviceDisconnectBusy = false,
    deviceToDisconnect = null,
    disconnectDevice = () => {},
    linkEmailBusy = false,
    linkEmailCode = $bindable(""),
    linkEmailFieldError = $bindable(""),
    linkEmailIsError = false,
    linkEmailOpen = false,
    linkEmailPending = "",
    linkEmailResendCooldown = 0,
    linkEmailStatus = "",
    linkEmailValue = $bindable(""),
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
    setPasswordBusy = false,
    setPasswordCode = $bindable(""),
    setPasswordConfirm = $bindable(""),
    setPasswordEmail = "",
    setPasswordIsError = false,
    setPasswordOpen = false,
    setPasswordPending = false,
    setPasswordResendCooldown = 0,
    setPasswordStatus = "",
    setPasswordValue = $bindable(""),
    singleTariffMode = false,
    subscription = {},
    subscriptionPurchaseDescription = "",
    tariffCatalog = [],
    tariffMode = false,
    trafficMode = false,
    closeDeviceDisconnectDialog = () => {},
    closeLinkEmailDialog = () => {},
    closePaymentModal = () => {},
    closeSetPasswordDialog = () => {},
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
    requestLinkEmailCode = () => {},
    requestSetPasswordCode = () => {},
    selectTariff = () => {},
    t = (key) => key,
    termUnitLabel = () => "",
    verifyLinkEmailCode = () => {},
    confirmSetPassword = () => {},
  }: {
    createPayment?: VoidAction;
    deviceConfirmOpen?: boolean;
    deviceDisconnectBusy?: boolean;
    deviceToDisconnect?: DeviceToDisconnect | null;
    disconnectDevice?: VoidAction;
    linkEmailBusy?: boolean;
    linkEmailCode?: string;
    linkEmailFieldError?: string;
    linkEmailIsError?: boolean;
    linkEmailOpen?: boolean;
    linkEmailPending?: string;
    linkEmailResendCooldown?: number;
    linkEmailStatus?: string;
    linkEmailValue?: string;
    hasMultipleTariffs?: boolean;
    methods?: AnyRecord[];
    payBusy?: boolean;
    paymentModalOpen?: boolean;
    paymentStep?: string;
    plans?: AnyRecord[];
    selectedMethod?: string;
    selectedPlan?: AnyRecord | null;
    selectedTariff?: AnyRecord | null;
    selectedTariffKey?: string;
    selectedTariffPlans?: AnyRecord[];
    renewHwidDevices?: boolean;
    setPasswordBusy?: boolean;
    setPasswordCode?: string;
    setPasswordConfirm?: string;
    setPasswordEmail?: string;
    setPasswordIsError?: boolean;
    setPasswordOpen?: boolean;
    setPasswordPending?: boolean;
    setPasswordResendCooldown?: number;
    setPasswordStatus?: string;
    setPasswordValue?: string;
    singleTariffMode?: boolean;
    subscription?: AnyRecord;
    subscriptionPurchaseDescription?: string;
    tariffCatalog?: AnyRecord[];
    tariffMode?: boolean;
    trafficMode?: boolean;
    closeDeviceDisconnectDialog?: VoidAction;
    closeLinkEmailDialog?: VoidAction;
    closePaymentModal?: VoidAction;
    closeSetPasswordDialog?: VoidAction;
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
    requestLinkEmailCode?: VoidAction;
    requestSetPasswordCode?: VoidAction;
    selectTariff?: (tariff: AnyRecord) => void;
    t?: Translate;
    termUnitLabel?: (value: number, unit: string) => string;
    verifyLinkEmailCode?: VoidAction;
    confirmSetPassword?: VoidAction;
  } = $props();

  function priceLabel(plan: AnyRecord | null) {
    return priceLabelFn(plan, selectedMethod);
  }
  function methodUsesStars() {
    return String(selectedMethod || "")
      .toLowerCase()
      .includes("stars");
  }
  function hwidRenewalFor(plan: AnyRecord | null) {
    return plan?.hwid_renewal?.available ? plan.hwid_renewal : null;
  }
  function isSubscriptionPlan(plan: AnyRecord | null) {
    const saleMode = String(plan?.sale_mode || "subscription").toLowerCase();
    return saleMode === "subscription";
  }
  function hwidRenewalAvailableForMethod(plan: AnyRecord | null) {
    const renewal = hwidRenewalFor(plan);
    if (!subscription?.active || !isSubscriptionPlan(plan) || !renewal) return false;
    if (methodUsesStars()) return Number(renewal.stars_price || 0) > 0;
    return Number(renewal.price || 0) > 0;
  }
  function planWithSelectedHwidRenewal(plan: AnyRecord | null) {
    if (!plan || !renewHwidDevices || !hwidRenewalAvailableForMethod(plan)) return plan;
    const renewal = hwidRenewalFor(plan);
    const withRenewal: AnyRecord = {
      ...plan,
      price: Number(plan.price || 0) + Number(renewal.price || 0),
    };
    if (Number(plan.stars_price || 0) > 0 && Number(renewal.stars_price || 0) > 0) {
      withRenewal.stars_price = Number(plan.stars_price || 0) + Number(renewal.stars_price || 0);
    }
    return withRenewal;
  }
  function paymentPriceLabel(plan: AnyRecord | null) {
    return priceLabelFn(planWithSelectedHwidRenewal(plan), selectedMethod);
  }
  function checkoutPaymentPriceLabel(plan: AnyRecord | null) {
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
  function planSaleModeBase(plan: AnyRecord | null) {
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
  function checkoutPromoScopeMatches(plan: AnyRecord | null) {
    const scope = String(checkoutPromoAppliesTo || "all").toLowerCase();
    const base = planSaleModeBase(plan);
    return scope === "all" || scope === base;
  }
  function checkoutPromoThresholdMatches(plan: AnyRecord | null) {
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
  function checkoutPromoAffectsPlan(plan: AnyRecord | null) {
    return (
      checkoutPromoDiscount() > 0 &&
      checkoutPromoScopeMatches(plan) &&
      checkoutPromoThresholdMatches(plan)
    );
  }
  function discountedCheckoutPlan(plan: AnyRecord | null) {
    const discount = checkoutPromoDiscount();
    if (!plan || discount <= 0) return plan;
    const multiplier = Math.max(0, 1 - discount / 100);
    const next: AnyRecord = { ...plan };
    if (Number(plan.price || 0) > 0) {
      next.price = Math.round(Number(plan.price || 0) * multiplier * 100) / 100;
    }
    if (Number(plan.stars_price || 0) > 0) {
      next.stars_price = Math.max(1, Math.round(Number(plan.stars_price || 0) * multiplier));
    }
    return next;
  }
  function checkoutPromoPriceParts(plan: AnyRecord | null) {
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
  function hwidRenewalPriceLabel(plan: AnyRecord | null = selectedPlan) {
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
  function hwidRenewalCount(plan: AnyRecord | null = selectedPlan) {
    return Number(hwidRenewalFor(plan)?.device_count || subscription?.extra_hwid_devices || 0);
  }
  function hwidRenewalHint(plan: AnyRecord | null = selectedPlan) {
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
  function planKey(plan: AnyRecord | null) {
    return planKeyFn(plan);
  }
  function planDisplayTitle(plan: AnyRecord | null) {
    return planDisplayTitleFn(plan, { trafficMode, t });
  }
  function planSubtitle(plan: AnyRecord | null) {
    return planSubtitleFn(plan, { t, termUnitLabel });
  }
  function planUnitHint(plan: AnyRecord | null) {
    return planUnitHintFn(plan, { trafficMode, selectedMethod, t });
  }
  function tariffLimitLabel(tariff: AnyRecord) {
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

<Dialog
  open={deviceConfirmOpen}
  title={t("wa_devices_disconnect_title")}
  description={t("wa_devices_disconnect_desc", {
    device:
      deviceToDisconnect?.display_name ||
      t("wa_device_fallback_name", { index: deviceToDisconnect?.index || "" }),
  })}
  closeLabel={t("wa_close")}
  onclose={closeDeviceDisconnectDialog}
  class="payment-dialog-card webapp-device-disconnect-dialog"
>
  <div class="payment-dialog-body">
    <Button
      variant="outline"
      class="wide device-danger-button"
      onclick={disconnectDevice}
      disabled={deviceDisconnectBusy}
    >
      <CircleX size={17} />
      {t("wa_devices_disconnect_confirm")}
    </Button>
    <Button
      variant="secondary"
      class="wide"
      onclick={closeDeviceDisconnectDialog}
      disabled={deviceDisconnectBusy}
    >
      {t("wa_cancel")}
    </Button>
  </div>
</Dialog>

<Dialog
  open={setPasswordOpen && !setPasswordPending}
  title={t("wa_password_modal_title")}
  description={t("wa_password_modal_desc")}
  closeLabel={t("wa_close")}
  onclose={closeSetPasswordDialog}
  class="payment-dialog-card webapp-set-password-dialog"
>
  <div class="payment-dialog-body">
    <Input
      bind:value={setPasswordValue}
      type="password"
      placeholder={t("wa_password_new_placeholder")}
      autocomplete="new-password"
    />
    <Input
      bind:value={setPasswordConfirm}
      type="password"
      placeholder={t("wa_password_confirm_placeholder")}
      autocomplete="new-password"
      onkeydown={(event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        requestSetPasswordCode();
      }}
    />
    <Button
      class="wide bottom-action payment-submit-button"
      onclick={requestSetPasswordCode}
      disabled={setPasswordBusy}
    >
      <LockKeyhole size={17} />
      {t("wa_password_send_code_action")}
    </Button>
    {#if setPasswordStatus}
      <StatusMessage error={setPasswordIsError}>{setPasswordStatus}</StatusMessage>
    {/if}
  </div>
</Dialog>

{#if setPasswordOpen && setPasswordPending}
  <div
    class="email-code-fullscreen webapp-set-password-code-dialog"
    role="dialog"
    aria-modal="true"
  >
    <EmailCodeScreen
      bind:code={setPasswordCode}
      email={setPasswordEmail || ""}
      busy={setPasswordBusy}
      resendCooldown={setPasswordResendCooldown}
      status={setPasswordStatus}
      isError={setPasswordIsError}
      {t}
      onBack={closeSetPasswordDialog}
      onConfirm={confirmSetPassword}
      onResend={requestSetPasswordCode}
    />
  </div>
{/if}

{#if linkEmailOpen && linkEmailPending}
  <div class="email-code-fullscreen webapp-link-email-code-dialog" role="dialog" aria-modal="true">
    <EmailCodeScreen
      bind:code={linkEmailCode}
      email={linkEmailPending}
      busy={linkEmailBusy}
      resendCooldown={linkEmailResendCooldown}
      status={linkEmailStatus}
      isError={linkEmailIsError}
      {t}
      onBack={closeLinkEmailDialog}
      onConfirm={verifyLinkEmailCode}
      onResend={requestLinkEmailCode}
    />
  </div>
{/if}

<Dialog
  open={linkEmailOpen && !linkEmailPending}
  title={t("wa_link_email_modal_title")}
  description={t("wa_link_email_modal_desc")}
  closeLabel={t("wa_close")}
  onclose={closeLinkEmailDialog}
  class="payment-dialog-card webapp-link-email-dialog"
>
  <div class="payment-dialog-body">
    <div class="field-error-wrap">
      <Tooltip.Root open={Boolean(linkEmailFieldError)}>
        <Input
          bind:value={linkEmailValue}
          type="email"
          placeholder={t("wa_email_placeholder")}
          autocomplete="email"
          class={linkEmailFieldError ? "input-error" : ""}
          oninput={() => (linkEmailFieldError = "")}
        />
        {#if linkEmailFieldError}
          <Tooltip.Trigger class="field-error-trigger" aria-label={linkEmailFieldError}>
            <span class="field-error-icon" aria-hidden="true"><TriangleAlert size={18} /></span>
          </Tooltip.Trigger>
        {/if}
        {#if linkEmailFieldError}
          <Tooltip.Portal>
            <Tooltip.Content class="field-error-tooltip">{linkEmailFieldError}</Tooltip.Content>
          </Tooltip.Portal>
        {/if}
      </Tooltip.Root>
    </div>
    <Button
      class="wide bottom-action payment-submit-button"
      onclick={requestLinkEmailCode}
      disabled={linkEmailBusy}
    >
      {t("wa_send_code_email")}
    </Button>
    {#if linkEmailStatus}
      <StatusMessage error={linkEmailIsError}>{linkEmailStatus}</StatusMessage>
    {/if}
  </div>
</Dialog>
