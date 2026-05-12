<script>
  import { ArrowLeft, CheckCircle2, CircleX, LockKeyhole, RefreshCw, TriangleAlert } from "$components/ui/icons.js";
  import { Tooltip } from "$components/ui/primitives.js";

  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import Input from "$components/ui/input.svelte";
  import { EmptyCard, PaymentMethodGrid, StatusMessage } from "$components/patterns/webapp/index.js";
  import {
    planKey as planKeyFn,
    planDisplayTitle as planDisplayTitleFn,
    planSubtitle as planSubtitleFn,
    planUnitHint as planUnitHintFn,
    tariffLimitLabel as tariffLimitLabelFn,
    priceLabel as priceLabelFn,
  } from "../lib/webapp/tariffs.js";


  export let createPayment = () => {};
  export let deviceConfirmOpen = false;
  export let deviceDisconnectBusy = false;
  export let deviceToDisconnect = null;
  export let disconnectDevice = () => {};
  export let linkEmailBusy = false;
  export let linkEmailCode = "";
  export let linkEmailFieldError = "";
  export let linkEmailIsError = false;
  export let linkEmailOpen = false;
  export let linkEmailPending = "";
  export let linkEmailResendCooldown = 0;
  export let linkEmailStatus = "";
  export let linkEmailValue = "";
  export let hasMultipleTariffs = false;
  export let methods = [];
  export let payBusy = false;
  export let paymentModalOpen = false;
  export let paymentStep = "tariff";
  export let plans = [];
  export let selectedMethod = "";
  export let selectedPlan = null;
  export let selectedTariff = null;
  export let selectedTariffKey = "";
  export let selectedTariffPlans = [];
  export let singleTariffMode = false;
  export let subscription = {};
  export let tariffCatalog = [];
  export let tariffMode = false;
  export let trafficMode = false;
  
  function priceLabel(plan) { return priceLabelFn(plan, selectedMethod); }
  function planKey(plan) { return planKeyFn(plan); }
  function planDisplayTitle(plan) { return planDisplayTitleFn(plan, { trafficMode, t }); }
  function planSubtitle(plan) { return planSubtitleFn(plan, { t, termUnitLabel }); }
  function planUnitHint(plan) { return planUnitHintFn(plan, { trafficMode, selectedMethod, t }); }
  function tariffLimitLabel(tariff) { return tariffLimitLabelFn(tariff, { t }); }

  function paymentTitle() {
    if (singleTariffMode) {
      return selectedTariff?.billing_model === "traffic" ? t("wa_traffic_packages_title") : t("wa_subscription_title");
    }
    if (tariffMode) return t("wa_tariffs_title");
    return trafficMode ? t("wa_traffic_packages_title") : t("wa_subscription_title");
  }

  function paymentDescription() {
    if (tariffMode) {
      if (singleTariffMode) {
        return selectedTariff?.billing_model === "traffic" ? t("wa_traffic_packages_choose") : t("wa_subscription_choose_period");
      }
      return paymentStep === "checkout" && selectedTariff
        ? t("wa_tariff_choose_period_payment", { tariff: selectedTariff.title })
        : t("wa_tariffs_choose");
    }
    return trafficMode ? t("wa_traffic_packages_choose") : t("wa_subscription_choose_period");
  }


  export let closeDeviceDisconnectDialog = () => {};
  export let closeLinkEmailDialog = () => {};
  export let closePaymentModal = () => {};
  export let backToTariffList = () => {};
  export let continueWithSelectedTariff = () => {};
  export let requestLinkEmailCode = () => {};
  export let selectTariff = () => {};
  export let t = (key) => key;
  export let termUnitLabel = () => "";
  export let verifyLinkEmailCode = () => {};
</script>

<Dialog
  open={paymentModalOpen}
  title={paymentTitle()}
  description={paymentDescription()}
  closeLabel={t("wa_close")}
  onclose={closePaymentModal}
  class="payment-dialog-card"
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
        <Button class="wide bottom-action payment-submit-button" onclick={continueWithSelectedTariff} disabled={!selectedTariffKey}>
          {t("wa_next")}
          <ArrowRight size={17} />
        </Button>
      {:else}
        <EmptyCard>{t("wa_no_tariff_change_options")}</EmptyCard>
      {/if}
    {:else}
      {#if tariffMode}
        {#if !singleTariffMode && !(subscription?.active && subscription?.tariff_key && tariffCatalog.some((t) => t.key === subscription.tariff_key))}
          <button class="back-inline" type="button" onclick={backToTariffList}>
            <ArrowLeft size={16} />
            {t("wa_back_to_tariffs")}
          </button>
        {/if}
        {#if hasMultipleTariffs && selectedTariff}
          <p class="tariff-step-caption">{t("wa_selected_tariff", { tariff: selectedTariff.title })}</p>
        {/if}
      {/if}
      {#if selectedTariffPlans.length}
        <div class="period-grid period-grid-two-columns">
          {#each selectedTariffPlans as plan}
            <button
              class:active={planKey(selectedPlan) === planKey(plan)}
              class="period-card"
              type="button"
              onclick={() => (selectedPlan = plan)}
            >
              <strong>{planSubtitle(plan) || planDisplayTitle(plan)}</strong>
              <span>{priceLabel(plan)}</span>
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
          <PaymentMethodGrid {methods} {selectedMethod} {t} onSelect={(id) => (selectedMethod = id)} />
        {:else}
          <EmptyCard>{t("wa_payment_methods_not_configured")}</EmptyCard>
        {/if}
        <Button class="wide bottom-action payment-submit-button" onclick={createPayment} disabled={!selectedPlan || !methods.length || payBusy}>
          {t("wa_pay")} {selectedPlan ? priceLabel(selectedPlan) : ""}
          <LockKeyhole size={17} />
        </Button>
      {:else}
        <EmptyCard>{t("wa_no_tariff_change_options")}</EmptyCard>
      {/if}
    {/if}
    {#if !tariffMode}
      <div class="period-grid period-grid-two-columns">
        {#each plans as plan}
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
            <span>{priceLabel(plan)}</span>
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
        <PaymentMethodGrid {methods} {selectedMethod} {t} onSelect={(id) => (selectedMethod = id)} />
      {:else}
        <EmptyCard>{t("wa_payment_methods_not_configured")}</EmptyCard>
      {/if}
      <Button class="wide bottom-action payment-submit-button" onclick={createPayment} disabled={!selectedPlan || !methods.length || payBusy}>
        {t("wa_pay")} {selectedPlan ? priceLabel(selectedPlan) : ""}
        <LockKeyhole size={17} />
      </Button>
    {/if}
  </div>
</Dialog>

<Dialog
  open={deviceConfirmOpen}
  title={t("wa_devices_disconnect_title")}
  description={t("wa_devices_disconnect_desc", {
    device: deviceToDisconnect?.display_name || t("wa_device_fallback_name", { index: deviceToDisconnect?.index || "" }),
  })}
  closeLabel={t("wa_close")}
  onclose={closeDeviceDisconnectDialog}
  class="payment-dialog-card"
>
  <div class="payment-dialog-body">
    <Button variant="outline" class="wide device-danger-button" onclick={disconnectDevice} disabled={deviceDisconnectBusy}>
      <CircleX size={17} />
      {t("wa_devices_disconnect_confirm")}
    </Button>
    <Button variant="secondary" class="wide" onclick={closeDeviceDisconnectDialog} disabled={deviceDisconnectBusy}>
      {t("wa_cancel")}
    </Button>
  </div>
</Dialog>

<Dialog
  open={linkEmailOpen}
  title={t("wa_link_email_modal_title")}
  description={linkEmailPending ? t("wa_email_sent_to", { email: linkEmailPending }) : t("wa_link_email_modal_desc")}
  closeLabel={t("wa_close")}
  onclose={closeLinkEmailDialog}
  class={`payment-dialog-card${linkEmailPending ? " link-email-dialog-card" : ""}`}
>
  <div class="payment-dialog-body">
    {#if !linkEmailPending}
      <div class="field-error-wrap">
        <Tooltip.Root open={Boolean(linkEmailFieldError)}>
          <Input
            bind:value={linkEmailValue}
            type="email"
            placeholder={t("wa_email_placeholder")}
            autocomplete="email"
            class={linkEmailFieldError ? "input-error" : ""}
            on:input={() => (linkEmailFieldError = "")}
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
      <Button class="wide bottom-action payment-submit-button" onclick={requestLinkEmailCode} disabled={linkEmailBusy}>
        {t("wa_send_code_email")}
      </Button>
    {:else}
      <div class="link-email-code-layout">
        <div class="otp-wrap link-email-code-center">
          <label class="otp-input-wrap">
            <input
              bind:value={linkEmailCode}
              inputmode="numeric"
              autocomplete="one-time-code"
              maxlength="6"
              aria-label={t("wa_email_code_aria")}
            />
            <span class="otp-slots" aria-hidden="true">
              {#each Array.from({ length: 6 }) as _, index}
                <span class:filled={linkEmailCode[index]}>{linkEmailCode[index] || ""}</span>
              {/each}
            </span>
          </label>
          <Button class="wide bottom-action payment-submit-button" onclick={verifyLinkEmailCode} disabled={linkEmailBusy}>
            {t("wa_confirm")}
          </Button>
        </div>
        <button
          class="link-button link-email-resend"
          type="button"
          onclick={requestLinkEmailCode}
          disabled={linkEmailBusy || linkEmailResendCooldown > 0}
        >
          <RefreshCw size={15} />
          {linkEmailResendCooldown > 0
            ? t("wa_auth_resend_wait", { seconds: linkEmailResendCooldown })
            : t("wa_resend_code")}
        </button>
      </div>
    {/if}
    {#if linkEmailStatus}
      <StatusMessage error={linkEmailIsError}>{linkEmailStatus}</StatusMessage>
    {/if}
  </div>
</Dialog>
