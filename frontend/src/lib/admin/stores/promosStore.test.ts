import { describe, expect, it, vi } from "vitest";

import { createPromosStore } from "./promosStore.svelte";
type TestOverrides = Record<string, unknown>;

function promo(overrides: TestOverrides = {}) {
  return {
    id: 5,
    code: "SAVE20",
    bonus_days: 0,
    regular_traffic_gb: 0,
    premium_traffic_gb: 0,
    discount_percent: 20,
    duration_multiplier: null,
    traffic_multiplier: null,
    bonus_requires_payment: false,
    applies_to: "subscription",
    min_subscription_months: null,
    min_subscription_days: null,
    min_traffic_gb: null,
    origin: "admin",
    effect_summary: "-20%",
    max_activations: 10,
    current_activations: 2,
    is_active: true,
    valid_until: null,
    created_at: null,
    created_by_admin_id: null,
    bot_link: null,
    webapp_link: null,
    user_id: null,
    user_username: null,
    user_name: null,
    ...overrides,
  };
}

function makeStore(api = vi.fn(), routePrefix = "") {
  const toasts: string[] = [];
  const store = createPromosStore({
    api,
    onToast: (message) => toasts.push(message),
    at: (_key: string, _params?: Record<string, unknown>, fallback?: string) => fallback || _key,
    routePrefix,
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

  it("preserves stacked effects when editing a mixed promo", async () => {
    const updated = promo({
      bonus_days: 7,
      regular_traffic_gb: 50,
      premium_traffic_gb: 20,
      discount_percent: 15,
      effect_summary: "+7 days, +50 GB regular, +20 GB premium, -15%",
    });
    const api = vi.fn().mockResolvedValue({ ok: true, promo: updated });
    const { store } = makeStore(api);
    store.promos = [
      promo({
        bonus_days: 7,
        regular_traffic_gb: 50,
        premium_traffic_gb: 20,
        discount_percent: 20,
      }),
    ];

    store.openEditPromo(store.promos[0]);
    store.updateEditDraft({ discount_percent: 15 });
    await store.savePromo();

    const body = JSON.parse(api.mock.calls[0][1].body);
    expect(body.bonus_days).toBe(7);
    expect(body.regular_traffic_gb).toBe(50);
    expect(body.premium_traffic_gb).toBe(20);
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
    const api = vi.fn().mockResolvedValue({
      ok: true,
      activations: [row],
      total: 1,
      revenue_summary: {
        payments_total: 3,
        revenue_payments: 2,
        currencies: [{ currency: "RUB", amount: 160, payments: 2 }],
      },
    });
    const { store } = makeStore(api);

    await store.openActivations(promo());

    expect(api).toHaveBeenCalledWith(
      "/admin/promos/5/activations?page=0&page_size=25&sort=date_desc"
    );
    expect(store.promoActivationsOpen).toBe(true);
    expect(store.promoActivations).toEqual([row]);
    expect(store.promoActivationsTotal).toBe(1);
    expect(store.promoRevenueSummary).toEqual({
      payments_total: 3,
      revenue_payments: 2,
      currencies: [{ currency: "RUB", amount: 160, payments: 2 }],
    });
  });

  it("reloads activation history from page one with the selected sort", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, activations: [], total: 0 });
    const { store } = makeStore(api);
    await store.openActivations(promo());
    api.mockClear();

    store.setActivationsSort("provider_asc");

    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        "/admin/promos/5/activations?page=0&page_size=25&sort=provider_asc"
      )
    );
    expect(store.promoActivationsPage).toBe(0);
  });

  it("keeps create and edit dialogs mutually exclusive", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, activations: [], total: 0 });
    const { store } = makeStore(api);
    const row = promo();

    store.openEditPromo(row);
    expect(store.promoEditOpen).toBe(true);

    store.setCreateOpen(true);
    expect(store.promoCreateOpen).toBe(true);
    expect(store.promoEditOpen).toBe(false);
    expect(store.promoEditing).toBeNull();

    store.openEditPromo(row);
    expect(store.promoCreateOpen).toBe(false);
    expect(store.promoEditOpen).toBe(true);

    await store.openActivations(row);
    store.setCreateOpen(true);
    expect(store.promoActivationsOpen).toBe(false);
    expect(store.promoActivations).toEqual([]);
  });

  it("loads the filtered first page through the typed list path", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      promos: [],
      total: 0,
      owned_total: 0,
    });
    const { store } = makeStore(api);

    store.setStatus("active");
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(1));
    store.setScope("subscription");
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    api.mockClear();

    store.setSearch(" SAVE ");

    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        "/admin/promos?page=0&page_size=25&sort=&kind=shared&search=SAVE&status=active&scope=subscription"
      )
    );
    expect(store.promosPage).toBe(0);
  });

  it("keeps the selected code in the browser path", () => {
    const location = {
      protocol: "https:",
      pathname: "/demo/runtime/admin/promos",
      search: "",
      hash: "",
    };
    vi.stubGlobal("window", {
      location,
      history: {
        pushState: (_state: unknown, _unused: string, value: string) => {
          location.pathname = new URL(value, "https://example.test").pathname;
        },
      },
    });
    try {
      const { store } = makeStore(vi.fn(), "/demo/runtime");
      store.setActive("promos");

      store.openEditPromo(promo());
      expect(window.location.pathname).toBe("/demo/runtime/admin/promos/5");

      store.closeEditPromo();
      expect(window.location.pathname).toBe("/demo/runtime/admin/promos");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
