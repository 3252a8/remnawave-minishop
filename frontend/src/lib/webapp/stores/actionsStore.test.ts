import { describe, expect, it, vi } from "vitest";

import { createActionsStore } from "./actionsStore.js";
type TestOverrides = Record<string, unknown>;

function makeActionsStore(overrides: TestOverrides = {}) {
  const deps = {
    api: vi.fn(),
    loadData: vi.fn(),
    maybeShowActivationSuccessDialog: vi.fn(),
    showToast: vi.fn(),
    startCheckoutPromo: vi.fn(),
    prefillCheckoutPromo: vi.fn(),
    t: (key: string, _params?: Record<string, unknown>, fallback?: string) => fallback || key,
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

  it("opens checkout from a deeplink when the code applies at checkout", async () => {
    const { deps, store } = makeActionsStore({
      api: vi.fn().mockResolvedValue({
        ok: true,
        status: "requires_checkout",
        code: "SAVE10",
        effect_summary: "-10%",
      }),
    });

    await store.handlePromoDeeplink("save10");

    expect(deps.startCheckoutPromo).toHaveBeenCalledWith("SAVE10");
    expect(store.promoDeeplinkOpen).toBe(false);
  });

  it("only prefills the code when another deeplink modal is already open", async () => {
    const { deps, store } = makeActionsStore({
      api: vi.fn().mockResolvedValue({
        ok: true,
        status: "requires_checkout",
        code: "SAVE10",
        effect_summary: "-10%",
      }),
    });

    await store.handlePromoDeeplink("save10", { modalOpened: true });

    expect(deps.prefillCheckoutPromo).toHaveBeenCalledWith("SAVE10");
    expect(deps.startCheckoutPromo).not.toHaveBeenCalled();
  });

  it("activates standalone codes immediately and shows the success dialog", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: "standalone",
        code: "GIFT7",
        effect_summary: "+7 days",
      })
      .mockResolvedValueOnce({ ok: true, end_date_text: "31.05.2026" });
    const { deps, store } = makeActionsStore({ api });

    await store.handlePromoDeeplink("gift7");

    expect(api).toHaveBeenCalledTimes(2);
    expect(api.mock.calls[1][0]).toBe("/promo/apply");
    expect(store).toMatchObject({
      promoDeeplinkOpen: true,
      promoDeeplinkStatus: "activated",
      promoDeeplinkCode: "GIFT7",
      promoDeeplinkEffectSummary: "+7 days",
    });
    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true });
    expect(deps.startCheckoutPromo).not.toHaveBeenCalled();
  });

  it("falls back to checkout when the code turns checkout-only during activation", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: "standalone", code: "GIFT7" })
      .mockResolvedValueOnce({ ok: true, requires_checkout: true, code: "GIFT7" });
    const { deps, store } = makeActionsStore({ api });

    await store.handlePromoDeeplink("gift7");

    expect(deps.startCheckoutPromo).toHaveBeenCalledWith("GIFT7");
    expect(store.promoDeeplinkOpen).toBe(false);
  });

  it("shows an explanatory dialog when the code was already used", async () => {
    const { deps, store } = makeActionsStore({
      api: vi.fn().mockResolvedValue({
        ok: true,
        status: "already_used",
        code: "GIFT7",
        message: "You already activated GIFT7 on 01.06.2026.",
      }),
    });

    await store.handlePromoDeeplink("gift7");

    expect(store).toMatchObject({
      promoDeeplinkOpen: true,
      promoDeeplinkStatus: "already_used",
      promoDeeplinkMessage: "You already activated GIFT7 on 01.06.2026.",
    });
    expect(deps.startCheckoutPromo).not.toHaveBeenCalled();
  });

  it("shows an invalid-code dialog for unknown codes", async () => {
    const { store } = makeActionsStore({
      api: vi.fn().mockResolvedValue({
        ok: true,
        status: "not_found",
        code: "NOPE",
        message: "Promo code NOPE not found.",
      }),
    });

    await store.handlePromoDeeplink("nope");

    expect(store).toMatchObject({
      promoDeeplinkOpen: true,
      promoDeeplinkStatus: "invalid",
      promoDeeplinkMessage: "Promo code NOPE not found.",
    });
  });

  it("shows an error dialog when the status check fails", async () => {
    const { store } = makeActionsStore({
      api: vi.fn().mockRejectedValue(new Error("network down")),
    });

    await store.handlePromoDeeplink("gift7");

    expect(store).toMatchObject({
      promoDeeplinkOpen: true,
      promoDeeplinkStatus: "error",
      promoDeeplinkMessage: "network down",
    });
  });

  it("shows the invalid dialog when immediate activation fails", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: "standalone", code: "GIFT7" })
      .mockRejectedValueOnce(new Error("used up"));
    const { deps, store } = makeActionsStore({ api });

    await store.handlePromoDeeplink("gift7");

    expect(store).toMatchObject({
      promoDeeplinkOpen: true,
      promoDeeplinkStatus: "invalid",
      promoDeeplinkMessage: "used up",
    });
    expect(deps.loadData).not.toHaveBeenCalled();
  });
});
