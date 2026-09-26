<script lang="ts">
  import DeviceDisconnectDialog from "./payment-dialogs/DeviceDisconnectDialog.svelte";
  import LinkEmailDialog from "./payment-dialogs/LinkEmailDialog.svelte";
  import PaymentCheckoutDialog from "./payment-dialogs/PaymentCheckoutDialog.svelte";
  import SetPasswordDialog from "./payment-dialogs/SetPasswordDialog.svelte";
  import type { ApiClient } from "$lib/webapp/publicApi.js";
  import type {
    CheckoutAddonSelection,
    DeviceView,
    PaymentMethodView,
    PendingPaymentView,
    PlanView,
    SubscriptionView,
    TariffView,
    StringAction,
    TermUnitLabel,
    Translate,
    VoidAction,
  } from "$lib/webapp/types.js";
  import type { CheckoutAddonPreset } from "$lib/webapp/deeplinks.js";
  import { loadPartnerBalanceSnapshot } from "$lib/webapp/partnerBalanceLookup.js";

  type DeviceToDisconnect = DeviceView & {
    display_name?: string | null;
    index?: number | string | null;
  };
  type CheckoutPaymentOptions = {
    balanceSource?: "user" | "partner" | null;
    usePartnerBalance?: boolean;
    checkoutAddons?: CheckoutAddonSelection;
    payerEmail?: string;
    payerPhone?: string;
  };
  type BalancePaymentAction = (options?: CheckoutPaymentOptions) => unknown;
  type CheckoutPromoAction = (options?: Pick<CheckoutPaymentOptions, "checkoutAddons">) => unknown;

  let {
    api,
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
    paymentMethodsDisplayMode = "dropdown",
    checkoutAddonValueAnimationEnabled = true,
    checkoutAddonEditorExpandedByDefault = false,
    pendingPayment = null,
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
    checkoutPromoInput = "",
    checkoutPromoIsError = false,
    checkoutPromoPriceText = "",
    checkoutPromoEffectiveAmount = 0,
    checkoutPromoStatus = "",
    checkoutPromoDiscountPercent = 0,
    checkoutPromoAppliesTo = "all",
    checkoutPromoMinSubscriptionDays = null,
    checkoutPromoMinTrafficGb = null,
    checkoutAddonPreset = null,
    applyCheckoutPromo = () => {},
    backToTariffList = () => {},
    clearCheckoutPromo = () => {},
    continueWithSelectedTariff = () => {},
    resumePendingPayment = () => {},
    cancelPendingPayment = () => {},
    requestLinkEmailCode = () => {},
    requestSetPasswordCode = () => {},
    selectTariff = () => {},
    setCheckoutPromoInput = () => {},
    t = (key) => key,
    termUnitLabel = () => "",
    verifyLinkEmailCode = () => {},
    confirmSetPassword = () => {},
  }: {
    api: ApiClient["api"];
    createPayment?: BalancePaymentAction;
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
    methods?: PaymentMethodView[];
    paymentMethodsDisplayMode?: "dropdown" | "buttons" | string;
    checkoutAddonValueAnimationEnabled?: boolean;
    checkoutAddonEditorExpandedByDefault?: boolean;
    pendingPayment?: PendingPaymentView | null;
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
    subscription?: SubscriptionView;
    subscriptionPurchaseDescription?: string;
    tariffCatalog?: TariffView[];
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
    checkoutPromoEffectiveAmount?: number;
    checkoutPromoStatus?: string;
    checkoutPromoDiscountPercent?: number;
    checkoutPromoAppliesTo?: string;
    checkoutPromoMinSubscriptionDays?: number | null;
    checkoutPromoMinTrafficGb?: number | null;
    checkoutAddonPreset?: CheckoutAddonPreset | null;
    applyCheckoutPromo?: CheckoutPromoAction;
    backToTariffList?: VoidAction;
    clearCheckoutPromo?: VoidAction;
    continueWithSelectedTariff?: VoidAction;
    resumePendingPayment?: (payment: PendingPaymentView) => void;
    cancelPendingPayment?: (payment: PendingPaymentView) => void;
    requestLinkEmailCode?: VoidAction;
    requestSetPasswordCode?: VoidAction;
    selectTariff?: (tariff: TariffView) => void;
    setCheckoutPromoInput?: StringAction;
    t?: Translate;
    termUnitLabel?: TermUnitLabel;
    verifyLinkEmailCode?: VoidAction;
    confirmSetPassword?: VoidAction;
  } = $props();

  $effect(() => {
    const currency = String(selectedPlan?.currency || "").toUpperCase();
    if (!currency) return;
    void loadPartnerBalanceSnapshot(api, currency).catch(() => {});
  });
</script>

<PaymentCheckoutDialog
  {api}
  {createPayment}
  {hasMultipleTariffs}
  {methods}
  {paymentMethodsDisplayMode}
  {checkoutAddonValueAnimationEnabled}
  {checkoutAddonEditorExpandedByDefault}
  {pendingPayment}
  {payBusy}
  bind:paymentModalOpen
  bind:paymentStep
  {plans}
  bind:selectedMethod
  bind:selectedPlan
  {selectedTariff}
  bind:selectedTariffKey
  {selectedTariffPlans}
  bind:renewHwidDevices
  {singleTariffMode}
  {subscription}
  {subscriptionPurchaseDescription}
  {tariffCatalog}
  {tariffMode}
  {trafficMode}
  {closePaymentModal}
  {checkoutPromoAppliedCode}
  {checkoutPromoInput}
  {checkoutPromoIsError}
  {checkoutPromoPriceText}
  {checkoutPromoEffectiveAmount}
  {checkoutPromoStatus}
  {checkoutPromoDiscountPercent}
  {checkoutPromoAppliesTo}
  {checkoutPromoMinSubscriptionDays}
  {checkoutPromoMinTrafficGb}
  {checkoutAddonPreset}
  {applyCheckoutPromo}
  {backToTariffList}
  {clearCheckoutPromo}
  {continueWithSelectedTariff}
  {resumePendingPayment}
  {cancelPendingPayment}
  {selectTariff}
  {setCheckoutPromoInput}
  {t}
  {termUnitLabel}
/>

<DeviceDisconnectDialog
  {deviceConfirmOpen}
  {deviceDisconnectBusy}
  {deviceToDisconnect}
  {disconnectDevice}
  {closeDeviceDisconnectDialog}
  {t}
/>

<SetPasswordDialog
  {setPasswordBusy}
  bind:setPasswordCode
  bind:setPasswordConfirm
  {setPasswordEmail}
  {setPasswordIsError}
  {setPasswordOpen}
  {setPasswordPending}
  {setPasswordResendCooldown}
  {setPasswordStatus}
  bind:setPasswordValue
  {closeSetPasswordDialog}
  {requestSetPasswordCode}
  {confirmSetPassword}
  {t}
/>

<LinkEmailDialog
  {linkEmailBusy}
  bind:linkEmailCode
  bind:linkEmailFieldError
  {linkEmailIsError}
  {linkEmailOpen}
  {linkEmailPending}
  {linkEmailResendCooldown}
  {linkEmailStatus}
  bind:linkEmailValue
  {closeLinkEmailDialog}
  {requestLinkEmailCode}
  {verifyLinkEmailCode}
  {t}
/>
