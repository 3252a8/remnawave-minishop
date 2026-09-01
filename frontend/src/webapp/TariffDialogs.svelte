<script lang="ts">
  import { ArrowRight, CheckCircle2, LockKeyhole } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import {
    planKey as planKeyFn,
    planUnitHint as planUnitHintFn,
    priceLabel as priceLabelFn,
    actionKey as actionKeyFn,
    firstAvailableMethod,
    methodSelectable,
    methodsForPlan,
  } from "../lib/webapp/tariffs.js";
  import { premiumTitle as premiumTitleFn } from "../lib/webapp/traffic.js";
  import { formatCompactNumber, formatMoney } from "../lib/webapp/formatters.js";
  import { loadPartnerBalanceSnapshot } from "$lib/webapp/partnerBalanceLookup.js";

  import Card from "$components/ui/card.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    DialogOptionsSkeleton,
    EmptyCard,
    PaymentMethodPicker,
  } from "$components/patterns/webapp/index.js";
  import CheckoutPromoRow from "./CheckoutPromoRow.svelte";
  import PartnerBalanceDiscount from "./payment-dialogs/PartnerBalanceDiscount.svelte";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import type {
    BillingOptionsResponse,
    DeviceTopupOptions,
    PaymentMethodView,
    PlanView,
    SubscriptionView,
    TariffChangeAction,
    TariffChangeOptions,
    TariffChangeTarget,
    StringAction,
    Translate,
    VoidAction,
  } from "$lib/webapp/types.js";

  type CheckoutPlan = PlanView | TariffChangeAction;
  type BalancePaymentAction = (options?: { balanceSource?: "user" | "partner" | null }) => unknown;

  let {
    api,
    applyTariffChange = () => {},
    changeConfirmOpen = $bindable(false),
    changeModalOpen = $bindable(false),
    changeOptions = null,
    closeDeviceTopupModal = () => {},
    closeTariffChangeConfirm = () => {},
    closeTariffChangeModal = () => {},
    closeTopupModal = () => {},
    checkoutPromoAppliedCode = "",
    checkoutPromoInput = "",
    checkoutPromoIsError = false,
    checkoutPromoPriceText = "",
    checkoutPromoEffectiveAmount = 0,
    checkoutPromoStatus = "",
    checkoutPromoDiscountPercent = 0,
    checkoutPromoAppliesTo = "all",
    checkoutPromoMinSubscriptionMonths = null,
    checkoutPromoMinTrafficGb = null,
    applyCheckoutPromo = () => {},
    clearCheckoutPromo = () => {},
    setCheckoutPromoInput = () => {},
    createDeviceTopupPayment = () => {},
    createTopupPayment = () => {},
    deviceTopupModalOpen = $bindable(false),
    deviceTopupOptions = null,
    methods = [],
    paymentMethodsDisplayMode = "dropdown",
    openTariffChangeConfirm = () => {},
    payBusy = false,
    selectedChangeAction = $bindable(null),
    selectedChangeTarget = $bindable(null),
    selectedDeviceTopupPlan = $bindable(null),
    selectedMethod = $bindable(""),
    selectedTopupPlan = $bindable(null),
    singleTariffMode = false,
    tariffActionBusy = false,
    topupModalOpen = $bindable(false),
    topupOptions = null,
    topupKind = "regular",
    subscription = {},
    trafficMode = false,
    t = (key) => key,
  }: {
    api: ApiClient["api"];
    applyTariffChange?: BalancePaymentAction;
    changeConfirmOpen?: boolean;
    changeModalOpen?: boolean;
    changeOptions?: TariffChangeOptions | null;
    closeDeviceTopupModal?: VoidAction;
    closeTariffChangeConfirm?: VoidAction;
    closeTariffChangeModal?: VoidAction;
    closeTopupModal?: VoidAction;
    checkoutPromoAppliedCode?: string;
    checkoutPromoInput?: string;
    checkoutPromoIsError?: boolean;
    checkoutPromoPriceText?: string;
    checkoutPromoEffectiveAmount?: number;
    checkoutPromoStatus?: string;
    checkoutPromoDiscountPercent?: number;
    checkoutPromoAppliesTo?: string;
    checkoutPromoMinSubscriptionMonths?: number | null;
    checkoutPromoMinTrafficGb?: number | null;
    applyCheckoutPromo?: VoidAction;
    clearCheckoutPromo?: VoidAction;
    setCheckoutPromoInput?: StringAction;
    createDeviceTopupPayment?: BalancePaymentAction;
    createTopupPayment?: BalancePaymentAction;
    deviceTopupModalOpen?: boolean;
    deviceTopupOptions?: DeviceTopupOptions | null;
    methods?: PaymentMethodView[];
    paymentMethodsDisplayMode?: "dropdown" | "buttons" | string;
    openTariffChangeConfirm?: VoidAction;
    payBusy?: boolean;
    selectedChangeAction?: TariffChangeAction | null;
    selectedChangeTarget?: TariffChangeTarget | null;
    selectedDeviceTopupPlan?: PlanView | null;
    selectedMethod?: string;
    selectedTopupPlan?: PlanView | null;
    singleTariffMode?: boolean;
    tariffActionBusy?: boolean;
    topupModalOpen?: boolean;
    topupOptions?: BillingOptionsResponse | null;
    topupKind?: string;
    subscription?: SubscriptionView;
    trafficMode?: boolean;
    t?: Translate;
  } = $props();

  function priceLabel(plan: CheckoutPlan | null) {
    return priceLabelFn(plan, selectedMethod);
  }
  function checkoutPlanPriceLabel(plan: CheckoutPlan | null) {
    const promoPrice = checkoutPromoPriceParts(plan);
    if (promoPrice) return promoPrice.discounted;
    if (checkoutPromoAppliedCode && checkoutPromoPriceText) return checkoutPromoPriceText;
    return priceLabel(plan);
  }
  function checkoutPromoDiscount() {
    const value = Number(checkoutPromoDiscountPercent || 0);
    if (!checkoutPromoAppliedCode || !Number.isFinite(value) || value <= 0) return 0;
    return Math.min(100, value);
  }
  function planSaleModeBase(plan: CheckoutPlan | null) {
    const fallback =
      Number(plan?.device_count || 0) > 0
        ? "hwid_devices"
        : Number(plan?.traffic_gb || 0) > 0
          ? "traffic_topup"
          : "subscription";
    const saleMode = String(plan?.sale_mode || fallback).toLowerCase();
    if (["traffic", "traffic_package"].includes(saleMode)) return "traffic";
    if (["topup", "premium_topup"].includes(saleMode)) return "traffic_topup";
    if (["hwid_device", "hwid_devices", "hwid_devices_renewal"].includes(saleMode)) return "hwid";
    return "subscription";
  }
  function checkoutPromoScopeMatches(plan: CheckoutPlan | null) {
    const scope = String(checkoutPromoAppliesTo || "all").toLowerCase();
    const base = planSaleModeBase(plan);
    return scope === "all" || scope === base;
  }
  function checkoutPromoThresholdMatches(plan: CheckoutPlan | null) {
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
  function checkoutPromoAffectsPlan(plan: CheckoutPlan | null) {
    return (
      checkoutPromoDiscount() > 0 &&
      checkoutPromoScopeMatches(plan) &&
      checkoutPromoThresholdMatches(plan)
    );
  }
  function discountedCheckoutPlan(plan: CheckoutPlan | null) {
    const discount = checkoutPromoDiscount();
    if (!plan || discount <= 0) return plan;
    const multiplier = Math.max(0, 1 - discount / 100);
    const next: CheckoutPlan = { ...plan };
    if (Number(plan.price || 0) > 0) {
      next.price = Math.round(Number(plan.price || 0) * multiplier * 100) / 100;
    }
    if (Number(plan.stars_price || 0) > 0) {
      next.stars_price = Math.max(1, Math.round(Number(plan.stars_price || 0) * multiplier));
    }
    return next;
  }
  function checkoutPromoPriceParts(plan: CheckoutPlan | null) {
    if (!checkoutPromoAffectsPlan(plan)) return null;
    return {
      base: priceLabel(plan),
      discounted: priceLabel(discountedCheckoutPlan(plan)),
    };
  }
  function planKey(plan: CheckoutPlan | null) {
    return planKeyFn(plan);
  }
  function planUnitHint(plan: CheckoutPlan | null) {
    return planUnitHintFn(plan, { trafficMode, selectedMethod, t });
  }
  function actionKey(action: TariffChangeAction | null) {
    return actionKeyFn(action);
  }

  const changePaymentMethods = $derived(methodsForPlan(methods, selectedChangeAction));
  const topupPaymentMethods = $derived(methodsForPlan(methods, selectedTopupPlan));
  const devicePaymentMethods = $derived(methodsForPlan(methods, selectedDeviceTopupPlan));
  const changePaymentMethodSelected = $derived(
    methodSelectable(changePaymentMethods, selectedMethod)
  );
  const topupPaymentMethodSelected = $derived(
    methodSelectable(topupPaymentMethods, selectedMethod)
  );
  const devicePaymentMethodSelected = $derived(
    methodSelectable(devicePaymentMethods, selectedMethod)
  );

  $effect(() => {
    if (!changeModalOpen || selectedChangeAction?.kind !== "payment") return;
    const firstMethod = firstAvailableMethod(changePaymentMethods);
    if (firstMethod && !methodSelectable(changePaymentMethods, selectedMethod)) {
      selectedMethod = firstMethod;
    }
  });
  $effect(() => {
    if (!topupModalOpen || !selectedTopupPlan) return;
    const firstMethod = firstAvailableMethod(topupPaymentMethods);
    if (firstMethod && !methodSelectable(topupPaymentMethods, selectedMethod)) {
      selectedMethod = firstMethod;
    }
  });
  $effect(() => {
    if (!deviceTopupModalOpen || !selectedDeviceTopupPlan) return;
    const firstMethod = firstAvailableMethod(devicePaymentMethods);
    if (firstMethod && !methodSelectable(devicePaymentMethods, selectedMethod)) {
      selectedMethod = firstMethod;
    }
  });
  $effect(() => {
    const currencies = new Set(
      [selectedChangeAction, selectedTopupPlan, selectedDeviceTopupPlan]
        .map((plan) => String(plan?.currency || "").toUpperCase())
        .filter(Boolean)
    );
    for (const currency of currencies) {
      void loadPartnerBalanceSnapshot(api, currency).catch(() => {});
    }
  });

  function changeActionTitle(action: TariffChangeAction | null) {
    const mode = String(action?.mode || "");
    if (mode === "recalc_days") {
      return t("wa_tariff_change_recalc_days", { days: Number(action?.days_after || 0) });
    }
    if (mode === "convert_days_to_gb") {
      return t("wa_tariff_change_convert_gb", {
        gb: formatCompactNumber(action?.converted_gb || 0),
      });
    }
    if (mode === "paid_diff") {
      return t("wa_tariff_change_pay_diff", { price: priceLabel(action) });
    }
    if (mode === "buy_package") {
      return t("wa_tariff_change_buy_package", {
        gb: formatCompactNumber(action?.traffic_gb || 0),
        price: priceLabel(action),
      });
    }
    if (mode === "buy_period") {
      return `${action?.title || ""} - ${priceLabel(action)}`;
    }
    return action?.title || mode;
  }

  function tariffChangeSummary() {
    if (!selectedChangeTarget || !selectedChangeAction) return [];
    const rows = [
      t("wa_tariff_change_confirm_target", { tariff: selectedChangeTarget.title }),
      t("wa_tariff_change_confirm_action", { action: changeActionTitle(selectedChangeAction) }),
    ];
    const mode = String(selectedChangeAction.mode || "");
    if (mode === "recalc_days") {
      rows.push(
        t("wa_tariff_change_confirm_recalc", { days: Number(selectedChangeAction.days_after || 0) })
      );
    } else if (mode === "convert_days_to_gb") {
      rows.push(
        t("wa_tariff_change_confirm_convert", {
          gb: formatCompactNumber(selectedChangeAction.converted_gb || 0),
        })
      );
    } else if (selectedChangeAction.kind === "payment") {
      rows.push(t("wa_tariff_change_confirm_payment", { price: priceLabel(selectedChangeAction) }));
    }
    return rows;
  }

  function topupCarryoverNotes() {
    const plans = topupOptions?.plans || [];
    if (!plans.length) return [];
    return [
      t(
        "wa_topup_carryover",
        {},
        "Purchased traffic does not expire: monthly allowance is spent first, then the purchased balance."
      ),
    ];
  }

  function deviceTopupModalDescription() {
    if (!deviceTopupOptions) return "";
    return deviceTopupOptions?.tariff_name
      ? t("wa_device_topup_for_tariff", { tariff: deviceTopupOptions.tariff_name })
      : "";
  }

  function deviceTopupPlanTitle(plan: PlanView) {
    return t("wa_hwid_devices_package", {
      count: Number(plan?.device_count || plan?.months || 0),
    });
  }

  function deviceTopupPlanBonus(plan: PlanView) {
    const bonusGb = Number(plan?.traffic_bonus_gb || 0);
    if (!(bonusGb > 0)) return "";
    return t("wa_hwid_devices_traffic_bonus", { gb: formatCompactNumber(bonusGb) });
  }

  function deviceTopupPlanHint(plan: PlanView) {
    return plan?.valid_until_text
      ? t("wa_hwid_devices_active_until", { date: plan.valid_until_text })
      : plan?.subtitle || deviceTopupOptions?.tariff_name || "";
  }

  function tariffChangeModalDescription() {
    if (!changeOptions) return "";
    return changeOptions?.current
      ? t("wa_current_tariff", { tariff: changeOptions.current.title })
      : "";
  }

  function isPremiumTopupContext() {
    if (selectedTopupPlan?.sale_mode === "premium_topup") return true;
    if (topupOptions?.topup_kind) return topupOptions.topup_kind === "premium";
    return topupKind === "premium";
  }

  function topupModalDescription() {
    if (!topupOptions) return "";
    if (isPremiumTopupContext())
      return topupOptions?.tariff_name
        ? t("wa_topup_for_tariff", { tariff: topupOptions.tariff_name })
        : "";
    if (singleTariffMode) return "";
    return topupOptions?.tariff_name
      ? t("wa_topup_for_tariff", { tariff: topupOptions.tariff_name })
      : "";
  }

  function topupModalTitle() {
    if (isPremiumTopupContext())
      return premiumTitleFn({ ...subscription, ...(topupOptions || {}) }, t);
    return t("wa_topup_traffic");
  }

  function checkoutPromoBlock(plan: unknown | null) {
    return Boolean(plan || checkoutPromoAppliedCode || checkoutPromoStatus);
  }

  let changeBalanceSource = $state<"user" | "partner" | null>(null);
  let changePartnerBalanceDiscount = $state(0);
  let topupBalanceSource = $state<"user" | "partner" | null>(null);
  let topupPartnerBalanceDiscount = $state(0);
  let deviceBalanceSource = $state<"user" | "partner" | null>(null);
  let devicePartnerBalanceDiscount = $state(0);

  function checkoutAmount(plan: CheckoutPlan | null) {
    const quotedPromoAmount = Number(checkoutPromoEffectiveAmount || 0);
    if (checkoutPromoAppliedCode && quotedPromoAmount > 0) return quotedPromoAmount;
    return Number(plan?.price || 0);
  }

  function selectedMethodMinimum() {
    const method = methods.find(
      (item) => String(item.id || "").toLowerCase() === String(selectedMethod || "").toLowerCase()
    );
    return Math.max(
      0,
      Number(method?.minimum_amount || method?.min_amount || method?.shop_min_amount || 0)
    );
  }

  function providerManagesPrice(plan: CheckoutPlan | null) {
    const normalizedMethod = String(selectedMethod || "").toLowerCase();
    if (
      plan?.externally_managed_price_method_ids?.some(
        (methodId) => String(methodId).toLowerCase() === normalizedMethod
      )
    ) {
      return true;
    }
    return Boolean(
      methods.find((method) => String(method.id || "").toLowerCase() === normalizedMethod)
        ?.price_managed_externally
    );
  }

  function partnerBalanceEligible(plan: CheckoutPlan | null) {
    return Boolean(
      plan &&
      selectedMethod &&
      checkoutAmount(plan) > 0 &&
      !String(selectedMethod).toLowerCase().includes("stars") &&
      !providerManagesPrice(plan)
    );
  }

  function partnerCheckoutPriceParts(
    plan: CheckoutPlan | null,
    selected: boolean,
    discount: number
  ) {
    if (!selected || discount <= 0 || !plan) return null;
    return {
      base: checkoutPlanPriceLabel(plan),
      discounted: formatMoney(
        Math.max(0, checkoutAmount(plan) - discount),
        String(plan.currency || "")
      ),
    };
  }
</script>

<Dialog
  open={changeModalOpen}
  title={t("wa_change_tariff")}
  description={tariffChangeModalDescription()}
  closeLabel={t("wa_close")}
  onclose={closeTariffChangeModal}
  class="payment-dialog-card webapp-tariff-change-dialog"
>
  <div class="payment-dialog-body">
    {#if !changeOptions}
      <DialogOptionsSkeleton
        label={t("wa_tariff_options_loading")}
        actions={2}
        rows={2}
        methods={0}
        showMeta={false}
      />
    {:else if changeOptions?.targets?.length}
      <p class="section-kicker">{t("wa_tariff_change_targets_title")}</p>
      <div class="tariff-action-list">
        {#each changeOptions.targets as target}
          <button
            class:active={selectedChangeTarget?.tariff_key === target.tariff_key}
            class="tariff-action-card"
            type="button"
            onclick={() => {
              selectedChangeTarget = target;
              selectedChangeAction = target.actions?.[0] || null;
            }}
          >
            <span>
              <strong>{target.title}</strong>
              <small>{target.description}</small>
            </span>
            <em
              >{target.billing_model === "traffic"
                ? t("wa_tariff_model_traffic")
                : t("wa_tariff_model_period")}</em
            >
          </button>
        {/each}
      </div>
      {#if selectedChangeTarget?.actions?.length}
        <div class="payment-divider" aria-hidden="true"></div>
        <p class="section-kicker">{t("wa_tariff_change_strategy_title")}</p>
        <div class="option-list">
          {#each selectedChangeTarget.actions as action}
            <button
              class:active={actionKey(selectedChangeAction) === actionKey(action)}
              class="option-row change-action-row"
              type="button"
              onclick={() => (selectedChangeAction = action)}
            >
              <span class="option-row-main">
                <strong>{changeActionTitle(action)}</strong>
                {#if action.mode === "recalc_days"}
                  <small
                    >{t("wa_tariff_change_recalc_hint", {
                      days: Number(action.remaining_days || 0),
                    })}</small
                  >
                {:else if action.mode === "convert_days_to_gb"}
                  <small
                    >{t("wa_tariff_change_convert_hint", {
                      days: Number(action.remaining_days || 0),
                    })}</small
                  >
                {:else if action.kind === "payment"}
                  <small>{t("wa_tariff_change_payment_hint")}</small>
                {/if}
              </span>
              {#if actionKey(selectedChangeAction) === actionKey(action)}
                <CheckCircle2 size={18} />
              {/if}
            </button>
          {/each}
        </div>
        {#if selectedChangeAction?.kind === "payment"}
          <PaymentMethodPicker
            methods={changePaymentMethods}
            {selectedMethod}
            mode={paymentMethodsDisplayMode}
            {t}
            onSelect={(id) => (selectedMethod = id)}
          />
        {/if}
        <Button
          class="wide bottom-action payment-submit-button"
          onclick={openTariffChangeConfirm}
          disabled={tariffActionBusy ||
            payBusy ||
            (selectedChangeAction?.kind === "payment" && !changePaymentMethodSelected)}
        >
          {selectedChangeAction?.kind === "payment" ? t("wa_pay") : t("wa_apply")}
          <ArrowRight size={17} />
        </Button>
      {:else}
        <EmptyCard>{t("wa_no_tariff_change_options")}</EmptyCard>
      {/if}
    {:else}
      <EmptyCard>{t("wa_no_tariff_change_options")}</EmptyCard>
    {/if}
  </div>
</Dialog>

<Dialog
  open={changeConfirmOpen}
  title={t("wa_tariff_change_confirm_title")}
  description={t("wa_tariff_change_confirm_desc")}
  closeLabel={t("wa_close")}
  onclose={closeTariffChangeConfirm}
  class="payment-dialog-card webapp-tariff-change-confirm-dialog"
>
  <div class="payment-dialog-body">
    <Card class="confirm-summary-card">
      {#each tariffChangeSummary() as row}
        <p>{row}</p>
      {/each}
    </Card>
    {#if selectedChangeAction?.kind === "payment"}
      <PartnerBalanceDiscount
        {api}
        open={changeConfirmOpen}
        amount={checkoutAmount(selectedChangeAction)}
        currency={String(selectedChangeAction.currency || "")}
        eligible={partnerBalanceEligible(selectedChangeAction)}
        minimumExternalAmount={selectedMethodMinimum()}
        bind:source={changeBalanceSource}
        bind:discount={changePartnerBalanceDiscount}
        {t}
      />
    {/if}
    <Button
      class="wide bottom-action payment-submit-button"
      onclick={() => applyTariffChange({ balanceSource: changeBalanceSource })}
      disabled={tariffActionBusy ||
        payBusy ||
        (selectedChangeAction?.kind === "payment" && !changePaymentMethodSelected)}
    >
      {selectedChangeAction?.kind === "payment"
        ? t("wa_confirm_and_pay")
        : t("wa_confirm_and_apply")}
      {#if partnerCheckoutPriceParts(selectedChangeAction, Boolean(changeBalanceSource), changePartnerBalanceDiscount)}
        {@const changeBalancePrice = partnerCheckoutPriceParts(
          selectedChangeAction,
          Boolean(changeBalanceSource),
          changePartnerBalanceDiscount
        )}
        <span class="promo-price-pair">
          <s>{changeBalancePrice?.base}</s>
          <b>{changeBalancePrice?.discounted}</b>
        </span>
      {/if}
      <ArrowRight size={17} />
    </Button>
    <Button
      variant="secondary"
      class="wide"
      onclick={closeTariffChangeConfirm}
      disabled={tariffActionBusy || payBusy}
    >
      {t("wa_cancel")}
    </Button>
  </div>
</Dialog>

<Dialog
  open={topupModalOpen}
  title={topupModalTitle()}
  description={topupModalDescription()}
  closeLabel={t("wa_close")}
  onclose={closeTopupModal}
  class="payment-dialog-card webapp-topup-dialog"
>
  <div class="payment-dialog-body">
    {#if !topupOptions}
      <DialogOptionsSkeleton label={t("wa_tariff_options_loading")} rows={3} showNote />
    {:else if topupOptions?.plans?.length}
      <div class="option-list">
        {#each topupOptions.plans as plan}
          {@const promoPrice = checkoutPromoPriceParts(plan)}
          <button
            class:active={planKey(selectedTopupPlan) === planKey(plan)}
            class="option-row plan-row"
            type="button"
            onclick={() => (selectedTopupPlan = plan)}
          >
            <span class="option-row-main">
              <strong>{plan.title}</strong>
              {#if !singleTariffMode || plan.sale_mode === "premium_topup"}
                <small>{plan.subtitle || topupOptions.tariff_name}</small>
              {/if}
            </span>
            <span class="option-row-meta">
              {#if promoPrice}
                <span class="promo-price-pair">
                  <s>{promoPrice.base}</s>
                  <b>{promoPrice.discounted}</b>
                </span>
              {:else}
                <em>{priceLabel(plan)}</em>
              {/if}
              {#if planUnitHint(plan)}
                <small>{planUnitHint(plan)}</small>
              {/if}
            </span>
          </button>
        {/each}
      </div>
      {@const carryoverNotes = topupCarryoverNotes()}
      {#if carryoverNotes.length}
        <div class="topup-carryover-note">
          {#each carryoverNotes as note}
            <p>{note}</p>
          {/each}
        </div>
      {/if}
      <PaymentMethodPicker
        methods={topupPaymentMethods}
        {selectedMethod}
        mode={paymentMethodsDisplayMode}
        {t}
        onSelect={(id) => (selectedMethod = id)}
      />
      {#if checkoutPromoBlock(selectedTopupPlan)}
        <CheckoutPromoRow
          inputId="webapp-topup-checkout-code"
          inputName="webapp-topup-checkout-code"
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
        open={topupModalOpen}
        amount={checkoutAmount(selectedTopupPlan)}
        currency={String(selectedTopupPlan?.currency || "")}
        eligible={partnerBalanceEligible(selectedTopupPlan)}
        minimumExternalAmount={selectedMethodMinimum()}
        bind:source={topupBalanceSource}
        bind:discount={topupPartnerBalanceDiscount}
        {t}
      />
      <Button
        class="wide bottom-action payment-submit-button"
        onclick={() => createTopupPayment({ balanceSource: topupBalanceSource })}
        disabled={!selectedTopupPlan || !topupPaymentMethodSelected || payBusy}
      >
        {t("wa_buy_traffic")}
        {#if partnerCheckoutPriceParts(selectedTopupPlan, Boolean(topupBalanceSource), topupPartnerBalanceDiscount)}
          {@const topupBalancePrice = partnerCheckoutPriceParts(
            selectedTopupPlan,
            Boolean(topupBalanceSource),
            topupPartnerBalanceDiscount
          )}
          <span class="promo-price-pair">
            <s>{topupBalancePrice?.base}</s>
            <b>{topupBalancePrice?.discounted}</b>
          </span>
        {:else}
          {selectedTopupPlan ? checkoutPlanPriceLabel(selectedTopupPlan) : ""}
        {/if}
        <LockKeyhole size={17} />
      </Button>
    {:else}
      <EmptyCard>{t("wa_no_topup_options")}</EmptyCard>
    {/if}
  </div>
</Dialog>

<Dialog
  open={deviceTopupModalOpen}
  title={t("wa_buy_hwid_devices")}
  description={deviceTopupModalDescription()}
  closeLabel={t("wa_close")}
  onclose={closeDeviceTopupModal}
  class="payment-dialog-card webapp-device-topup-dialog"
>
  <div class="payment-dialog-body">
    {#if !deviceTopupOptions}
      <DialogOptionsSkeleton label={t("wa_tariff_options_loading")} rows={3} />
    {:else if deviceTopupOptions?.plans?.length}
      {#if Number(deviceTopupOptions?.extra_hwid_devices || 0) > 0 && deviceTopupOptions?.extra_hwid_devices_valid_until_text}
        <div class="topup-carryover-note">
          <p>
            {t("wa_hwid_devices_valid_until", {
              count: Number(deviceTopupOptions.extra_hwid_devices || 0),
              date: deviceTopupOptions.extra_hwid_devices_valid_until_text,
            })}
          </p>
        </div>
      {/if}
      <div class="option-list">
        {#each deviceTopupOptions.plans as plan}
          {@const promoPrice = checkoutPromoPriceParts(plan)}
          <button
            class:active={planKey(selectedDeviceTopupPlan) === planKey(plan)}
            class="option-row plan-row"
            type="button"
            onclick={() => (selectedDeviceTopupPlan = plan)}
          >
            <span class="option-row-main">
              <strong>{deviceTopupPlanTitle(plan)}</strong>
              <small>{deviceTopupPlanHint(plan)}</small>
              {#if deviceTopupPlanBonus(plan)}
                <small class="hwid-traffic-bonus">{deviceTopupPlanBonus(plan)}</small>
              {/if}
            </span>
            <span class="option-row-meta">
              {#if promoPrice}
                <span class="promo-price-pair">
                  <s>{promoPrice.base}</s>
                  <b>{promoPrice.discounted}</b>
                </span>
              {:else}
                <em>{priceLabel(plan)}</em>
              {/if}
              {#if planKey(selectedDeviceTopupPlan) === planKey(plan)}
                <CheckCircle2 size={18} />
              {/if}
            </span>
          </button>
        {/each}
      </div>
      <PaymentMethodPicker
        methods={devicePaymentMethods}
        {selectedMethod}
        mode={paymentMethodsDisplayMode}
        {t}
        onSelect={(id) => (selectedMethod = id)}
      />
      {#if checkoutPromoBlock(selectedDeviceTopupPlan)}
        <CheckoutPromoRow
          inputId="webapp-device-topup-checkout-code"
          inputName="webapp-device-topup-checkout-code"
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
        open={deviceTopupModalOpen}
        amount={checkoutAmount(selectedDeviceTopupPlan)}
        currency={String(selectedDeviceTopupPlan?.currency || "")}
        eligible={partnerBalanceEligible(selectedDeviceTopupPlan)}
        minimumExternalAmount={selectedMethodMinimum()}
        bind:source={deviceBalanceSource}
        bind:discount={devicePartnerBalanceDiscount}
        {t}
      />
      <Button
        class="wide bottom-action payment-submit-button"
        onclick={() => createDeviceTopupPayment({ balanceSource: deviceBalanceSource })}
        disabled={!selectedDeviceTopupPlan || !devicePaymentMethodSelected || payBusy}
      >
        {t("wa_pay")}
        {#if partnerCheckoutPriceParts(selectedDeviceTopupPlan, Boolean(deviceBalanceSource), devicePartnerBalanceDiscount)}
          {@const deviceBalancePrice = partnerCheckoutPriceParts(
            selectedDeviceTopupPlan,
            Boolean(deviceBalanceSource),
            devicePartnerBalanceDiscount
          )}
          <span class="promo-price-pair">
            <s>{deviceBalancePrice?.base}</s>
            <b>{deviceBalancePrice?.discounted}</b>
          </span>
        {:else}
          {selectedDeviceTopupPlan ? checkoutPlanPriceLabel(selectedDeviceTopupPlan) : ""}
        {/if}
        <LockKeyhole size={17} />
      </Button>
    {:else}
      <EmptyCard>{t("wa_no_hwid_device_options")}</EmptyCard>
    {/if}
  </div>
</Dialog>
