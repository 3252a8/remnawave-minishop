<script>
  import { ArrowRight, CheckCircle2, LockKeyhole } from "$components/ui/icons.js";

  import Button from "$components/ui/button.svelte";
  import {
    planKey as planKeyFn,
    planUnitHint as planUnitHintFn,
    priceLabel as priceLabelFn,
    actionKey as actionKeyFn,
  } from "../lib/webapp/tariffs.js";
  import { premiumTitle as premiumTitleFn } from "../lib/webapp/traffic.js";
  import { formatCompactNumber } from "../lib/webapp/formatters.js";

  import Card from "$components/ui/card.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    DialogOptionsSkeleton,
    EmptyCard,
    PaymentMethodGrid,
  } from "$components/patterns/webapp/index.js";

  export let applyTariffChange = () => {};
  export let changeConfirmOpen = false;
  export let changeModalOpen = false;
  export let changeOptions = null;
  export let closeDeviceTopupModal = () => {};
  export let closeTariffChangeConfirm = () => {};
  export let closeTariffChangeModal = () => {};
  export let closeTopupModal = () => {};
  export let createDeviceTopupPayment = () => {};
  export let createTopupPayment = () => {};
  export let deviceTopupModalOpen = false;
  export let deviceTopupOptions = null;
  export let methods = [];
  export let openTariffChangeConfirm = () => {};
  export let payBusy = false;
  export let selectedChangeAction = null;
  export let selectedChangeTarget = null;
  export let selectedDeviceTopupPlan = null;
  export let selectedMethod = "";
  export let selectedTopupPlan = null;
  export let singleTariffMode = false;
  export let tariffActionBusy = false;
  export let topupModalOpen = false;
  export let topupOptions = null;
  export let topupKind = "regular";
  export let subscription = {};
  export let trafficMode = false;

  function priceLabel(plan) {
    return priceLabelFn(plan, selectedMethod);
  }
  function planKey(plan) {
    return planKeyFn(plan);
  }
  function planUnitHint(plan) {
    return planUnitHintFn(plan, { trafficMode, selectedMethod, t });
  }
  function actionKey(action) {
    return actionKeyFn(action);
  }

  function changeActionTitle(action) {
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
      return `${action?.title || ""} · ${priceLabel(action)}`;
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
        "Докупленный трафик не сгорает: сначала расходуется месячный лимит, затем докупленный остаток."
      ),
    ];
  }

  function deviceTopupModalDescription() {
    if (!deviceTopupOptions) return "";
    return deviceTopupOptions?.tariff_name
      ? t("wa_device_topup_for_tariff", { tariff: deviceTopupOptions.tariff_name })
      : "";
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

  export let t = (key) => key;
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
            {methods}
            {selectedMethod}
            {t}
            onSelect={(id) => (selectedMethod = id)}
          />
        {/if}
        <Button
          class="wide bottom-action payment-submit-button"
          onclick={openTariffChangeConfirm}
          disabled={tariffActionBusy || payBusy}
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
      disabled={tariffActionBusy || payBusy}
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
      <PaymentMethodGrid {methods} {selectedMethod} {t} onSelect={(id) => (selectedMethod = id)} />
      <Button
        class="wide bottom-action payment-submit-button"
        onclick={createTopupPayment}
        disabled={!selectedTopupPlan || !methods.length || payBusy}
      >
        {t("wa_buy_traffic")}
        {selectedTopupPlan ? priceLabel(selectedTopupPlan) : ""}
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
      <div class="option-list">
        {#each deviceTopupOptions.plans as plan}
          <button
            class:active={planKey(selectedDeviceTopupPlan) === planKey(plan)}
            class="option-row plan-row"
            type="button"
            onclick={() => (selectedDeviceTopupPlan = plan)}
          >
            <span class="option-row-main">
              <strong
                >{t("wa_hwid_devices_package", {
                  count: Number(plan.device_count || plan.months || 0),
                })}</strong
              >
              <small>{plan.subtitle || deviceTopupOptions.tariff_name}</small>
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
      <PaymentMethodGrid {methods} {selectedMethod} {t} onSelect={(id) => (selectedMethod = id)} />
      <Button
        class="wide bottom-action payment-submit-button"
        onclick={createDeviceTopupPayment}
        disabled={!selectedDeviceTopupPlan || !methods.length || payBusy}
      >
        {t("wa_pay")}
        {selectedDeviceTopupPlan ? priceLabel(selectedDeviceTopupPlan) : ""}
        <LockKeyhole size={17} />
      </Button>
    {:else}
      <EmptyCard>{t("wa_no_hwid_device_options")}</EmptyCard>
    {/if}
  </div>
</Dialog>
