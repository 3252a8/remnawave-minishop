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
  return { actions: createPromoTrialActions({ actionsStore: store }), store };
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
});
