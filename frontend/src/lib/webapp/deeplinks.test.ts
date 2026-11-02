import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildCheckoutUrl,
  buildCheckoutMiniAppUrl,
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
  it("round-trips a private Mini App link through every launch parameter", () => {
    const accessCode = "ab".repeat(16);
    const url = buildCheckoutMiniAppUrl({ botUsername: "@shop_bot", accessCode });
    const payload = new URL(url).searchParams.get("startapp")!;
    expect(url).toBe(`https://t.me/shop_bot?startapp=checkout_${accessCode}`);
    for (const key of ["startapp", "start_param", "tgWebAppStartParam"]) {
      expect(parseCheckoutDeeplink({ search: `?${key}=${payload}` })).toMatchObject({
        accessCode,
        plan: "",
      });
    }
    expect(parseCheckoutDeeplink({ telegramStartParam: payload.toUpperCase() })).toEqual({
      accessCode,
      plan: "",
      months: null,
      addons: { deviceTotal: null, regularLimitGb: null, premiumLimitGb: null },
    });
  });

  it("builds public Mini App links and rejects unavailable or malformed inputs", () => {
    expect(buildCheckoutMiniAppUrl({ botUsername: "shop_bot", plan: "standard" })).toBe(
      "https://t.me/shop_bot?startapp=plan_standard"
    );
    expect(buildCheckoutMiniAppUrl({ botUsername: "", accessCode: "ab".repeat(16) })).toBe("");
    expect(
      buildCheckoutMiniAppUrl({ botUsername: "shop_bot", accessCode: "bad", plan: "public" })
    ).toBe("");
    expect(buildCheckoutMiniAppUrl({ botUsername: "shop_bot", plan: "a__months_3" })).toBe("");
    expect(buildCheckoutMiniAppUrl({ botUsername: "shop_bot" })).toBe("");
    for (const payload of [
      "checkout_bad",
      `checkout_${"a".repeat(31)}`,
      `checkout_${"a".repeat(33)}`,
    ]) {
      expect(parseCheckoutDeeplink({ telegramStartParam: payload })).toBeNull();
    }
  });

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

  it("builds and parses a private hex-path checkout link", () => {
    const accessCode = "ab".repeat(16);
    expect(
      buildCheckoutUrl({
        accessCode: accessCode.toUpperCase(),
        origin: "https://shop.example/",
        plan: "private",
        routePrefix: "/minishop",
      })
    ).toBe(`https://shop.example/minishop/checkout/${accessCode}`);
    expect(
      parseCheckoutDeeplink({ pathname: `/minishop/checkout/${accessCode.toUpperCase()}` })
    ).toEqual({
      accessCode,
      plan: "",
      months: null,
      addons: { deviceTotal: null, regularLimitGb: null, premiumLimitGb: null },
    });
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
      accessCode: "",
      plan: "standard",
      months: 3,
      addons: { deviceTotal: 5, regularLimitGb: 200, premiumLimitGb: 50 },
    });
  });

  it("supports a hash checkout route with an empty outer plan marker", () => {
    expect(
      parseCheckoutDeeplink({ pathname: "/", search: "?plan", hash: "#/checkout?plan=8" })
    ).toEqual({
      accessCode: "",
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
      accessCode: "",
      plan: "standard",
      months: 6,
      addons: { deviceTotal: 4, regularLimitGb: 300, premiumLimitGb: 100 },
    });
  });
});
