<script lang="ts">
  import type { AccountStore } from "../lib/webapp/stores/accountStore.js";
  import type { BillingStore } from "../lib/webapp/stores/billingStore.js";

  import { CheckCircle2 } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import type { DevicesStore } from "../lib/webapp/stores/devicesStore.js";
  import PaymentDialogs from "./PaymentDialogs.svelte";
  import TariffDialogs from "./TariffDialogs.svelte";

  type AnyRecord = Record<string, any>;
  type Action = (...args: any[]) => any;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  type Props = {
    accountStore: AccountStore;
    activationSuccessDialogOpen?: boolean;
    activationSuccessUseInstallGuides?: boolean;
    backToTariffList: Action;
    billingStore: BillingStore;
    closeActivationSuccessDialog: Action;
    closeDeviceTopupModal: Action;
    continueWithSelectedTariff: Action;
    devicesStore: DevicesStore;
    disconnectDevice: Action;
    emailAuthEnabled?: boolean;
    hasMultipleTariffs?: boolean;
    methods?: AnyRecord[];
    plans?: AnyRecord[];
    selectTariff: Action;
    selectedTariff?: AnyRecord | null;
    selectedTariffPlans?: AnyRecord[];
    singleTariffMode?: boolean;
    subscription?: AnyRecord;
    subscriptionPurchaseDescription?: string;
    t: Translate;
    tariffCatalog?: AnyRecord[];
    tariffMode?: boolean;
    termUnitLabel: Action;
    trafficMode?: boolean;
    user?: AnyRecord;
  };

  let {
    accountStore,
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
  class="activation-success-dialog"
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
