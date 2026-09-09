import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./publicApi.js";
import { loadPartnerBalanceSnapshot, peekPartnerBalanceSnapshot } from "./partnerBalanceLookup.js";

function apiWithOverview(overview: unknown): ApiClient["api"] {
  return vi.fn().mockResolvedValue(overview) as unknown as ApiClient["api"];
}

describe("partner balance lookup", () => {
  it("caches a confirmed positive balance for checkout rendering", async () => {
    const api = apiWithOverview({
      balance_payment_enabled: true,
      profile: { status: "active" },
      balances: [{ currency: "RUB", currency_scale: 2, available_minor: 57_950 }],
    });

    await expect(loadPartnerBalanceSnapshot(api, "rub")).resolves.toEqual({
      available: 579.5,
      scale: 2,
    });
    expect(peekPartnerBalanceSnapshot(api, "RUB")).toEqual({ available: 579.5, scale: 2 });
  });

  it("caches an unavailable balance without exposing a checkout option", async () => {
    const api = apiWithOverview({
      balance_payment_enabled: false,
      profile: { status: "active" },
      balances: [{ currency: "RUB", currency_scale: 2, available_minor: 57_950 }],
    });

    await expect(loadPartnerBalanceSnapshot(api, "RUB")).resolves.toEqual({
      available: 0,
      scale: 2,
    });
    expect(peekPartnerBalanceSnapshot(api, "RUB")?.available).toBe(0);
  });

  it("deduplicates concurrent preload and checkout requests", async () => {
    const api = apiWithOverview({
      balance_payment_enabled: true,
      profile: { status: "active" },
      balances: [{ currency: "RUB", currency_scale: 2, available_minor: 12_000 }],
    });

    const [first, second] = await Promise.all([
      loadPartnerBalanceSnapshot(api, "RUB"),
      loadPartnerBalanceSnapshot(api, "rub"),
    ]);

    expect(first).toEqual(second);
    expect(api).toHaveBeenCalledTimes(1);
  });
});
