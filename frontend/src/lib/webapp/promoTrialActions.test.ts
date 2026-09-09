import { describe, expect, it, vi } from "vitest";

import { createPromoTrialActions } from "./promoTrialActions.js";

function makeActions() {
  const store = {
    activateTrial: vi.fn(() => "activated"),
    applyPromo: vi.fn(() => "applied"),
    clearPromoFieldError: vi.fn(),
    openPromoCheckout: vi.fn(),
    setPromoCode: vi.fn(),
  };
  const getAppSettings = vi.fn(() => ({}));
  const openTrialPayment = vi.fn(() => "checkout");
  return {
    actions: createPromoTrialActions({ actionsStore: store, getAppSettings, openTrialPayment }),
    getAppSettings,
    openTrialPayment,
    store,
  };
}

describe("createPromoTrialActions", () => {
  it("delegates promo code actions to the actions store", () => {
    const { actions, store } = makeActions();

    expect(actions.applyPromo()).toBe("applied");
    actions.setPromoCode("SAVE10");
    actions.clearPromoFieldError();
    actions.openPromoCheckout();

    expect(store.applyPromo).toHaveBeenCalledOnce();
    expect(store.setPromoCode).toHaveBeenCalledWith("SAVE10");
    expect(store.clearPromoFieldError).toHaveBeenCalledOnce();
    expect(store.openPromoCheckout).toHaveBeenCalledOnce();
  });

  it("delegates trial activation to the actions store", () => {
    const { actions, store } = makeActions();

    expect(actions.activateTrial()).toBe("activated");

    expect(store.activateTrial).toHaveBeenCalledOnce();
  });

  it("opens the dedicated checkout when paid trial activation is enabled", () => {
    const { getAppSettings, openTrialPayment, actions, store } = makeActions();
    const plan = { id: "trial:activation", sale_mode: "trial", price: 100 };
    getAppSettings.mockReturnValue({ trial_payment_enabled: true, trial_payment_plan: plan });

    expect(actions.activateTrial()).toBe("checkout");

    expect(openTrialPayment).toHaveBeenCalledWith(plan);
    expect(store.activateTrial).not.toHaveBeenCalled();
  });
});
