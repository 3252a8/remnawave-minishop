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
  it("opens checkout for checkout-only promo codes", async () => {
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

    expect(store).toMatchObject({
      promoCheckoutCode: "SAVE10",
      promoCheckoutSummary: "-10%",
      promoIsError: false,
      promoStatus: "-10%",
    });
    expect(deps.loadData).not.toHaveBeenCalled();
    expect(deps.startCheckoutPromo).toHaveBeenCalledWith("SAVE10");
  });

  it("clears stale promo result state when promo input changes", async () => {
    const { store } = makeActionsStore({
      api: vi.fn().mockResolvedValue({
        ok: true,
        requires_checkout: true,
        code: "SAVE10",
        effect_summary: "-10%",
      }),
    });

    store.setPromoCode("SAVE10");
    await store.applyPromo();
    store.setPromoCode("");

    expect(store).toMatchObject({
      promoCheckoutCode: "",
      promoCheckoutSummary: "",
      promoCode: "",
      promoFieldError: "",
      promoIsError: false,
      promoStatus: "",
    });
  });
});
