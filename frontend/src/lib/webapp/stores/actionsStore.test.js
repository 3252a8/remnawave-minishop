import { describe, expect, it, vi } from "vitest";

import { createActionsStore } from "./actionsStore.ts";

function makeActionsStore(overrides = {}) {
  const deps = {
    api: vi.fn(),
    loadData: vi.fn(),
    maybeShowActivationSuccessDialog: vi.fn(),
    showToast: vi.fn(),
    startCheckoutPromo: vi.fn(),
    t: (key, _params, fallback) => fallback || key,
    ...overrides,
  };
  return { deps, store: createActionsStore(deps) };
}

describe("actionsStore", () => {
  it("keeps checkout-only code available for checkout handoff", async () => {
    const { deps, store } = makeActionsStore({
      api: vi.fn().mockResolvedValue({
        ok: true,
        requires_checkout: true,
        code: "SAVE10",
        effect_summary: "-10%",
      }),
    });

    store.setPromoCode("SAVE10");
    await store.applyPromo();
    store.openPromoCheckout();

    expect(store).toMatchObject({
      promoCheckoutCode: "SAVE10",
      promoCheckoutSummary: "-10%",
      promoIsError: false,
      promoStatus: "-10%",
    });
    expect(deps.loadData).not.toHaveBeenCalled();
    expect(deps.startCheckoutPromo).toHaveBeenCalledWith("SAVE10");
  });
});
