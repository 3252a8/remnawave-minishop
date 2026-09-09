import { describe, expect, it, vi } from "vitest";

import { createBillingStore } from "./billingStore.js";
type TestOverrides = Record<string, unknown>;

const translateFallback = (key: string, params: Record<string, unknown> = {}, fallback = "") =>
  String(fallback || key).replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`));

function makeBillingStore(overrides: TestOverrides = {}) {
  const { billing: rawBillingOverrides, ...depOverrides } = overrides;
  const billingOverrides = (rawBillingOverrides || {}) as Record<string, unknown>;
  const billing = {
    fetchTopupOptions: vi.fn(),
    fetchDeviceTopupOptions: vi.fn(),
    fetchTariffChangeOptions: vi.fn(),
    notifyPlansViewed: vi.fn().mockResolvedValue({ ok: true }),
    postPayment: vi.fn(),
    cancelPayment: vi.fn(),
    quotePromo: vi.fn(),
    postTariffChange: vi.fn(),
    postTariffChangePayment: vi.fn(),
    planPaymentBody: vi.fn((plan, method, options) => ({ plan, method, options })),
    topupPaymentBody: vi.fn((plan, method, tariffKey) => ({ plan, method, tariffKey })),
    deviceTopupPaymentBody: vi.fn((plan, method, tariffKey) => ({ plan, method, tariffKey })),
    changePaymentBody: vi.fn((action, target, method) => ({ action, target, method })),
    fetchPaymentStatus: vi.fn(),
    ...billingOverrides,
  };
  const deps = {
    billing,
    loadData: vi.fn(),
    t: (key: string) => key,
    termUnitLabel: (value: number, unit: string) => (value === 1 ? unit : `${unit}s`),
    showToast: vi.fn(),
    openExternalLink: vi.fn(),
    ...depOverrides,
  };
  return {
    store: createBillingStore(deps as unknown as Parameters<typeof createBillingStore>[0]),
    deps,
    billing,
  };
}

describe("billingStore", () => {
  it("opens payment modal on preferred default tariff checkout", () => {
    const { store, billing } = makeBillingStore();

    store.openPaymentModal(
      true,
      false,
      [{ key: "pro", is_default: true }] as unknown as Parameters<typeof store.openPaymentModal>[2],
      { active: false },
      [{ id: "plan-1", tariff_key: "pro" }],
      "card",
      { selectDefaultTariff: true, preferCheckout: true }
    );

    expect(store).toMatchObject({
      paymentModalOpen: true,
      paymentStep: "checkout",
      selectedTariffKey: "pro",
      selectedPlan: { id: "plan-1", tariff_key: "pro" },
      selectedMethod: "card",
      renewHwidDevices: true,
    });
    expect(billing.notifyPlansViewed).toHaveBeenCalledWith({
      plans_count: 1,
      tariff_key: "pro",
    });
  });

  it("selects the requested plan period and retains flexible checkout presets", () => {
    const { store } = makeBillingStore();
    const preset = { deviceTotal: 5, regularLimitGb: 300, premiumLimitGb: 100 };

    store.openPaymentModal(
      true,
      false,
      [{ key: "pro", is_default: true }] as unknown as Parameters<typeof store.openPaymentModal>[2],
      { active: false },
      [
        { id: "pro-1", tariff_key: "pro", months: 1 },
        { id: "pro-6", tariff_key: "pro", months: 6 },
      ],
      "card",
      {
        preferredPlanId: "pro",
        preferredTariffKey: "pro",
        preferredMonths: 6,
        checkoutAddonPreset: preset,
      }
    );

    expect(store).toMatchObject({
      paymentModalOpen: true,
      paymentStep: "checkout",
      selectedTariffKey: "pro",
      selectedPlan: { id: "pro-6", months: 6 },
      checkoutAddonPreset: preset,
    });
  });

  it("loads topup options and selects the first plan", async () => {
    const { store, billing } = makeBillingStore({
      billing: {
        fetchTopupOptions: vi.fn().mockResolvedValue({
          ok: true,
          topup_kind: "premium",
          tariff_key: "pro",
          plans: [{ id: "topup-1" }, { id: "topup-2" }],
        }),
      },
    });

    store.openTopupModal("premium", "card");

    await vi.waitFor(() => expect(billing.fetchTopupOptions).toHaveBeenCalledWith("premium"));
    await vi.waitFor(() =>
      expect(store).toMatchObject({
        topupModalOpen: true,
        topupKind: "premium",
        selectedMethod: "card",
        tariffActionBusy: false,
        selectedTopupPlan: { id: "topup-1" },
      })
    );
  });

  it("applies checkout code quote and includes it in payment creation", async () => {
    const { store, deps, billing } = makeBillingStore({
      t: translateFallback,
      billing: {
        postPayment: vi.fn().mockResolvedValue({
          ok: true,
          action: "invoice_sent",
          payment_id: "pay-1",
        }),
        quotePromo: vi.fn().mockResolvedValue({
          ok: true,
          valid: true,
          code: "SAVE10",
          effect_summary: "-10%",
          discount_percent: 10,
          applies_to: "subscription",
          min_subscription_months: null,
          min_traffic_gb: null,
          effective_amount: 90,
        }),
      },
    });

    store.openPaymentModal(
      true,
      false,
      [{ key: "pro", is_default: true }] as unknown as Parameters<typeof store.openPaymentModal>[2],
      { active: false },
      [{ id: "plan-1", tariff_key: "pro" }],
      "card",
      { selectDefaultTariff: true, preferCheckout: true }
    );
    store.setCheckoutPromoInput("SAVE10");

    await store.applyCheckoutPromo();
    await store.createPayment({ usePartnerBalance: true });

    expect(billing.quotePromo).toHaveBeenCalledWith({
      plan: { id: "plan-1", tariff_key: "pro" },
      method: "card",
      options: { renewHwidDevices: false },
      promo_code: "SAVE10",
    });
    expect(store).toMatchObject({
      checkoutPromoInput: "SAVE10",
      checkoutPromoAppliedCode: "SAVE10",
      checkoutPromoPriceText: "90 ₽",
      checkoutPromoStatus: "10% discount",
      checkoutPromoDiscountPercent: 10,
      checkoutPromoAppliesTo: "subscription",
    });
    expect(billing.planPaymentBody).toHaveBeenLastCalledWith(
      { id: "plan-1", tariff_key: "pro" },
      "card",
      {
        promoCode: "SAVE10",
        renewHwidDevices: false,
        usePartnerBalance: true,
      }
    );
    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true, preserveView: true });

    store.clearCheckoutPromo();
    expect(store.checkoutPromoAppliedCode).toBe("");
  });

  it("automatically applies a suggested personal code and lets the user remove it", async () => {
    const { store, billing } = makeBillingStore({
      t: translateFallback,
      billing: {
        quotePromo: vi.fn().mockResolvedValue({
          ok: true,
          valid: true,
          code: "PERSONAL20",
          effect_summary: "-20%",
          discount_percent: 20,
          applies_to: "subscription",
          effective_amount: 80,
        }),
      },
    });

    store.openPaymentModal(
      true,
      false,
      [{ key: "pro", is_default: true }] as unknown as Parameters<typeof store.openPaymentModal>[2],
      { active: false },
      [{ id: "plan-1", tariff_key: "pro" }],
      "card",
      {
        selectDefaultTariff: true,
        preferCheckout: true,
        suggestedPromoCode: "PERSONAL20",
      }
    );

    await vi.waitFor(() => expect(store.checkoutPromoAppliedCode).toBe("PERSONAL20"));
    expect(billing.quotePromo).toHaveBeenCalledOnce();
    expect(store.checkoutPromoStatus).toBe("20% discount");

    store.clearCheckoutPromo();
    expect(store).toMatchObject({
      checkoutPromoInput: "",
      checkoutPromoAppliedCode: "",
      checkoutPromoAutoApply: false,
    });
    expect(billing.quotePromo).toHaveBeenCalledOnce();
  });

  it("keeps fiat pricing for bonus-day promos when Stars are also configured", async () => {
    const { store } = makeBillingStore({
      billing: {
        quotePromo: vi.fn().mockResolvedValue({
          ok: true,
          valid: true,
          code: "BONUS7",
          effect_summary: "+7 days",
          discount_percent: 0,
          applies_to: "subscription",
          effective_amount: 299,
          effective_stars: 150,
          currency: "RUB",
        }),
      },
    });

    store.openPaymentModal(
      false,
      false,
      [],
      { active: false },
      [{ id: "plan-1", price: 299, stars_price: 150, currency: "RUB" }],
      "yookassa"
    );
    store.update((state) => ({
      ...state,
      selectedPlan: { id: "plan-1", price: 299, stars_price: 150, currency: "RUB" },
    }));
    store.setCheckoutPromoInput("BONUS7");

    await store.applyCheckoutPromo();

    expect(store.checkoutPromoPriceText).toBe("299 ₽");
    expect(store.checkoutPromoStatus).toBe("+7 days");
  });

  it("does not call Telegram openInvoice outside a Mini App", async () => {
    const openInvoice = vi.fn();
    const { store, deps } = makeBillingStore({
      billing: {
        postPayment: vi.fn().mockResolvedValue({
          ok: true,
          action: "open_invoice",
          payment_id: "stars-1",
          payment_url: "https://t.me/$invoice",
        }),
      },
      tg: { openInvoice },
      telegramSdk: { hasLaunchParams: vi.fn(() => false) },
    });

    store.openPaymentModal(
      false,
      false,
      [],
      { active: false },
      [{ id: "plan-1", price: 299, stars_price: 150, currency: "RUB" }],
      "stars"
    );
    store.update((state) => ({
      ...state,
      selectedPlan: { id: "plan-1", price: 299, stars_price: 150, currency: "RUB" },
    }));

    await store.createPayment();

    expect(openInvoice).not.toHaveBeenCalled();
    expect(deps.showToast).toHaveBeenCalledWith("wa_payment_stars_telegram_required");
  });

  it("resumes the stored discounted payment link and starts status polling", async () => {
    vi.useFakeTimers();
    const { store, deps, billing } = makeBillingStore({
      billing: {
        fetchPaymentStatus: vi.fn().mockResolvedValue({
          ok: true,
          paid: true,
          status: "succeeded",
        }),
      },
    });
    store.openPaymentModal(
      false,
      false,
      [],
      { active: false },
      [{ id: "plan-1", price: 900, currency: "RUB" }],
      "yookassa",
      { preferredPlanId: "plan-1" }
    );

    await store.resumePendingPayment({
      payment_id: 17,
      payment_url: "https://pay.example/17",
      provider: "yookassa",
      sale_mode: "subscription@pro",
    } as Parameters<typeof store.resumePendingPayment>[0]);

    expect(deps.openExternalLink).toHaveBeenCalledWith("https://pay.example/17");
    expect(deps.showToast).toHaveBeenCalledWith("wa_pending_payment_opened");
    expect(store.paymentModalOpen).toBe(false);

    await vi.advanceTimersByTimeAsync(1500);
    expect(billing.fetchPaymentStatus).toHaveBeenCalledWith(17);
    vi.useRealTimers();
  });

  it("cancels a pending checkout and reapplies its promo to the selected plan", async () => {
    const { store, deps, billing } = makeBillingStore({
      t: translateFallback,
      billing: {
        cancelPayment: vi.fn().mockResolvedValue({
          ok: true,
          payment_id: 17,
          status: "canceled",
        }),
        quotePromo: vi.fn().mockResolvedValue({
          ok: true,
          valid: true,
          code: "SAVE20",
          effect_summary: "-20%",
          discount_percent: 20,
          applies_to: "subscription",
          effective_amount: 720,
        }),
      },
    });
    store.openPaymentModal(
      false,
      false,
      [],
      { active: false },
      [{ id: "plan-1", price: 900, currency: "RUB" }],
      "yookassa",
      { preferredPlanId: "plan-1" }
    );

    await store.cancelPendingPayment({
      payment_id: 17,
      payment_url: "https://pay.example/17",
      provider: "yookassa",
      promo_code: "SAVE20",
    } as Parameters<typeof store.cancelPendingPayment>[0]);

    expect(billing.cancelPayment).toHaveBeenCalledWith(17);
    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true, preserveView: true });
    expect(billing.quotePromo).toHaveBeenCalledOnce();
    expect(store).toMatchObject({
      paymentModalOpen: true,
      checkoutPromoInput: "SAVE20",
      checkoutPromoAppliedCode: "SAVE20",
      checkoutPromoStatus: "20% discount",
    });
    expect(deps.showToast).toHaveBeenCalledWith("wa_pending_payment_canceled");
  });

  it("keeps a pending promo reserved when provider cancellation is unavailable", async () => {
    const { store, deps, billing } = makeBillingStore({
      billing: {
        cancelPayment: vi.fn().mockResolvedValue({
          ok: false,
          error: "payment_cancel_unavailable",
        }),
      },
    });

    await store.cancelPendingPayment({
      payment_id: 17,
      promo_code: "SAVE20",
    } as Parameters<typeof store.cancelPendingPayment>[0]);

    expect(billing.cancelPayment).toHaveBeenCalledWith(17);
    expect(deps.loadData).not.toHaveBeenCalled();
    expect(deps.showToast).toHaveBeenCalledWith("wa_pending_payment_cancel_unavailable");
  });

  it("applies no-payment tariff changes and refreshes data", async () => {
    const { store, deps, billing } = makeBillingStore({
      billing: {
        postTariffChange: vi.fn().mockResolvedValue({ ok: true }),
      },
    });
    store.update((s) => ({
      ...s,
      selectedChangeTarget: { tariff_key: "plus" } as unknown as NonNullable<
        typeof s.selectedChangeTarget
      >,
      selectedChangeAction: { mode: "switch", kind: "now" },
      changeConfirmOpen: true,
      changeModalOpen: true,
    }));

    await store.applyTariffChange();

    expect(billing.postTariffChange).toHaveBeenCalledWith({
      tariff_key: "plus",
      mode: "switch",
    });
    expect(deps.showToast).toHaveBeenCalledWith("wa_tariff_change_applied");
    expect(deps.loadData).toHaveBeenCalled();
    expect(store).toMatchObject({
      changeConfirmOpen: false,
      changeModalOpen: false,
      changeOptions: null,
      tariffActionBusy: false,
    });
  });
});
