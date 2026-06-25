<script lang="ts">
  import type { Writable } from "svelte/store";

  import { CheckCircle2 } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import PaymentDialogs from "./PaymentDialogs.svelte";
  import TariffDialogs from "./TariffDialogs.svelte";

  type AnyRecord = Record<string, any>;
  type StoreLike = Writable<AnyRecord> & Record<string, any>;
  type Action = (...args: any[]) => any;
  type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

  export let accountStore: StoreLike;
  export let activationSuccessDialogOpen = false;
  export let activationSuccessUseInstallGuides = false;
  export let backToTariffList: Action;
  export let billingStore: StoreLike;
  export let closeActivationSuccessDialog: Action;
  export let closeDeviceTopupModal: Action;
  export let continueWithSelectedTariff: Action;
  export let devicesStore: StoreLike;
  export let disconnectDevice: Action;
  export let emailAuthEnabled = true;
  export let hasMultipleTariffs = false;
  export let methods: AnyRecord[] = [];
  export let plans: AnyRecord[] = [];
  export let selectTariff: Action;
  export let selectedTariff: AnyRecord | null = null;
  export let selectedTariffPlans: AnyRecord[] = [];
  export let singleTariffMode = false;
  export let subscription: AnyRecord = {};
  export let subscriptionPurchaseDescription = "";
  export let t: Translate;
  export let tariffCatalog: AnyRecord[] = [];
  export let tariffMode = false;
  export let termUnitLabel: Action;
  export let trafficMode = false;
  export let user: AnyRecord = {};
</script>

<PaymentDialogs
  bind:linkEmailCode={$accountStore.linkEmailCode}
  bind:linkEmailFieldError={$accountStore.linkEmailFieldError}
  bind:linkEmailValue={$accountStore.linkEmailValue}
  bind:paymentModalOpen={$billingStore.paymentModalOpen}
  bind:paymentStep={$billingStore.paymentStep}
  bind:selectedMethod={$billingStore.selectedMethod}
  bind:selectedPlan={$billingStore.selectedPlan}
  bind:renewHwidDevices={$billingStore.renewHwidDevices}
  bind:selectedTariffKey={$billingStore.selectedTariffKey}
  bind:setPasswordCode={$accountStore.setPasswordCode}
  bind:setPasswordConfirm={$accountStore.setPasswordConfirm}
  bind:setPasswordValue={$accountStore.setPasswordValue}
  setPasswordEmail={user?.email || ""}
  createPayment={billingStore.createPayment}
  deviceConfirmOpen={$devicesStore.deviceConfirmOpen}
  deviceDisconnectBusy={$devicesStore.deviceDisconnectBusy}
  deviceToDisconnect={$devicesStore.deviceToDisconnect}
  {disconnectDevice}
  linkEmailBusy={$accountStore.linkEmailBusy}
  linkEmailIsError={$accountStore.linkEmailIsError}
  linkEmailOpen={emailAuthEnabled && $accountStore.linkEmailOpen}
  linkEmailPending={$accountStore.linkEmailPending}
  linkEmailResendCooldown={$accountStore.linkEmailResendCooldown}
  linkEmailStatus={$accountStore.linkEmailStatus}
  setPasswordBusy={$accountStore.setPasswordBusy}
  setPasswordIsError={$accountStore.setPasswordIsError}
  setPasswordOpen={emailAuthEnabled && $accountStore.setPasswordOpen}
  setPasswordPending={$accountStore.setPasswordPending}
  setPasswordResendCooldown={$accountStore.setPasswordResendCooldown}
  setPasswordStatus={$accountStore.setPasswordStatus}
  {hasMultipleTariffs}
  {methods}
  payBusy={$billingStore.payBusy}
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
  bind:changeConfirmOpen={$billingStore.changeConfirmOpen}
  bind:changeModalOpen={$billingStore.changeModalOpen}
  bind:deviceTopupModalOpen={$billingStore.deviceTopupModalOpen}
  bind:selectedChangeAction={$billingStore.selectedChangeAction}
  bind:selectedChangeTarget={$billingStore.selectedChangeTarget}
  bind:selectedDeviceTopupPlan={$billingStore.selectedDeviceTopupPlan}
  bind:selectedMethod={$billingStore.selectedMethod}
  bind:selectedTopupPlan={$billingStore.selectedTopupPlan}
  bind:topupModalOpen={$billingStore.topupModalOpen}
  applyTariffChange={billingStore.applyTariffChange}
  changeOptions={$billingStore.changeOptions}
  {closeDeviceTopupModal}
  closeTariffChangeConfirm={billingStore.closeTariffChangeConfirm}
  closeTariffChangeModal={billingStore.closeTariffChangeModal}
  closeTopupModal={billingStore.closeTopupModal}
  createDeviceTopupPayment={billingStore.createDeviceTopupPayment}
  createTopupPayment={billingStore.createTopupPayment}
  deviceTopupOptions={$billingStore.deviceTopupOptions}
  {methods}
  openTariffChangeConfirm={billingStore.openTariffChangeConfirm}
  payBusy={$billingStore.payBusy}
  {singleTariffMode}
  {subscription}
  tariffActionBusy={$billingStore.tariffActionBusy}
  topupKind={$billingStore.topupKind}
  topupOptions={$billingStore.topupOptions}
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
