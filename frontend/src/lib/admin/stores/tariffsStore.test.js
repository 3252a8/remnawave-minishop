import { describe, expect, it, vi } from "vitest";

import { createTariffsStore } from "./tariffsStore.svelte.ts";

function makeStore(api = vi.fn(), options = {}) {
  const toasts = [];
  const store = createTariffsStore({
    api,
    onTariffsSaved: options.onTariffsSaved,
    flash: (message) => toasts.push(message),
    at: (key) => key,
  });
  return { api, store, toasts };
}

function periodTariff(overrides = {}) {
  return {
    key: "standard",
    names: { ru: "Standard", en: "Standard" },
    descriptions: { ru: "Base tariff" },
    billing_model: "period",
    enabled: true,
    monthly_gb: 500,
    enabled_periods: [1, 3],
    prices_rub: { 1: 200, 3: 600 },
    prices_stars: { 1: 100, 3: 250 },
    squad_uuids: ["base-squad"],
    ...overrides,
  };
}

function catalog(tariffs) {
  return {
    default_tariff: "standard",
    default_currency: "rub",
    topup_packages_default: { rub: [], stars: [] },
    tariffs,
  };
}

function transientPrices(amount) {
  const transient = { provider: { amount }, handler: () => {} };
  transient.self = transient;
  return transient;
}

describe("tariffsStore", () => {
  it("persists edited period price and regular traffic limit for an existing tariff", async () => {
    const originalTariff = periodTariff();
    const onTariffsSaved = vi.fn().mockResolvedValue(undefined);
    const api = vi.fn(async (_path, options = {}) => {
      const body = JSON.parse(options.body);
      return {
        ok: true,
        exists: true,
        path: "data/tariffs.json",
        provider_currency_support: [],
        catalog: body.catalog,
      };
    });
    const { store, toasts } = makeStore(api, { onTariffsSaved });
    store.updateState({ tariffsCatalog: catalog([originalTariff]) });

    store.openEditTariff(originalTariff);
    store.updateDraftField("monthly_gb", "750");
    store.updateDraftRow("periodRows", 0, { rub: "250" });
    await store.saveTariffDraft();

    expect(api).toHaveBeenCalledWith("/admin/tariffs", {
      method: "PUT",
      body: expect.any(String),
    });
    const body = JSON.parse(api.mock.calls[0][1].body);
    expect(body.catalog.tariffs).toHaveLength(1);
    expect(body.catalog.tariffs[0]).toMatchObject({
      key: "standard",
      monthly_gb: 750,
      prices_rub: { 1: 250, 3: 600 },
    });
    expect(store.tariffsCatalog.tariffs[0]).toMatchObject({
      monthly_gb: 750,
      prices_rub: { 1: 250, 3: 600 },
    });
    expect(store.tariffEditorOpen).toBe(false);
    expect(onTariffsSaved).toHaveBeenCalledWith(body.catalog);
    expect(toasts).toEqual(["tariff_saved"]);
  });

  it("persists HWID package rows even when transient UI data is not cloneable", async () => {
    const api = vi.fn(async (_path, options = {}) => {
      const body = JSON.parse(options.body);
      return {
        ok: true,
        exists: true,
        path: "data/tariffs.json",
        provider_currency_support: [],
        catalog: body.catalog,
      };
    });
    const { store } = makeStore(api);
    store.updateState({ tariffsCatalog: catalog([periodTariff()]) });

    store.openEditTariff(periodTariff());
    store.addDraftRow("hwidRows", {
      count: "2",
      price: "99",
      stars: "",
      prices: transientPrices(99),
    });
    await store.saveTariffDraft();

    expect(api).toHaveBeenCalledWith("/admin/tariffs", {
      method: "PUT",
      body: expect.any(String),
    });
    const body = JSON.parse(api.mock.calls[0][1].body);
    expect(body.catalog.tariffs[0].hwid_device_packages).toEqual({
      rub: [
        {
          count: 2,
          price: 99,
          prices: { provider: { amount: 99 } },
        },
      ],
    });
  });

  it("persists topup and premium package rows with transient pricing metadata", async () => {
    const api = vi.fn(async (_path, options = {}) => {
      const body = JSON.parse(options.body);
      return {
        ok: true,
        exists: true,
        path: "data/tariffs.json",
        provider_currency_support: [],
        catalog: body.catalog,
      };
    });
    const { store } = makeStore(api);
    store.updateState({ tariffsCatalog: catalog([periodTariff()]) });

    store.openEditTariff(periodTariff());
    store.addDraftRow("topupRows", {
      gb: "20",
      price: "150",
      stars: "75",
      prices: transientPrices(150),
      stars_prices: transientPrices(75),
    });
    store.addDraftRow("premiumTopupRows", {
      gb: "30",
      price: "250",
      stars: "125",
      prices: transientPrices(250),
      stars_prices: transientPrices(125),
    });
    await store.saveTariffDraft();

    expect(api).toHaveBeenCalledWith("/admin/tariffs", {
      method: "PUT",
      body: expect.any(String),
    });
    const body = JSON.parse(api.mock.calls[0][1].body);
    expect(body.catalog.tariffs[0].topup_packages).toEqual({
      rub: [{ gb: 20, price: 150, prices: { provider: { amount: 150 } } }],
      stars: [{ gb: 20, price: 75, prices: { provider: { amount: 75 } } }],
    });
    expect(body.catalog.tariffs[0].premium_topup_packages).toEqual({
      rub: [{ gb: 30, price: 250, prices: { provider: { amount: 250 } } }],
      stars: [{ gb: 30, price: 125, prices: { provider: { amount: 125 } } }],
    });
  });

  it("persists traffic package rows with transient pricing metadata", async () => {
    const api = vi.fn(async (_path, options = {}) => {
      const body = JSON.parse(options.body);
      return {
        ok: true,
        exists: true,
        path: "data/tariffs.json",
        provider_currency_support: [],
        catalog: body.catalog,
      };
    });
    const { store } = makeStore(api);
    const trafficTariff = periodTariff({
      key: "traffic",
      billing_model: "traffic",
      traffic_packages: { rub: [], stars: [] },
    });
    store.updateState({ tariffsCatalog: catalog([trafficTariff]) });

    store.openEditTariff(trafficTariff);
    store.addDraftRow("trafficRows", {
      gb: "100",
      price: "399",
      stars: "199",
      prices: transientPrices(399),
      stars_prices: transientPrices(199),
    });
    await store.saveTariffDraft();

    expect(api).toHaveBeenCalledWith("/admin/tariffs", {
      method: "PUT",
      body: expect.any(String),
    });
    const body = JSON.parse(api.mock.calls[0][1].body);
    expect(body.catalog.tariffs[0].traffic_packages).toEqual({
      rub: [{ gb: 100, price: 399, prices: { provider: { amount: 399 } } }],
      stars: [{ gb: 100, price: 199, prices: { provider: { amount: 199 } } }],
    });
  });
});
