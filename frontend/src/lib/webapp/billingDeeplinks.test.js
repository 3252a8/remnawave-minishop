import { describe, expect, it } from "vitest";

import { renewalPaymentConfig, resolveTopupDeeplinkKind } from "./billingDeeplinks.js";

const PLANS = [
  {
    id: "basic-month",
    tariff_key: "basic",
    tariff_name: "Basic",
  },
];

const ACTIVE_SUBSCRIPTION = {
  active: true,
  can_topup_premium_traffic: true,
  can_topup_regular_traffic: true,
  premium_limit_bytes: 10,
  premium_used_bytes: 5,
  tariff_key: "basic",
  traffic_limit_bytes: 10,
  traffic_used_bytes: 5,
};

describe("billing deeplinks", () => {
  it("allows a regular top-up deeplink for active tariff subscriptions", () => {
    expect(
      resolveTopupDeeplinkKind({
        plans: PLANS,
        search: "?topup=regular",
        subscription: ACTIVE_SUBSCRIPTION,
      })
    ).toBe("regular");
  });

  it("allows a premium top-up deeplink when premium traffic is visible", () => {
    expect(
      resolveTopupDeeplinkKind({
        plans: PLANS,
        search: "?topup=premium",
        subscription: ACTIVE_SUBSCRIPTION,
      })
    ).toBe("premium");
  });

  it("rejects unavailable top-up deeplinks", () => {
    expect(
      resolveTopupDeeplinkKind({
        plans: PLANS,
        search: "?topup=regular",
        subscription: { ...ACTIVE_SUBSCRIPTION, can_topup_regular_traffic: false },
      })
    ).toBe("");
    expect(
      resolveTopupDeeplinkKind({
        plans: PLANS,
        search: "?topup=premium",
        subscription: { ...ACTIVE_SUBSCRIPTION, premium_limit_bytes: 0 },
      })
    ).toBe("");
    expect(
      resolveTopupDeeplinkKind({
        plans: PLANS,
        search: "?topup=regular",
        subscription: { ...ACTIVE_SUBSCRIPTION, tariff_key: "missing" },
      })
    ).toBe("");
  });

  it("builds renewal payment config from current plans", () => {
    expect(
      renewalPaymentConfig({
        defaultMethod: "card",
        plans: PLANS,
        subscription: ACTIVE_SUBSCRIPTION,
        tariffKey: "basic",
      })
    ).toMatchObject({
      defaultMethod: "card",
      options: {
        preferCheckout: true,
        preferredTariffKey: "basic",
        selectDefaultTariff: true,
      },
      singleTariffMode: true,
      tariffMode: true,
    });
  });
});
