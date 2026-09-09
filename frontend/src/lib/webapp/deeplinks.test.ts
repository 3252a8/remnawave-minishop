import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildCheckoutUrl,
  isPlansRoute,
  parseCheckoutDeeplink,
  readCheckoutPromoDeeplink,
} from "./deeplinks.js";

function withSearch(search: string) {
  vi.stubGlobal("window", { location: { search } });
}

describe("checkout promo deeplinks", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads a prefixed code out of every start parameter", () => {
    for (const key of ["startapp", "start_param", "tgWebAppStartParam"]) {
      withSearch(`?${key}=promo_SAVE10`);
      expect(readCheckoutPromoDeeplink()).toBe("SAVE10");
    }
  });

  it("still accepts a bare code from the explicit promo parameters", () => {
    withSearch("?promo_code=SAVE10");
    expect(readCheckoutPromoDeeplink()).toBe("SAVE10");
    withSearch("?promo=SAVE10");
    expect(readCheckoutPromoDeeplink()).toBe("SAVE10");
  });

  it("never mistakes an app route in a start parameter for a code", () => {
    // These payloads name where to go. Reading one as a promo code opened
    // checkout and complained the code was invalid instead of navigating.
    for (const payload of ["plans", "invite", "support", "ticket_7", "admin_user_5"]) {
      withSearch(`?startapp=${payload}`);
      expect(readCheckoutPromoDeeplink()).toBe("");
    }
  });
});

describe("checkout route", () => {
  it("builds a public checkout link for a tariff", () => {
    expect(
      buildCheckoutUrl({ origin: "https://shop.example", plan: "standard", routePrefix: "" })
    ).toBe("https://shop.example/checkout?plan=standard");
    expect(
      buildCheckoutUrl({
        origin: "https://shop.example/",
        plan: "pro plus",
        routePrefix: "/minishop",
      })
    ).toBe("https://shop.example/minishop/checkout?plan=pro+plus");
  });

  it("does not build a checkout link without an origin or tariff key", () => {
    expect(buildCheckoutUrl({ origin: "", plan: "standard" })).toBe("");
    expect(buildCheckoutUrl({ origin: "https://shop.example", plan: "" })).toBe("");
  });

  it("recognises the route with and without a mount prefix", () => {
    expect(isPlansRoute("/plans")).toBe(true);
    expect(isPlansRoute("/plans/")).toBe(true);
    expect(isPlansRoute("/demo/runtime/plans", "/demo/runtime")).toBe(true);
    expect(isPlansRoute("/home")).toBe(false);
    expect(isPlansRoute("/plans/extra")).toBe(false);
  });

  it("reads a plan and flexible limits from a web checkout link", () => {
    expect(
      parseCheckoutDeeplink({
        pathname: "/checkout",
        search: "?plan=standard&months=3&devices=5&traffic=200&premium=50",
      })
    ).toEqual({
      plan: "standard",
      months: 3,
      addons: { deviceTotal: 5, regularLimitGb: 200, premiumLimitGb: 50 },
    });
  });

  it("supports a hash checkout route with an empty outer plan marker", () => {
    expect(
      parseCheckoutDeeplink({ pathname: "/", search: "?plan", hash: "#/checkout?plan=8" })
    ).toEqual({
      plan: "8",
      months: null,
      addons: { deviceTotal: null, regularLimitGb: null, premiumLimitGb: null },
    });
  });

  it("reads a Telegram plan payload with checkout options", () => {
    expect(
      parseCheckoutDeeplink({
        telegramStartParam: "plan_standard__months_6__devices_4__traffic_300__premium_100",
      })
    ).toEqual({
      plan: "standard",
      months: 6,
      addons: { deviceTotal: 4, regularLimitGb: 300, premiumLimitGb: 100 },
    });
  });
});
