import type { BillingActions, PartnerBalancePaymentOptions } from "./billingActions.js";
import type { createPaymentResponseHandler } from "./billingPaymentResume.js";
import { paymentProviderUnavailable } from "./paymentFallback.js";
import {
  SUBSCRIPTION_DAYS_METHOD,
  subscriptionDaysQuote,
  subscriptionDaysQuoteUsable,
  subscriptionDaysRequestError,
} from "./subscriptionDays.js";
import { planKey } from "./tariffs.js";
import {
  asBillingRecord,
  billingRecordArray,
  billingStringField,
  unwrapBilling,
  type BillingState,
} from "./stores/billingStoreSupport.js";
import type { PlanView, Translate } from "./types.js";

export function createTopupPaymentAction(
  devices: boolean,
  {
    billing,
    getState,
    updateState,
    checkoutPromoCode,
    handlePaymentResponse,
    showToast,
    t,
  }: {
    billing: BillingActions;
    getState: () => BillingState;
    updateState: (updater: (state: BillingState) => BillingState) => void;
    checkoutPromoCode: () => string | null;
    handlePaymentResponse: ReturnType<typeof createPaymentResponseHandler>;
    showToast: (message: string) => void;
    t: Translate;
  }
) {
  async function refreshQuote(previous: PlanView, kind: string): Promise<void> {
    const response = devices
      ? await billing.fetchDeviceTopupOptions()
      : await billing.fetchTopupOptions(kind);
    if (!response.ok) throw response;
    const payload = unwrapBilling(response);
    const plans = billingRecordArray<PlanView>(payload.plans);
    const selected = plans.find((plan) => planKey(plan) === planKey(previous)) || plans[0] || null;
    updateState((state) => ({
      ...state,
      ...(devices
        ? { deviceTopupOptions: payload, selectedDeviceTopupPlan: selected }
        : { topupOptions: payload, selectedTopupPlan: selected }),
    }));
  }

  return async function createTopupPayment(
    options: PartnerBalancePaymentOptions = {}
  ): Promise<void> {
    const state = getState();
    const plan = devices ? state.selectedDeviceTopupPlan : state.selectedTopupPlan;
    const method = options.paymentMethod || state.selectedMethod;
    if (!plan || !method || state.payBusy) return;
    if (
      method === SUBSCRIPTION_DAYS_METHOD &&
      !subscriptionDaysQuoteUsable(subscriptionDaysQuote(plan))
    ) {
      showToast(t("wa_subscription_days_unavailable"));
      return;
    }
    const kind = state.topupKind;
    const topupOptions = devices ? state.deviceTopupOptions : state.topupOptions;
    updateState((current) => ({ ...current, payBusy: true }));
    try {
      const buildBody = devices ? billing.deviceTopupPaymentBody : billing.topupPaymentBody;
      const response = await billing.postPayment(
        buildBody(
          plan,
          method,
          billingStringField(topupOptions?.tariff_key),
          checkoutPromoCode(),
          options.usePartnerBalance,
          options.balanceSource
        )
      );
      await handlePaymentResponse(response, {}, () => {
        updateState((current) => ({
          ...current,
          ...(devices ? { deviceTopupModalOpen: false } : { topupModalOpen: false }),
          // A completed purchase can change the expiry used by either quote.
          topupOptions: null,
          deviceTopupOptions: null,
        }));
      });
    } catch (error: unknown) {
      const code = subscriptionDaysRequestError(error);
      if (method === SUBSCRIPTION_DAYS_METHOD && code) {
        if (code === "subscription_days_quote_stale" || code === "subscription_days_unavailable") {
          try {
            await refreshQuote(plan, kind);
          } catch {
            updateState((current) => ({
              ...current,
              ...(devices
                ? {
                    deviceTopupOptions: null,
                    selectedDeviceTopupPlan: null,
                    deviceTopupModalOpen: false,
                  }
                : { topupOptions: null, selectedTopupPlan: null, topupModalOpen: false }),
            }));
            showToast(t("wa_tariff_options_failed"));
            return;
          }
        }
        showToast(t(`wa_${code}`));
      } else if (paymentProviderUnavailable(error) && options.onProviderUnavailable) {
        options.onProviderUnavailable(method);
      } else {
        showToast(
          billingStringField(asBillingRecord(error).message) || t("wa_payment_create_failed")
        );
      }
    } finally {
      updateState((current) => ({ ...current, payBusy: false }));
    }
  };
}
