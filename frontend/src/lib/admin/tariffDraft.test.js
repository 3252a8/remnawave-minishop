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
} from "./tariffDraft.js";

describe("tariffDraft", () => {
  it("normalizes currency aliases and clones catalog defaults", () => {
    expect(emptyTariffDraft().defaultCurrency).toBe("cny");
    expect(normalizeCurrencyKey("¥")).toBe("cny");
    expect(normalizeCurrencyKey("RMB")).toBe("cny");
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

  it("round-trips period tariffs through draft form", () => {
    const tariff = {
      key: "pro",
      names: { ru: "Про" },
      enabled_periods: [1, 3],
      prices_rub: { 1: 200, 3: 550 },
      prices_stars: { 1: 90 },
      referral_bonus_days_inviter: { 1: 3 },
      referral_bonus_days_referee: { 1: 1 },
      squad_uuids: ["a", "b"],
      monthly_gb: 500,
      topup_packages: { rub: [{ gb: 10, price: 199 }] },
    };

    const draft = draftFromTariff(tariff, "rub");
    expect(draft.key).toBe("pro");
    expect(draft.periodRows).toEqual([
      { months: 1, rub: 200, stars: 90, referral_inviter: 3, referral_referee: 1 },
      { months: 3, rub: 550, stars: "", referral_inviter: "", referral_referee: "" },
    ]);

    draft.squadUuids = " a\nb, c ";
    draft.periodRows.push({ months: 3, rub: 600, stars: 10 });
    expect(tariffFromDraft(draft)).toMatchObject({
      key: "pro",
      names: { ru: "Про" },
      squad_uuids: ["a", "b", "c"],
      enabled_periods: [1, 3],
      prices_rub: { 1: 200, 3: 550 },
      prices_stars: { 1: 90, 3: 0 },
      monthly_gb: 500,
      topup_packages: { rub: [{ gb: 10, price: 199 }] },
    });
  });

  it("builds traffic-model tariffs without period-only fields", () => {
    const draft = {
      ...emptyTariffDraft(),
      key: "traffic",
      nameRu: "Трафик",
      billing_model: "traffic",
      defaultCurrency: "rub",
      trafficRows: [{ gb: "25", price: "300", stars: "" }],
      conversion_rate_rub_per_gb: "12.5",
    };

    expect(tariffFromDraft(draft)).toMatchObject({
      key: "traffic",
      billing_model: "traffic",
      traffic_packages: { rub: [{ gb: 25, price: 300 }] },
      conversion_rate_rub_per_gb: 12.5,
    });
  });

  it("normalizes uuid lists from arrays and text", () => {
    expect(normalizeUuidList([" a ", "", "b"])).toEqual(["a", "b"]);
    expect(normalizeUuidList("a\nb, c")).toEqual(["a", "b", "c"]);
  });
});
