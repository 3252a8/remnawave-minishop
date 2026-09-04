import { describe, expect, it, vi } from "vitest";

import { createBillingActions } from "./billingActions.js";

describe("billingActions partner balance funding", () => {
  it("includes the selection in every supported checkout payload", () => {
    const actions = createBillingActions({ api: vi.fn() });
    const plan = {
      months: 3,
      traffic_gb: 50,
      device_count: 2,
      tariff_key: "pro",
      sale_mode: "subscription@pro",
    };

    expect(
      actions.planPaymentBody(plan, "card", {
        usePartnerBalance: true,
      })
    ).toMatchObject({ balance_source: "partner", use_partner_balance: true });
    expect(actions.topupPaymentBody(plan, "card", "pro", null, true)).toMatchObject({
      balance_source: "partner",
      use_partner_balance: true,
    });
    expect(actions.deviceTopupPaymentBody(plan, "card", "pro", null, true)).toMatchObject({
      balance_source: "partner",
      use_partner_balance: true,
    });
    expect(
      actions.changePaymentBody(
        { mode: "buy_period", months: 3 },
        { tariff_key: "pro" },
        "card",
        true
      )
    ).toMatchObject({ balance_source: "partner", use_partner_balance: true });
  });

  it("sends the explicit main balance source through every checkout flow", () => {
    const actions = createBillingActions({ api: vi.fn() });
    const plan = {
      months: 3,
      traffic_gb: 50,
      device_count: 2,
      tariff_key: "pro",
      sale_mode: "subscription@pro",
    };

    expect(actions.planPaymentBody(plan, "card", { balanceSource: "user" })).toMatchObject({
      balance_source: "user",
      use_partner_balance: false,
    });
    expect(actions.topupPaymentBody(plan, "card", "pro", null, false, "user")).toMatchObject({
      balance_source: "user",
    });
    expect(actions.deviceTopupPaymentBody(plan, "card", "pro", null, false, "user")).toMatchObject({
      balance_source: "user",
    });
    expect(
      actions.changePaymentBody(
        { mode: "buy_period", months: 3 },
        { tariff_key: "pro" },
        "card",
        false,
        "user"
      )
    ).toMatchObject({ balance_source: "user" });
  });

  it("prefers a device checkout add-on over legacy device renewal", () => {
    const actions = createBillingActions({ api: vi.fn() });
    const plan = {
      months: 1,
      tariff_key: "pro",
      sale_mode: "subscription@pro",
    };

    expect(
      actions.planPaymentBody(plan, "card", {
        renewHwidDevices: true,
        checkoutAddons: {
          device_count: 2,
          regular_limit_gb: null,
          premium_limit_gb: null,
        },
      })
    ).toMatchObject({
      renew_hwid_devices: false,
      checkout_addons: { device_count: 2 },
    });
    expect(
      actions.planPaymentBody(plan, "card", {
        renewHwidDevices: true,
        checkoutAddons: {
          device_count: 0,
          regular_limit_gb: null,
          premium_limit_gb: null,
        },
      })
    ).toMatchObject({ renew_hwid_devices: true });
  });

  it("includes the selected active-trial day strategy", () => {
    const actions = createBillingActions({ api: vi.fn() });
    const plan = {
      months: 1,
      tariff_key: "pro",
      sale_mode: "subscription@pro",
    };

    expect(
      actions.planPaymentBody(plan, "card", {
        trialDaysStrategy: "start_from_payment",
      })
    ).toMatchObject({ trial_days_strategy: "start_from_payment" });
  });
});
