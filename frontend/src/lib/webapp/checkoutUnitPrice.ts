import type { BillingPlan } from "./tariffs.js";
import { billingDurationDays } from "./subscriptionPeriods.js";

/** Informational rates use 30 days; they never become a charge amount. */
export function checkoutUnitPrice<T extends BillingPlan>(
  checkoutPlan: T,
  plan: BillingPlan | null,
  traffic: boolean,
  stars: boolean
): T | null {
  if (!traffic && Number(billingDurationDays(plan) || 0) < 30) return null;
  const divisor = traffic
    ? Number(plan?.traffic_gb || plan?.months || 0)
    : Number(billingDurationDays(plan) || 0) / 30;
  if (!(divisor > 0)) return null;
  const starRate = Number(checkoutPlan.stars_price || 0) / divisor;
  if (stars && starRate > 0 && starRate < 1) return null;
  return {
    ...checkoutPlan,
    price: Math.round((Number(checkoutPlan.price || 0) / divisor) * 100) / 100,
    stars_price: starRate > 0 ? Math.round(starRate) : checkoutPlan.stars_price,
  };
}
