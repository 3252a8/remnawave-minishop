<script>
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
  import Dialog from "$components/ui/dialog.svelte";
  import EmailCodeScreen from "./auth/EmailCodeScreen.svelte";
  import Input from "$components/ui/input.svelte";
  import {
    EmptyCard,
    PaymentMethodGrid,
    StatusMessage,
  } from "$components/patterns/webapp/index.js";
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
  export let setPasswordBusy = false;
  export let setPasswordCode = "";
  export let setPasswordConfirm = "";
  export let setPasswordEmail = "";
  export let setPasswordIsError = false;
  export let setPasswordOpen = false;
  export let setPasswordPending = false;
  export let setPasswordResendCooldown = 0;
  export let setPasswordStatus = "";
  export let setPasswordValue = "";
  export let singleTariffMode = false;
  export let subscription = {};
  export let subscriptionPurchaseDescription = "";
  export let tariffCatalog = [];
  export let tariffMode = false;
  export let trafficMode = false;

  function priceLabel(plan) {
    return priceLabelFn(plan, selectedMethod);
  }
  function planKey(plan) {
    return planKeyFn(plan);
  }
  function planDisplayTitle(plan) {
    return planDisplayTitleFn(plan, { trafficMode, t });
  }
  function planSubtitle(plan) {
    return planSubtitleFn(plan, { t, termUnitLabel });
  }
  function planUnitHint(plan) {
    return planUnitHintFn(plan, { trafficMode, selectedMethod, t });
  }
  function tariffLimitLabel(tariff) {
    return tariffLimitLabelFn(tariff, { t });
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

  export let closeDeviceDisconnectDialog = () => {};
  export let closeLinkEmailDialog = () => {};
  export let closePaymentModal = () => {};
  export let closeSetPasswordDialog = () => {};
  export let backToTariffList = () => {};
  export let continueWithSelectedTariff = () => {};
  export let requestLinkEmailCode = () => {};
  export let requestSetPasswordCode = () => {};
  export let selectTariff = () => {};
  export let t = (key) => key;
  export let termUnitLabel = () => "";
  export let verifyLinkEmailCode = () => {};
  export let confirmSetPassword = () => {};
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
        {#if subscription?.active && Number(subscription?.extra_hwid_devices || 0) > 0}
          <div class="subscription-purchase-description">
            <p>
              {t("wa_hwid_devices_renewal_notice", {
                count: Number(subscription.extra_hwid_devices || 0),
                date: subscription.extra_hwid_devices_valid_until_text || "",
              })}
            </p>
          </div>
        {/if}
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
          <PaymentMethodGrid
            {methods}
            {selectedMethod}
            {t}
            onSelect={(id) => (selectedMethod = id)}
          />
        {:else}
          <EmptyCard>{t("wa_payment_methods_not_configured")}</EmptyCard>
        {/if}
        <Button
          class="wide bottom-action payment-submit-button"
          onclick={createPayment}
          disabled={!selectedPlan || !methods.length || payBusy}
        >
          {t("wa_pay")}
          {selectedPlan ? priceLabel(selectedPlan) : ""}
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
      {#if subscription?.active && Number(subscription?.extra_hwid_devices || 0) > 0}
        <div class="subscription-purchase-description">
          <p>
            {t("wa_hwid_devices_renewal_notice", {
              count: Number(subscription.extra_hwid_devices || 0),
              date: subscription.extra_hwid_devices_valid_until_text || "",
            })}
          </p>
        </div>
      {/if}
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
        <PaymentMethodGrid
          {methods}
          {selectedMethod}
          {t}
          onSelect={(id) => (selectedMethod = id)}
        />
      {:else}
        <EmptyCard>{t("wa_payment_methods_not_configured")}</EmptyCard>
      {/if}
      <Button
        class="wide bottom-action payment-submit-button"
        onclick={createPayment}
        disabled={!selectedPlan || !methods.length || payBusy}
      >
        {t("wa_pay")}
        {selectedPlan ? priceLabel(selectedPlan) : ""}
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
  class="payment-dialog-card"
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
  class="payment-dialog-card"
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
      on:keydown={(event) => {
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
  <div class="email-code-fullscreen" role="dialog" aria-modal="true">
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
  <div class="email-code-fullscreen" role="dialog" aria-modal="true">
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
  class="payment-dialog-card"
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
