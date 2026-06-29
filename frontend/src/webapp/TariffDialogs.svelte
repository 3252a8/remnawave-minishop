<script lang="ts">
  import { ArrowRight, CheckCircle2, LockKeyhole, X } from "$components/ui/icons.js";

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
  import { formatCompactNumber } from "../lib/webapp/formatters.js";

  import Card from "$components/ui/card.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    DialogOptionsSkeleton,
    EmptyCard,
    PaymentMethodGrid,
    StatusMessage,
  } from "$components/patterns/webapp/index.js";

  type AnyRecord = Record<string, any>;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type VoidAction = () => void;

  let {
    applyTariffChange = () => {},
    changeConfirmOpen = $bindable(false),
    changeModalOpen = $bindable(false),
    changeOptions = null,
    closeDeviceTopupModal = () => {},
    closeTariffChangeConfirm = () => {},
    closeTariffChangeModal = () => {},
    closeTopupModal = () => {},
    checkoutPromoAppliedCode = "",
    checkoutPromoInput = $bindable(""),
    checkoutPromoIsError = false,
    checkoutPromoPriceText = "",
    checkoutPromoStatus = "",
    applyCheckoutPromo = () => {},
    clearCheckoutPromo = () => {},
    createDeviceTopupPayment = () => {},
    createTopupPayment = () => {},
    deviceTopupModalOpen = $bindable(false),
    deviceTopupOptions = null,
    methods = [],
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
    applyTariffChange?: VoidAction;
    changeConfirmOpen?: boolean;
    changeModalOpen?: boolean;
    changeOptions?: AnyRecord | null;
    closeDeviceTopupModal?: VoidAction;
    closeTariffChangeConfirm?: VoidAction;
    closeTariffChangeModal?: VoidAction;
    closeTopupModal?: VoidAction;
    checkoutPromoAppliedCode?: string;
    checkoutPromoInput?: string;
    checkoutPromoIsError?: boolean;
    checkoutPromoPriceText?: string;
    checkoutPromoStatus?: string;
    applyCheckoutPromo?: VoidAction;
    clearCheckoutPromo?: VoidAction;
    createDeviceTopupPayment?: VoidAction;
    createTopupPayment?: VoidAction;
    deviceTopupModalOpen?: boolean;
    deviceTopupOptions?: AnyRecord | null;
    methods?: AnyRecord[];
    openTariffChangeConfirm?: VoidAction;
    payBusy?: boolean;
    selectedChangeAction?: AnyRecord | null;
    selectedChangeTarget?: AnyRecord | null;
    selectedDeviceTopupPlan?: AnyRecord | null;
    selectedMethod?: string;
    selectedTopupPlan?: AnyRecord | null;
    singleTariffMode?: boolean;
    tariffActionBusy?: boolean;
    topupModalOpen?: boolean;
    topupOptions?: AnyRecord | null;
    topupKind?: string;
    subscription?: AnyRecord;
    trafficMode?: boolean;
    t?: Translate;
  } = $props();

  function priceLabel(plan: AnyRecord | null) {
    return priceLabelFn(plan, selectedMethod);
  }
  function checkoutPlanPriceLabel(plan: AnyRecord | null) {
    if (checkoutPromoAppliedCode && checkoutPromoPriceText) return checkoutPromoPriceText;
    return priceLabel(plan);
  }
  function planKey(plan: AnyRecord | null) {
    return planKeyFn(plan);
  }
  function planUnitHint(plan: AnyRecord | null) {
    return planUnitHintFn(plan, { trafficMode, selectedMethod, t });
  }
  function actionKey(action: AnyRecord | null) {
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

  function changeActionTitle(action: AnyRecord | null) {
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

  function deviceTopupPlanTitle(plan: AnyRecord) {
    return t("wa_hwid_devices_package", {
      count: Number(plan?.device_count || plan?.months || 0),
    });
  }

  function deviceTopupPlanHint(plan: AnyRecord) {
    if (plan?.valid_until_text) {
      return t("wa_hwid_devices_active_until", { date: plan.valid_until_text });
    }
    return plan?.subtitle || deviceTopupOptions?.tariff_name || "";
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

  function checkoutPromoBlock(plan: AnyRecord | null) {
    return Boolean(plan || checkoutPromoAppliedCode || checkoutPromoStatus);
  }
</script>

<Dialog
  open={changeModalOpen}
  title={t("wa_change_tariff")}
  description={tariffChangeModalDescription()}
  closeLabel={t("wa_close")}
  onclose={closeTariffChangeModal}
  class="payment-dialog-card"
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
          <PaymentMethodGrid
            methods={changePaymentMethods}
            {selectedMethod}
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
  class="payment-dialog-card"
>
  <div class="payment-dialog-body">
    <Card class="confirm-summary-card">
      {#each tariffChangeSummary() as row}
        <p>{row}</p>
      {/each}
    </Card>
    <Button
      class="wide bottom-action payment-submit-button"
      onclick={applyTariffChange}
      disabled={tariffActionBusy ||
        payBusy ||
        (selectedChangeAction?.kind === "payment" && !changePaymentMethodSelected)}
    >
      {selectedChangeAction?.kind === "payment"
        ? t("wa_confirm_and_pay")
        : t("wa_confirm_and_apply")}
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
  class="payment-dialog-card"
>
  <div class="payment-dialog-body">
    {#if !topupOptions}
      <DialogOptionsSkeleton label={t("wa_tariff_options_loading")} rows={3} showNote />
    {:else if topupOptions?.plans?.length}
      <div class="option-list">
        {#each topupOptions.plans as plan}
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
              <em>{priceLabel(plan)}</em>
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
      <PaymentMethodGrid
        methods={topupPaymentMethods}
        {selectedMethod}
        {t}
        onSelect={(id) => (selectedMethod = id)}
      />
      {#if checkoutPromoBlock(selectedTopupPlan)}
        <div class="checkout-promo-row">
          {#if checkoutPromoAppliedCode}
            <span class="checkout-promo-chip">
              {checkoutPromoAppliedCode}
              <button type="button" onclick={clearCheckoutPromo} aria-label={t("wa_remove")}>
                <X size={14} />
              </button>
            </span>
          {:else}
            <input
              class="input"
              value={checkoutPromoInput}
              oninput={(e) => (checkoutPromoInput = (e.currentTarget as HTMLInputElement).value)}
              placeholder={t("wa_promo_enter")}
            />
            <Button
              variant="secondary"
              onclick={applyCheckoutPromo}
              disabled={!checkoutPromoInput.trim()}
            >
              {t("wa_apply")}
            </Button>
          {/if}
        </div>
        {#if checkoutPromoStatus}
          <StatusMessage error={checkoutPromoIsError}>
            {checkoutPromoStatus}
            {#if checkoutPromoPriceText}
              - {checkoutPromoPriceText}
            {/if}
          </StatusMessage>
        {/if}
      {/if}
      <Button
        class="wide bottom-action payment-submit-button"
        onclick={createTopupPayment}
        disabled={!selectedTopupPlan || !topupPaymentMethodSelected || payBusy}
      >
        {t("wa_buy_traffic")}
        {selectedTopupPlan ? checkoutPlanPriceLabel(selectedTopupPlan) : ""}
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
  class="payment-dialog-card"
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
          <button
            class:active={planKey(selectedDeviceTopupPlan) === planKey(plan)}
            class="option-row plan-row"
            type="button"
            onclick={() => (selectedDeviceTopupPlan = plan)}
          >
            <span class="option-row-main">
              <strong>{deviceTopupPlanTitle(plan)}</strong>
              <small>{deviceTopupPlanHint(plan)}</small>
            </span>
            <span class="option-row-meta">
              <em>{priceLabel(plan)}</em>
              {#if planKey(selectedDeviceTopupPlan) === planKey(plan)}
                <CheckCircle2 size={18} />
              {/if}
            </span>
          </button>
        {/each}
      </div>
      <PaymentMethodGrid
        methods={devicePaymentMethods}
        {selectedMethod}
        {t}
        onSelect={(id) => (selectedMethod = id)}
      />
      {#if checkoutPromoBlock(selectedDeviceTopupPlan)}
        <div class="checkout-promo-row">
          {#if checkoutPromoAppliedCode}
            <span class="checkout-promo-chip">
              {checkoutPromoAppliedCode}
              <button type="button" onclick={clearCheckoutPromo} aria-label={t("wa_remove")}>
                <X size={14} />
              </button>
            </span>
          {:else}
            <input
              class="input"
              value={checkoutPromoInput}
              oninput={(e) => (checkoutPromoInput = (e.currentTarget as HTMLInputElement).value)}
              placeholder={t("wa_promo_enter")}
            />
            <Button
              variant="secondary"
              onclick={applyCheckoutPromo}
              disabled={!checkoutPromoInput.trim()}
            >
              {t("wa_apply")}
            </Button>
          {/if}
        </div>
        {#if checkoutPromoStatus}
          <StatusMessage error={checkoutPromoIsError}>
            {checkoutPromoStatus}
            {#if checkoutPromoPriceText}
              - {checkoutPromoPriceText}
            {/if}
          </StatusMessage>
        {/if}
      {/if}
      <Button
        class="wide bottom-action payment-submit-button"
        onclick={createDeviceTopupPayment}
        disabled={!selectedDeviceTopupPlan || !devicePaymentMethodSelected || payBusy}
      >
        {t("wa_pay")}
        {selectedDeviceTopupPlan ? checkoutPlanPriceLabel(selectedDeviceTopupPlan) : ""}
        <LockKeyhole size={17} />
      </Button>
    {:else}
      <EmptyCard>{t("wa_no_hwid_device_options")}</EmptyCard>
    {/if}
  </div>
</Dialog>
