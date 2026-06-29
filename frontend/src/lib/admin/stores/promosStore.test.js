import { describe, expect, it, vi } from "vitest";

import { createPromosStore } from "./promosStore.svelte.ts";

function promo(overrides = {}) {
  return {
    id: 5,
    code: "SAVE20",
    bonus_days: 0,
    discount_percent: 20,
    duration_multiplier: null,
    traffic_multiplier: null,
    bonus_requires_payment: false,
    applies_to: "subscription",
    min_subscription_months: null,
    min_traffic_gb: null,
    origin: "admin",
    effect_summary: "-20%",
    max_activations: 10,
    current_activations: 2,
    is_active: true,
    valid_until: null,
    created_at: null,
    created_by_admin_id: null,
    ...overrides,
  };
}

function makeStore(api = vi.fn()) {
  const toasts = [];
  const store = createPromosStore({
    api,
    onToast: (message) => toasts.push(message),
    at: (_key, _params, fallback) => fallback || _key,
  });
  return { api, store, toasts };
}

describe("promosStore", () => {
  it("saves edits through the typed admin path", async () => {
    const updated = promo({ discount_percent: 15, effect_summary: "-15%" });
    const api = vi.fn().mockResolvedValue({ ok: true, promo: updated });
    const { store, toasts } = makeStore(api);
    store.promos = [promo()];

    store.openEditPromo(store.promos[0]);
    store.updateEditDraft({ discount_percent: 15 });
    await store.savePromo();

    expect(api).toHaveBeenCalledWith("/admin/promos/5", {
      method: "PATCH",
      body: expect.stringContaining('"discount_percent":15'),
    });
    expect(store.promoEditOpen).toBe(false);
    expect(store.promos[0].discount_percent).toBe(15);
    expect(toasts).toEqual(["Code saved"]);
  });

  it("saves only one active effect when editing old mixed rows", async () => {
    const updated = promo({ bonus_days: 0, discount_percent: 15, effect_summary: "-15%" });
    const api = vi.fn().mockResolvedValue({ ok: true, promo: updated });
    const { store } = makeStore(api);
    store.promos = [promo({ bonus_days: 7, discount_percent: 20, effect_summary: "+7d + -20%" })];

    store.openEditPromo(store.promos[0]);
    store.updateEditDraft({
      bonus_days: 0,
      discount_percent: 15,
      duration_multiplier: null,
      traffic_multiplier: null,
    });
    await store.savePromo();

    const body = JSON.parse(api.mock.calls[0][1].body);
    expect(body.bonus_days).toBe(0);
    expect(body.discount_percent).toBe(15);
    expect(body.duration_multiplier).toBeNull();
    expect(body.traffic_multiplier).toBeNull();
  });

  it("loads activation history for the selected row", async () => {
    const row = {
      activation_id: 9,
      promo_id: 5,
      user_id: 42,
      user_label: "Ada",
      telegram_id: 4242,
      activated_at: "2026-01-03T00:00:00Z",
      payment_id: 77,
      payment_amount: 80,
      payment_currency: "RUB",
      payment_status: "succeeded",
      payment_provider: "yookassa",
      payment_sale_mode: "subscription@standard",
      payment_description: "Subscription",
      payment_created_at: "2026-01-02T00:00:00Z",
      effect_summary: "-20%",
      bonus_days: 0,
      discount_percent: 20,
      duration_multiplier: null,
      traffic_multiplier: null,
      applies_to: "subscription",
    };
    const api = vi.fn().mockResolvedValue({ ok: true, activations: [row], total: 1 });
    const { store } = makeStore(api);

    await store.openActivations(promo());

    expect(api).toHaveBeenCalledWith("/admin/promos/5/activations?page=0&page_size=25");
    expect(store.promoActivationsOpen).toBe(true);
    expect(store.promoActivations).toEqual([row]);
    expect(store.promoActivationsTotal).toBe(1);
  });
});
