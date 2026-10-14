import { describe, expect, it, vi } from "vitest";

import { billingErrorMessage, createBillingActions } from "./billingActions.js";

describe("billing error translation", () => {
  it("uses the tariff error code for both quote and payment failures", () => {
    const error = {
      error: "tariff_switch_required",
      message: "Switch the active tariff before purchasing its renewal",
    };
    const t = (key: string) => `translated:${key}`;
    expect(billingErrorMessage(error, t)).toBe("translated:wa_tariff_switch_required");
    expect(billingErrorMessage(error, t, "wa_checkout_quote_failed")).toBe(
      "translated:wa_tariff_switch_required"
    );
    expect(billingErrorMessage(null, t, "wa_checkout_quote_failed")).toBe(
      "translated:wa_checkout_quote_failed"
    );
  });
});

describe("billingActions partner balance funding", () => {
  it("keeps the recurring balance consent and flexible limits in subscription payments", () => {
    const actions = createBillingActions({ api: vi.fn() });
    const body = actions.planPaymentBody(
      { months: 3, tariff_key: "standard", sale_mode: "subscription" },
      "balance",
      {
        balanceSource: "partner",
        balanceAutoRenew: true,
        checkoutAddons: { device_count: 2, regular_limit_gb: 250, premium_limit_gb: 50 },
      }
    );
    expect(body).toMatchObject({
      method: "balance",
      balance_source: "partner",
      balance_auto_renew: true,
      checkout_addons: { device_count: 2, regular_limit_gb: 250, premium_limit_gb: 50 },
    });
    expect(actions.planPaymentBody({ months: 1 }, "card").balance_auto_renew).toBe(false);
    expect(actions.topupPaymentBody({ months: 1 }, "card")).not.toHaveProperty(
      "balance_auto_renew"
    );
    expect(actions.deviceTopupPaymentBody({ months: 1 }, "card")).not.toHaveProperty(
      "balance_auto_renew"
    );
  });
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

  it("sends Wata subscription contacts only when checkout provides them", () => {
    const actions = createBillingActions({ api: vi.fn() });
    const plan = {
      months: 1,
      tariff_key: "pro",
      sale_mode: "subscription@pro",
    };

    expect(
      actions.planPaymentBody(plan, "wata_subscription", {
        payerEmail: "person@example.com",
        payerPhone: "+79991234567",
      })
    ).toMatchObject({
      payer_email: "person@example.com",
      payer_phone: "+79991234567",
    });
    expect(actions.planPaymentBody(plan, "card")).not.toHaveProperty("payer_email");
    expect(actions.planPaymentBody(plan, "card")).not.toHaveProperty("payer_phone");
  });
});
