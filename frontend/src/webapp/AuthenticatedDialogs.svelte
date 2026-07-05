<script lang="ts">
  import type { AccountStore } from "../lib/webapp/stores/accountStore.js";
  import type { ActionsStore } from "../lib/webapp/stores/actionsStore.js";
  import type { BillingStore } from "../lib/webapp/stores/billingStore.js";

  import { CheckCircle2, Gift, Info, TriangleAlert } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import type { DevicesStore } from "../lib/webapp/stores/devicesStore.js";
  import PaymentDialogs from "./PaymentDialogs.svelte";
  import TariffDialogs from "./TariffDialogs.svelte";
  import type {
    PaymentMethod,
    PlanView,
    SubscriptionView,
    TariffView,
    TermUnitLabel,
    Translate,
    UserProfile,
    VoidAction,
  } from "$lib/webapp/types.js";

  type Props = {
    accountStore: AccountStore;
    actionsStore: ActionsStore;
    activationSuccessDialogOpen?: boolean;
    activationSuccessUseInstallGuides?: boolean;
    backToTariffList: VoidAction;
    billingStore: BillingStore;
    closeActivationSuccessDialog: VoidAction;
    closeDeviceTopupModal: VoidAction;
    continueWithSelectedTariff: VoidAction;
    devicesStore: DevicesStore;
    disconnectDevice: VoidAction;
    emailAuthEnabled?: boolean;
    hasMultipleTariffs?: boolean;
    methods?: PaymentMethod[];
    plans?: PlanView[];
    selectTariff: (tariff: TariffView) => void;
    selectedTariff?: TariffView | null;
    selectedTariffPlans?: PlanView[];
    singleTariffMode?: boolean;
    subscription?: SubscriptionView;
    subscriptionPurchaseDescription?: string;
    t: Translate;
    tariffCatalog?: TariffView[];
    tariffMode?: boolean;
    termUnitLabel: TermUnitLabel;
    trafficMode?: boolean;
    user?: UserProfile;
  };

  let {
    accountStore,
    actionsStore,
    activationSuccessDialogOpen = false,
    activationSuccessUseInstallGuides = false,
    backToTariffList,
    billingStore,
    closeActivationSuccessDialog,
    closeDeviceTopupModal,
    continueWithSelectedTariff,
    devicesStore,
    disconnectDevice,
    emailAuthEnabled = true,
    hasMultipleTariffs = false,
    methods = [],
    plans = [],
    selectTariff,
    selectedTariff = null,
    selectedTariffPlans = [],
    singleTariffMode = false,
    subscription = {},
    subscriptionPurchaseDescription = "",
    t,
    tariffCatalog = [],
    tariffMode = false,
    termUnitLabel,
    trafficMode = false,
    user = {},
  }: Props = $props();

  const promoDeeplinkOpen = $derived(actionsStore.promoDeeplinkOpen);
  const promoDeeplinkStatus = $derived(actionsStore.promoDeeplinkStatus);
  const promoDeeplinkCode = $derived(actionsStore.promoDeeplinkCode);
  const promoDeeplinkMessage = $derived(actionsStore.promoDeeplinkMessage);
  const promoDeeplinkEffectSummary = $derived(actionsStore.promoDeeplinkEffectSummary);
  const promoDeeplinkError = $derived(actionsStore.promoDeeplinkError);
  const promoDeeplinkBusy = $derived(actionsStore.promoDeeplinkBusy);
  const promoDeeplinkTitle = $derived.by(() => {
    if (promoDeeplinkStatus === "standalone") {
      return t("wa_promo_deeplink_title_confirm", {}, "Activate promo code?");
    }
    if (promoDeeplinkStatus === "already_used") {
      return t("wa_promo_deeplink_title_already_used", {}, "Promo code already activated");
    }
    if (promoDeeplinkStatus === "invalid") {
      return t("wa_promo_deeplink_title_invalid", {}, "Promo code unavailable");
    }
    return t("wa_promo_deeplink_title_error", {}, "Could not check the promo code");
  });
  const promoDeeplinkDescription = $derived.by(() => {
    if (promoDeeplinkStatus !== "standalone") return promoDeeplinkMessage;
    return (
      promoDeeplinkMessage ||
      t(
        "wa_promo_deeplink_confirm_hint",
        { code: promoDeeplinkCode },
        `Promo code ${promoDeeplinkCode} will be activated on your account.`
      )
    );
  });
</script>

<PaymentDialogs
  bind:linkEmailCode={accountStore.linkEmailCode}
  bind:linkEmailFieldError={accountStore.linkEmailFieldError}
  bind:linkEmailValue={accountStore.linkEmailValue}
  bind:paymentModalOpen={billingStore.paymentModalOpen}
  bind:paymentStep={billingStore.paymentStep}
  bind:selectedMethod={billingStore.selectedMethod}
  bind:selectedPlan={billingStore.selectedPlan}
  bind:renewHwidDevices={billingStore.renewHwidDevices}
  bind:selectedTariffKey={billingStore.selectedTariffKey}
  bind:setPasswordCode={accountStore.setPasswordCode}
  bind:setPasswordConfirm={accountStore.setPasswordConfirm}
  bind:setPasswordValue={accountStore.setPasswordValue}
  setPasswordEmail={user?.email || ""}
  createPayment={billingStore.createPayment}
  deviceConfirmOpen={devicesStore.deviceConfirmOpen}
  deviceDisconnectBusy={devicesStore.deviceDisconnectBusy}
  deviceToDisconnect={devicesStore.deviceToDisconnect}
  {disconnectDevice}
  linkEmailBusy={accountStore.linkEmailBusy}
  linkEmailIsError={accountStore.linkEmailIsError}
  linkEmailOpen={emailAuthEnabled && accountStore.linkEmailOpen}
  linkEmailPending={accountStore.linkEmailPending}
  linkEmailResendCooldown={accountStore.linkEmailResendCooldown}
  linkEmailStatus={accountStore.linkEmailStatus}
  setPasswordBusy={accountStore.setPasswordBusy}
  setPasswordIsError={accountStore.setPasswordIsError}
  setPasswordOpen={emailAuthEnabled && accountStore.setPasswordOpen}
  setPasswordPending={accountStore.setPasswordPending}
  setPasswordResendCooldown={accountStore.setPasswordResendCooldown}
  setPasswordStatus={accountStore.setPasswordStatus}
  bind:checkoutPromoInput={billingStore.checkoutPromoInput}
  checkoutPromoAppliedCode={billingStore.checkoutPromoAppliedCode}
  checkoutPromoIsError={billingStore.checkoutPromoIsError}
  checkoutPromoPriceText={billingStore.checkoutPromoPriceText}
  checkoutPromoStatus={billingStore.checkoutPromoStatus}
  checkoutPromoDiscountPercent={billingStore.checkoutPromoDiscountPercent}
  checkoutPromoAppliesTo={billingStore.checkoutPromoAppliesTo}
  checkoutPromoMinSubscriptionMonths={billingStore.checkoutPromoMinSubscriptionMonths}
  checkoutPromoMinTrafficGb={billingStore.checkoutPromoMinTrafficGb}
  applyCheckoutPromo={billingStore.applyCheckoutPromo}
  clearCheckoutPromo={billingStore.clearCheckoutPromo}
  {hasMultipleTariffs}
  {methods}
  payBusy={billingStore.payBusy}
  {plans}
  {selectedTariff}
  {selectedTariffPlans}
  {singleTariffMode}
  {subscription}
  {subscriptionPurchaseDescription}
  {tariffCatalog}
  {tariffMode}
  closeDeviceDisconnectDialog={devicesStore.closeDeviceDisconnectDialog}
  closeLinkEmailDialog={accountStore.closeLinkEmailDialog}
  closePaymentModal={billingStore.closePaymentModal}
  closeSetPasswordDialog={accountStore.closeSetPasswordDialog}
  {backToTariffList}
  {continueWithSelectedTariff}
  requestLinkEmailCode={accountStore.requestLinkEmailCode}
  requestSetPasswordCode={accountStore.requestSetPasswordCode}
  {selectTariff}
  {t}
  {termUnitLabel}
  verifyLinkEmailCode={accountStore.verifyLinkEmailCode}
  confirmSetPassword={accountStore.confirmSetPassword}
/>

<TariffDialogs
  bind:changeConfirmOpen={billingStore.changeConfirmOpen}
  bind:changeModalOpen={billingStore.changeModalOpen}
  bind:deviceTopupModalOpen={billingStore.deviceTopupModalOpen}
  bind:selectedChangeAction={billingStore.selectedChangeAction}
  bind:selectedChangeTarget={billingStore.selectedChangeTarget}
  bind:selectedDeviceTopupPlan={billingStore.selectedDeviceTopupPlan}
  bind:selectedMethod={billingStore.selectedMethod}
  bind:selectedTopupPlan={billingStore.selectedTopupPlan}
  bind:topupModalOpen={billingStore.topupModalOpen}
  applyTariffChange={billingStore.applyTariffChange}
  changeOptions={billingStore.changeOptions}
  {closeDeviceTopupModal}
  closeTariffChangeConfirm={billingStore.closeTariffChangeConfirm}
  closeTariffChangeModal={billingStore.closeTariffChangeModal}
  closeTopupModal={billingStore.closeTopupModal}
  bind:checkoutPromoInput={billingStore.checkoutPromoInput}
  checkoutPromoAppliedCode={billingStore.checkoutPromoAppliedCode}
  checkoutPromoIsError={billingStore.checkoutPromoIsError}
  checkoutPromoPriceText={billingStore.checkoutPromoPriceText}
  checkoutPromoStatus={billingStore.checkoutPromoStatus}
  checkoutPromoDiscountPercent={billingStore.checkoutPromoDiscountPercent}
  checkoutPromoAppliesTo={billingStore.checkoutPromoAppliesTo}
  checkoutPromoMinSubscriptionMonths={billingStore.checkoutPromoMinSubscriptionMonths}
  checkoutPromoMinTrafficGb={billingStore.checkoutPromoMinTrafficGb}
  applyCheckoutPromo={billingStore.applyCheckoutPromo}
  clearCheckoutPromo={billingStore.clearCheckoutPromo}
  createDeviceTopupPayment={billingStore.createDeviceTopupPayment}
  createTopupPayment={billingStore.createTopupPayment}
  deviceTopupOptions={billingStore.deviceTopupOptions}
  {methods}
  openTariffChangeConfirm={billingStore.openTariffChangeConfirm}
  payBusy={billingStore.payBusy}
  {singleTariffMode}
  {subscription}
  tariffActionBusy={billingStore.tariffActionBusy}
  topupKind={billingStore.topupKind}
  topupOptions={billingStore.topupOptions}
  {trafficMode}
  {t}
/>

<Dialog
  open={activationSuccessDialogOpen}
  title={t("wa_activation_success_title", {}, "Everything is successfully activated")}
  description={activationSuccessUseInstallGuides
    ? t(
        "wa_activation_success_install_hint",
        {},
        "Press OK and follow the setup instructions for your device."
      )
    : t(
        "wa_activation_success_connect_hint",
        {},
        "Press OK and we will open the Remnawave subscription page for setup."
      )}
  closeLabel={t("wa_close")}
  onclose={closeActivationSuccessDialog}
  class="activation-success-dialog webapp-activation-success-dialog"
>
  {#snippet titleIcon()}
    <CheckCircle2 size={23} />
  {/snippet}
  <div class="activation-success-dialog-body">
    <Button class="wide" onclick={closeActivationSuccessDialog}>
      {t("wa_ok", {}, "OK")}
    </Button>
  </div>
</Dialog>

<Dialog
  open={promoDeeplinkOpen}
  title={promoDeeplinkTitle}
  description={promoDeeplinkDescription}
  closeLabel={t("wa_close")}
  onclose={actionsStore.closePromoDeeplink}
  class="promo-deeplink-dialog"
>
  {#snippet titleIcon()}
    {#if promoDeeplinkStatus === "standalone"}
      <Gift size={23} />
    {:else if promoDeeplinkStatus === "already_used"}
      <Info size={23} />
    {:else}
      <TriangleAlert size={23} />
    {/if}
  {/snippet}
  <div class="promo-deeplink-dialog-body">
    {#if promoDeeplinkStatus === "standalone" && promoDeeplinkEffectSummary}
      <p class="promo-deeplink-effect">
        <strong>{promoDeeplinkCode}</strong> · {promoDeeplinkEffectSummary}
      </p>
    {/if}
    {#if promoDeeplinkError}
      <p class="promo-deeplink-error">{promoDeeplinkError}</p>
    {/if}
    {#if promoDeeplinkStatus === "standalone"}
      <Button
        class="wide"
        disabled={promoDeeplinkBusy}
        onclick={() => void actionsStore.activatePromoDeeplink()}
      >
        {promoDeeplinkBusy
          ? t("wa_loading", {}, "Loading...")
          : t("wa_promo_deeplink_activate", {}, "Activate")}
      </Button>
    {:else}
      <Button class="wide" onclick={actionsStore.closePromoDeeplink}>
        {t("wa_ok", {}, "OK")}
      </Button>
    {/if}
  </div>
</Dialog>

<style>
  .promo-deeplink-dialog-body {
    display: grid;
    gap: 12px;
  }

  .promo-deeplink-effect {
    margin: 0;
    padding: 10px 12px;
    border: 1px solid var(--border, rgba(255, 255, 255, 0.12));
    border-radius: 10px;
    background: color-mix(in srgb, var(--accent, #00fe7a) 8%, transparent);
    font-size: 14px;
  }

  .promo-deeplink-error {
    margin: 0;
    color: var(--danger, #ff6b6b);
    font-size: 13px;
  }
</style>
