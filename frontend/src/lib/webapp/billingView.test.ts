import { describe, expect, it } from "vitest";

import { computeBillingView } from "./billingView.js";

describe("computeBillingView", () => {
  const periodPlan = {
    tariff_key: "period",
    tariff_name: "Period",
    billing_model: "period",
    months: 1,
    monthly_gb: 100,
  };
  const trafficPlan = {
    tariff_key: "traffic",
    tariff_name: "Traffic",
    billing_model: "traffic",
    sale_mode: "traffic_package",
    traffic_gb: 25,
  };

  it("keeps legacy non-tariff plans selectable as-is", () => {
    const plans = [
      { id: 1, months: 1 },
      { id: 2, months: 3 },
    ];
    const view = computeBillingView({
      appSettings: { traffic_mode: true },
      plans,
      selectedTariffKey: "",
      subscription: {},
      topupUnlockPercent: 80,
    });

    expect(view.trafficMode).toBe(true);
    expect(view.tariffMode).toBe(false);
    expect(view.selectedTariffPlans).toBe(plans);
    expect(view.currentTariffName).toBe("");
    expect(view.canOpenRegularTopupModal).toBe(false);
  });

  it("derives tariff selection and regular top-up thresholds for period tariffs", () => {
    const view = computeBillingView({
      appSettings: {},
      plans: [periodPlan, trafficPlan],
      selectedTariffKey: "period",
      subscription: {
        active: true,
        tariff_key: "period",
        can_topup_traffic: true,
        traffic_limit_bytes: 100,
        traffic_used_bytes: 79,
      },
      topupUnlockPercent: 80,
    });

    expect(view.tariffMode).toBe(true);
    expect(view.hasMultipleTariffs).toBe(true);
    expect(view.selectedTariff?.key).toBe("period");
    expect(view.selectedTariffPlans).toEqual([periodPlan]);
    expect(view.hasActiveTariffSubscription).toBe(true);
    expect(view.canChangeTariff).toBe(true);
    expect(view.currentTariffName).toBe("Period");
    expect(view.canOpenRegularTopupModal).toBe(true);
    expect(view.regularTrafficTopupUnlocked).toBe(false);
    expect(view.regularTrafficTopupBarClickable).toBe(false);
  });

  it("lets traffic tariffs open top-up from the progress bar before the threshold", () => {
    const view = computeBillingView({
      appSettings: {},
      plans: [trafficPlan],
      selectedTariffKey: "traffic",
      subscription: {
        active: true,
        tariff_key: "traffic",
        can_topup_regular_traffic: true,
        traffic_limit_bytes: 100,
        traffic_used_bytes: 20,
      },
      topupUnlockPercent: 80,
    });

    expect(view.singleTariffMode).toBe(true);
    expect(view.subscriptionIsTrafficTariff).toBe(true);
    expect(view.regularTrafficTopupUnlocked).toBe(false);
    expect(view.regularTrafficTopupBarClickable).toBe(true);
  });

  it("unlocks top-up below the threshold when the tariff allows it always", () => {
    const view = computeBillingView({
      appSettings: {},
      plans: [periodPlan],
      selectedTariffKey: "period",
      subscription: {
        active: true,
        tariff_key: "period",
        can_topup_traffic: true,
        topup_always_available: true,
        traffic_limit_bytes: 100,
        traffic_used_bytes: 5,
      },
      topupUnlockPercent: 80,
    });

    expect(view.canOpenRegularTopupModal).toBe(true);
    expect(view.regularTrafficTopupUnlocked).toBe(true);
    expect(view.regularTrafficTopupBarClickable).toBe(true);
  });

  it("gates regular and premium always-available toggles independently", () => {
    const view = computeBillingView({
      appSettings: {},
      plans: [periodPlan],
      selectedTariffKey: "period",
      subscription: {
        active: true,
        tariff_key: "period",
        can_topup_regular_traffic: true,
        can_topup_premium_traffic: true,
        topup_always_available: false,
        premium_topup_always_available: true,
        traffic_limit_bytes: 100,
        traffic_used_bytes: 5,
        premium_limit_bytes: 100,
        premium_used_bytes: 5,
      },
      topupUnlockPercent: 80,
    });

    expect(view.regularTrafficTopupUnlocked).toBe(false);
    expect(view.premiumTrafficTopupUnlocked).toBe(true);
  });

  it("uses premium-specific top-up permissions before the generic fallback", () => {
    const view = computeBillingView({
      appSettings: {},
      plans: [periodPlan],
      selectedTariffKey: "period",
      subscription: {
        active: true,
        tariff_key: "period",
        can_topup_traffic: true,
        can_topup_premium_traffic: false,
        premium_limit_bytes: 100,
        premium_used_bytes: 95,
      },
      topupUnlockPercent: 80,
    });

    expect(view.canOpenPremiumTopupModal).toBe(false);
    expect(view.premiumTrafficTopupUnlocked).toBe(false);
    expect(view.premiumTrafficTopupBarClickable).toBe(false);
  });
});
