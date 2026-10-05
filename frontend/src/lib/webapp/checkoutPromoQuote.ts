import type { BillingActions } from "./billingActions.js";
import type { CheckoutAddonSelection } from "./tariffs.js";
import { priceLabel } from "./tariffs.js";
import type { PlanView } from "./types.js";
import {
  billingStringField as stringField,
  type BillingRecord,
  type BillingState,
} from "./stores/billingStoreSupport.js";

export function checkoutPromoPlan(state: BillingState): PlanView | null {
  return (
    (state.paymentModalOpen && state.selectedPlan) ||
    (state.topupModalOpen && state.selectedTopupPlan) ||
    (state.deviceTopupModalOpen && state.selectedDeviceTopupPlan) ||
    null
  );
}

export function checkoutPromoQuoteBody(
  state: BillingState,
  billing: BillingActions,
  checkoutAddons: CheckoutAddonSelection | undefined
) {
  const code = String(state.checkoutPromoInput || state.checkoutPromoAppliedCode || "").trim();
  if (!code || !state.selectedMethod) return null;
  if (state.paymentModalOpen && state.selectedPlan) {
    return {
      ...billing.planPaymentBody(state.selectedPlan, state.selectedMethod, {
        renewHwidDevices:
          state.renewHwidDevices && Boolean(state.selectedPlan?.hwid_renewal?.available),
        checkoutAddons,
      }),
      promo_code: code,
    };
  }
  if (state.topupModalOpen && state.selectedTopupPlan) {
    return {
      ...billing.topupPaymentBody(
        state.selectedTopupPlan,
        state.selectedMethod,
        stringField(state.topupOptions?.tariff_key)
      ),
      promo_code: code,
    };
  }
  if (state.deviceTopupModalOpen && state.selectedDeviceTopupPlan) {
    return {
      ...billing.deviceTopupPaymentBody(
        state.selectedDeviceTopupPlan,
        state.selectedMethod,
        stringField(state.deviceTopupOptions?.tariff_key)
      ),
      promo_code: code,
    };
  }
  return null;
}

function checkoutPlanKey(plan: PlanView | null): string {
  if (!plan) return "";
  return String(
    plan.id ||
      `${plan.tariff_key || ""}:${plan.sale_mode || ""}:${plan.months || ""}:${plan.traffic_gb || ""}`
  );
}

export function checkoutPromoQuoteKey(
  state: BillingState,
  checkoutAddons: CheckoutAddonSelection | undefined
): string {
  const code = String(
    state.checkoutPromoAppliedCode ||
      (state.checkoutPromoAutoApply || state.checkoutPromoIsError ? state.checkoutPromoInput : "")
  ).trim();
  if (!code || !state.selectedMethod) return "";
  if (state.paymentModalOpen && state.selectedPlan) {
    return [
      "payment",
      code,
      state.selectedMethod,
      checkoutPlanKey(state.selectedPlan),
      state.renewHwidDevices ? "hwid" : "no-hwid",
      JSON.stringify(checkoutAddons || {}),
    ].join(":");
  }
  if (state.topupModalOpen && state.selectedTopupPlan) {
    return [
      "topup",
      code,
      state.selectedMethod,
      checkoutPlanKey(state.selectedTopupPlan),
      state.topupKind,
    ].join(":");
  }
  if (state.deviceTopupModalOpen && state.selectedDeviceTopupPlan) {
    return [
      "device",
      code,
      state.selectedMethod,
      checkoutPlanKey(state.selectedDeviceTopupPlan),
    ].join(":");
  }
  return "";
}

export function checkoutPromoPriceText(payload: BillingRecord, selectedMethod: string): string {
  const amount = Number(payload.effective_amount || 0);
  const stars = Number(payload.effective_stars || 0);
  if (amount <= 0 && stars <= 0) return "";
  return priceLabel(
    {
      price: amount,
      stars_price: stars,
      currency: stringField(payload.currency) || undefined,
    },
    selectedMethod
  );
}
