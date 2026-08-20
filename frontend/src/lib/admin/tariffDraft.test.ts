import { describe, expect, it } from "vitest";

import {
  cloneCatalog,
  draftFromTariff,
  emptyTariffDraft,
  normalizeCurrencyKey,
  normalizeUuidList,
  packageRowsFromPackageSet,
  packageSetFromRows,
  tariffFromDraft,
  tributeProductsFromRows,
} from "./tariffDraft";

describe("tariffDraft", () => {
  it("normalizes currency aliases and clones catalog defaults", () => {
    expect(normalizeCurrencyKey(" RUR ")).toBe("rub");
    expect(normalizeCurrencyKey("XTR")).toBe("stars");
    expect(normalizeCurrencyKey("***", "usd")).toBe("usd");

    const source = new Proxy({ default_currency: "RUR", tariffs: [{ key: "base" }] }, {});
    const cloned = cloneCatalog(source);
    cloned.tariffs[0].key = "changed";

    expect(cloned.default_currency).toBe("rub");
    expect(source.tariffs[0].key).toBe("base");
  });

  it("merges default-currency and Stars package rows by value", () => {
    expect(
      packageRowsFromPackageSet(
        {
          rub: [{ gb: 10, price: 100 }],
          stars: [
            { gb: 10, price: 50 },
            { gb: 30, price: 120 },
          ],
        },
        "rub",
        "gb"
      )
    ).toEqual([
      {
        gb: 10,
        price: 100,
        stars: 50,
        prices: undefined,
        min_price: "",
        stars_prices: undefined,
        stars_min_price: "",
      },
      { gb: 30, price: "", stars: 120, stars_prices: undefined, stars_min_price: "" },
    ]);
  });

  it("builds package sets from valid rows only", () => {
    expect(
      packageSetFromRows(
        [
          { gb: "10", price: "199", stars: "50" },
          { gb: "0", price: "199", stars: "50" },
          { gb: "30", price: "", stars: "120" },
        ],
        "gb",
        "rub"
      )
    ).toEqual({
      rub: [{ gb: 10, price: 199 }],
      stars: [
        { gb: 10, price: 50 },
        { gb: 30, price: 120 },
      ],
    });
  });

  it("keeps each period on the Tribute subscription that sells it", () => {
    // Tribute publishes one subscription per offer, so a tariff can map a
    // different subscription for every period it sells.
    const tariff = {
      key: "pro",
      enabled_periods: [1, 12],
      prices_rub: { 1: 200, 12: 2000 },
      tribute: {
        period_ids: { 1: 1001, 12: 4001 },
        period_links: {
          1: "https://t.me/tribute/app?startapp=ep_monthly",
          12: "https://t.me/tribute/app?startapp=ep_yearly",
        },
        period_subscription_ids: { 1: 101, 12: 909 },
      },
    };

    const draft = draftFromTariff(tariff, "rub");

    expect(draft.periodRows[0]).toMatchObject({
      months: 1,
      tribute_period_id: 1001,
      tribute_link: "https://t.me/tribute/app?startapp=ep_monthly",
      tribute_subscription_id: 101,
    });
    expect(draft.periodRows[1]).toMatchObject({
      months: 12,
      tribute_subscription_id: 909,
    });

    expect(tariffFromDraft(draft)).toMatchObject({
      tribute: {
        period_ids: { 1: 1001, 12: 4001 },
        period_links: {
          1: "https://t.me/tribute/app?startapp=ep_monthly",
          12: "https://t.me/tribute/app?startapp=ep_yearly",
        },
        period_subscription_ids: { 1: 101, 12: 909 },
      },
    });
  });

  it("round-trips period tariffs through draft form", () => {
    const tariff = {
      key: "pro",
      legacy_keys: ["premium"],
      names: { ru: "Про" },
      enabled_periods: [1, 3],
      prices_rub: { 1: 200, 3: 550 },
      prices_stars: { 1: 90 },
      referral_bonus_days_inviter: { 1: 3 },
      referral_bonus_days_referee: { 1: 1 },
      squad_uuids: ["a", "b"],
      premium_squad_uuids: ["premium-squad"],
      monthly_gb: 500,
      traffic_limit_strategy: "WEEK",
      premium_traffic_limit_strategy: "MONTH",
      topup_packages: { rub: [{ gb: 10, price: 199 }] },
      flexible_traffic_limit: {
        step_gb: 50,
        max_total_gb: 700,
        price_per_step: 99,
        stars_price_per_step: 50,
      },
      premium_flexible_traffic_limit: {
        step_gb: 25,
        max_total_gb: 100,
        price_per_step: 79,
      },
      checkout_addons: {
        devices: {
          enabled: true,
          max_extra_devices: 4,
          price_per_device: 79,
          stars_price_per_device: 40,
        },
        traffic: { enabled: true },
        premium_traffic: { enabled: false },
      },
      tribute: {
        link: "https://t.me/tribute/app?startapp=pro",
        subscription_id: 101,
        period_ids: { 1: 1001, 3: 1003 },
        traffic_products: {
          10: {
            product_id: 501,
            link: "https://tribute.tg/products/501",
          },
        },
      },
    };

    const draft = draftFromTariff(tariff, "rub");
    expect(draft.key).toBe("pro");
    expect(draft.legacyKeys).toEqual(["premium"]);
    expect(draft.traffic_limit_strategy).toBe("WEEK");
    expect(draft.premium_traffic_limit_strategy).toBe("MONTH");
    expect(draft.tributeLink).toBe("https://t.me/tribute/app?startapp=pro");
    expect(draft.tributeSubscriptionId).toBe(101);
    expect(draft.topupRows).toEqual([
      {
        gb: 10,
        price: 199,
        prices: undefined,
        min_price: "",
        stars: "",
        stars_prices: undefined,
        stars_min_price: "",
        tribute_product_id: 501,
        tribute_product_link: "https://tribute.tg/products/501",
      },
    ]);
    expect(draft.flexible_traffic_step_gb).toBe(50);
    expect(draft.flexible_traffic_max_total_gb).toBe(700);
    expect(draft.flexible_traffic_price_per_step).toBe(99);
    expect(draft.flexible_traffic_stars_price_per_step).toBe(50);
    expect(draft.premium_flexible_traffic_step_gb).toBe(25);
    expect(draft.premium_flexible_traffic_max_total_gb).toBe(100);
    expect(draft.premium_flexible_traffic_price_per_step).toBe(79);
    expect(draft.checkout_devices_enabled).toBe(true);
    expect(draft.checkout_devices_max_extra).toBe(4);
    expect(draft.checkout_devices_price_per_device).toBe(79);
    expect(draft.checkout_devices_stars_price_per_device).toBe(40);
    expect(draft.periodRows).toEqual([
      {
        months: 1,
        rub: 200,
        stars: 90,
        referral_inviter: 3,
        referral_referee: 1,
        tribute_period_id: 1001,
        tribute_link: "",
        tribute_subscription_id: "",
      },
      {
        months: 3,
        rub: 550,
        stars: "",
        referral_inviter: "",
        referral_referee: "",
        tribute_period_id: 1003,
        tribute_link: "",
        tribute_subscription_id: "",
      },
    ]);

    draft.squadUuids = " a\nb, c ";
    draft.periodRows.push({ months: 3, rub: 600, stars: 10 });
    expect(tariffFromDraft(draft)).toMatchObject({
      key: "pro",
      legacy_keys: ["premium"],
      names: { ru: "Про" },
      squad_uuids: ["a", "b", "c"],
      enabled_periods: [1, 3],
      prices_rub: { 1: 200, 3: 550 },
      prices_stars: { 1: 90, 3: 0 },
      monthly_gb: 500,
      traffic_limit_strategy: "WEEK",
      premium_traffic_limit_strategy: "MONTH",
      topup_packages: { rub: [{ gb: 10, price: 199 }] },
      flexible_traffic_limit: {
        step_gb: 50,
        max_total_gb: 700,
        price_per_step: 99,
        stars_price_per_step: 50,
      },
      premium_flexible_traffic_limit: {
        step_gb: 25,
        max_total_gb: 100,
        price_per_step: 79,
        stars_price_per_step: null,
      },
      checkout_addons: {
        devices: {
          enabled: true,
          max_extra_devices: 4,
          price_per_device: 79,
          stars_price_per_device: 40,
        },
        traffic: { enabled: true },
        premium_traffic: { enabled: false },
      },
      tribute: {
        link: "https://t.me/tribute/app?startapp=pro",
        subscription_id: 101,
        period_ids: { 1: 1001, 3: 1003 },
        traffic_products: {
          10: {
            product_id: 501,
            link: "https://tribute.tg/products/501",
          },
        },
      },
    });
  });

  it("round-trips Tribute digital products for traffic and premium packages", () => {
    const tariff = {
      key: "traffic",
      billing_model: "traffic",
      traffic_packages: { rub: [{ gb: 10.5, price: 200 }] },
      premium_squad_uuids: ["premium"],
      premium_topup_packages: { rub: [{ gb: 5, price: 150 }] },
      tribute: {
        traffic_products: {
          10.5: {
            product_id: 501,
            link: "https://tribute.tg/products/501",
          },
        },
        premium_traffic_products: {
          5: {
            product_id: 502,
            link: "https://t.me/tribute/app?startapp=product-502",
          },
        },
      },
    };

    const draft = draftFromTariff(tariff);

    expect(draft.trafficRows[0]).toMatchObject({
      gb: 10.5,
      tribute_product_id: 501,
      tribute_product_link: "https://tribute.tg/products/501",
    });
    expect(draft.premiumTopupRows[0]).toMatchObject({
      gb: 5,
      tribute_product_id: 502,
      tribute_product_link: "https://t.me/tribute/app?startapp=product-502",
    });
    expect(tariffFromDraft(draft)).toMatchObject({
      tribute: {
        traffic_products: {
          10.5: {
            product_id: 501,
            link: "https://tribute.tg/products/501",
          },
        },
        premium_traffic_products: {
          5: {
            product_id: 502,
            link: "https://t.me/tribute/app?startapp=product-502",
          },
        },
      },
    });
  });

  it("serializes partial Tribute product rows for backend validation", () => {
    expect(
      tributeProductsFromRows(
        [
          { gb: "10.50", tribute_product_id: "501", tribute_product_link: " https://t.me/p " },
          { gb: "20", tribute_product_id: "", tribute_product_link: "" },
          { gb: "30", tribute_product_id: "502", tribute_product_link: "" },
        ],
        "gb"
      )
    ).toEqual({
      10.5: { product_id: 501, link: "https://t.me/p" },
      30: { product_id: 502, link: "" },
    });
  });

  it("builds traffic-model tariffs without period-only fields", () => {
    const draft = {
      ...emptyTariffDraft(),
      key: "traffic",
      nameRu: "Трафик",
      billing_model: "traffic",
      trafficRows: [{ gb: "25", price: "300", stars: "" }],
      conversion_rate_rub_per_gb: "12.5",
      premium_traffic_limit_strategy: "MONTH",
    };

    const tariff = tariffFromDraft(draft);
    expect(tariff).toMatchObject({
      key: "traffic",
      billing_model: "traffic",
      traffic_packages: { rub: [{ gb: 25, price: 300 }] },
      conversion_rate_rub_per_gb: 12.5,
      premium_traffic_limit_strategy: "MONTH",
    });
    expect(tariff).not.toHaveProperty("traffic_limit_strategy");
    expect(tariff).not.toHaveProperty("tribute");
  });

  it("preserves the global fallback for legacy period tariffs without a strategy", () => {
    const draft = draftFromTariff({
      key: "legacy",
      billing_model: "period",
      monthly_gb: 100,
      enabled_periods: [1],
      prices_rub: { 1: 100 },
    });

    expect(draft.traffic_limit_strategy).toBe("");
    expect(draft.premium_traffic_limit_strategy).toBe("");
    expect(tariffFromDraft(draft)).not.toHaveProperty("traffic_limit_strategy");
    expect(tariffFromDraft(draft)).not.toHaveProperty("premium_traffic_limit_strategy");
  });

  it("round-trips the explicit premium unlimited flag", () => {
    const draft = draftFromTariff({
      key: "premium",
      billing_model: "period",
      premium_squad_uuids: ["premium-squad"],
      premium_monthly_gb: 0,
      premium_unlimited: true,
      enabled_periods: [1],
      prices_rub: { 1: 100 },
    });

    expect(draft.premium_unlimited).toBe(true);
    expect(tariffFromDraft(draft)).toMatchObject({
      premium_monthly_gb: 0,
      premium_unlimited: true,
    });
  });

  it("drops premium settings that require a squad when the last squad is removed", () => {
    const draft = draftFromTariff({
      key: "premium",
      billing_model: "period",
      premium_squad_uuids: ["premium-squad"],
      premium_monthly_gb: 50,
      premium_traffic_limit_strategy: "MONTH",
      premium_topup_packages: { rub: [{ gb: 10, price: 99 }] },
      premium_flexible_traffic_limit: {
        step_gb: 10,
        max_total_gb: 100,
        price_per_step: 49,
      },
      premium_topup_always_available: true,
      checkout_addons: { premium_traffic: { enabled: true } },
      tribute: {
        premium_traffic_products: {
          10: {
            product_id: 501,
            link: "https://tribute.tg/products/501",
          },
        },
      },
      monthly_gb: 100,
      enabled_periods: [1],
      prices_rub: { 1: 100 },
    });

    draft.premiumSquadUuids = [];
    const tariff = tariffFromDraft(draft);

    expect(tariff).toMatchObject({
      premium_squad_uuids: [],
      checkout_addons: { premium_traffic: { enabled: false } },
    });
    expect(tariff).not.toHaveProperty("premium_monthly_gb");
    expect(tariff).not.toHaveProperty("premium_topup_packages");
    expect(tariff).not.toHaveProperty("premium_flexible_traffic_limit");
    expect(tariff).not.toHaveProperty("tribute");
  });

  it("normalizes uuid lists from arrays and text", () => {
    expect(normalizeUuidList([" a ", "", "b"])).toEqual(["a", "b"]);
    expect(normalizeUuidList("a\nb, c")).toEqual(["a", "b", "c"]);
  });
});
