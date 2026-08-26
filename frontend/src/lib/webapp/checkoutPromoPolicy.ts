import type { BillingPlan } from "./tariffs.js";

type SelectPaymentMethod = (methodId: string) => void;

export function selectPaymentMethodWithPromoReset(
  methodId: string,
  plan: BillingPlan | null,
  selectMethod: SelectPaymentMethod,
  clearCheckoutPromo: () => void
): void {
  selectMethod(methodId);
  const saleMode = String(plan?.sale_mode || "subscription").toLowerCase();
  if (String(methodId || "").toLowerCase() === "tribute" && saleMode === "subscription") {
    clearCheckoutPromo();
  }
}

export function checkoutPromoAffectsQuotedPlan(
  discount: number,
  scopeMatches: boolean,
  thresholdMatches: boolean
): boolean {
  return discount > 0 && scopeMatches && thresholdMatches;
}

export function normalizedCheckoutPromoDiscount(
  appliedCode: string,
  discountPercent: number
): number {
  const value = Number(discountPercent || 0);
  if (!appliedCode || !Number.isFinite(value) || value <= 0) return 0;
  return Math.min(100, value);
}

export function checkoutPlanSaleMode(plan: BillingPlan | null): string {
  const fallback =
    Number(plan?.device_count || 0) > 0
      ? "hwid_devices"
      : Number(plan?.traffic_gb || 0) > 0
        ? "traffic"
        : "subscription";
  const saleMode = String(plan?.sale_mode || fallback).toLowerCase();
  if (["traffic", "traffic_package"].includes(saleMode)) return "traffic";
  if (["topup", "premium_topup"].includes(saleMode)) return "traffic_topup";
  if (["hwid_device", "hwid_devices", "hwid_devices_renewal"].includes(saleMode)) return "hwid";
  return "subscription";
}

export function checkoutPromoMatchesPlan(
  plan: BillingPlan | null,
  appliesTo: string,
  minSubscriptionMonths: number | null,
  minTrafficGb: number | null
): boolean {
  const saleMode = checkoutPlanSaleMode(plan);
  const scope = String(appliesTo || "all").toLowerCase();
  if (scope !== "all" && scope !== saleMode) return false;

  const minimumMonths = Number(minSubscriptionMonths || 0);
  if (saleMode === "subscription" && minimumMonths > 0) {
    return Number(plan?.months || 0) >= minimumMonths;
  }
  const minimumTrafficGb = Number(minTrafficGb || 0);
  if ((saleMode === "traffic" || saleMode === "traffic_topup") && minimumTrafficGb > 0) {
    return Number(plan?.traffic_gb || plan?.months || 0) >= minimumTrafficGb;
  }
  return true;
}

export function discountedCheckoutPlan(
  plan: BillingPlan | null,
  discount: number
): BillingPlan | null {
  if (!plan || discount <= 0) return plan;
  const multiplier = Math.max(0, 1 - discount / 100);
  const next: BillingPlan = { ...plan };
  if (Number(plan.price || 0) > 0) {
    next.price = Math.round(Number(plan.price || 0) * multiplier * 100) / 100;
  }
  if (Number(plan.stars_price || 0) > 0) {
    next.stars_price = Math.max(1, Math.round(Number(plan.stars_price || 0) * multiplier));
  }
  return next;
}

export function checkoutPromoBlockVisible(
  providerManagesPrice: boolean,
  hasSelectionOrPromoState: boolean
): boolean {
  return !providerManagesPrice && hasSelectionOrPromoState;
}
