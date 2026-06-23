import { get } from "svelte/store";
import { describe, expect, it, vi } from "vitest";

import { createBillingStore } from "./billingStore.ts";

function makeBillingStore(overrides = {}) {
  const billing = {
    fetchTopupOptions: vi.fn(),
    fetchDeviceTopupOptions: vi.fn(),
    fetchTariffChangeOptions: vi.fn(),
    postPayment: vi.fn(),
    postTariffChange: vi.fn(),
    postTariffChangePayment: vi.fn(),
    planPaymentBody: vi.fn((plan, method, options) => ({ plan, method, options })),
    topupPaymentBody: vi.fn((plan, method, tariffKey) => ({ plan, method, tariffKey })),
    deviceTopupPaymentBody: vi.fn((plan, method, tariffKey) => ({ plan, method, tariffKey })),
    changePaymentBody: vi.fn((action, target, method) => ({ action, target, method })),
    fetchPaymentStatus: vi.fn(),
    ...overrides.billing,
  };
  const deps = {
    billing,
    loadData: vi.fn(),
    t: (key) => key,
    showToast: vi.fn(),
    openExternalLink: vi.fn(),
    ...overrides,
  };
  return { store: createBillingStore(deps), deps, billing };
}

describe("billingStore", () => {
  it("opens payment modal on preferred default tariff checkout", () => {
    const { store } = makeBillingStore();

    store.openPaymentModal(
      true,
      false,
      [{ key: "pro", is_default: true }],
      { active: false },
      [{ id: "plan-1", tariff_key: "pro" }],
      "card",
      { selectDefaultTariff: true, preferCheckout: true }
    );

    expect(get(store)).toMatchObject({
      paymentModalOpen: true,
      paymentStep: "checkout",
      selectedTariffKey: "pro",
      selectedPlan: { id: "plan-1", tariff_key: "pro" },
      selectedMethod: "card",
      renewHwidDevices: true,
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
      expect(get(store)).toMatchObject({
        topupModalOpen: true,
        topupKind: "premium",
        selectedMethod: "card",
        tariffActionBusy: false,
        selectedTopupPlan: { id: "topup-1" },
      })
    );
  });

  it("applies no-payment tariff changes and refreshes data", async () => {
    const { store, deps, billing } = makeBillingStore({
      billing: {
        postTariffChange: vi.fn().mockResolvedValue({ ok: true }),
      },
    });
    store.update((s) => ({
      ...s,
      selectedChangeTarget: { tariff_key: "plus" },
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
    expect(get(store)).toMatchObject({
      changeConfirmOpen: false,
      changeModalOpen: false,
      changeOptions: null,
      tariffActionBusy: false,
    });
  });
});
