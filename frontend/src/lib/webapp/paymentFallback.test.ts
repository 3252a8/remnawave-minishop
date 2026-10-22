import { afterEach, describe, expect, it, vi } from "vitest";
import { nextCheckoutPaymentMethod, paymentProviderUnavailable } from "./paymentFallback.js";
import { createApiClient } from "./publicApi.js";
import { methodsForPlan } from "./tariffs.js";

afterEach(() => vi.unstubAllGlobals());

describe("checkout payment fallback", () => {
  const methods = [{ id: "before" }, { id: "wata" }, { id: "card" }, { id: "crypto" }];

  it("continues in configured order, wraps and excludes the entire failed chain", () => {
    expect(nextCheckoutPaymentMethod(methods, ["wata"])?.id).toBe("card");
    expect(nextCheckoutPaymentMethod(methods, ["wata", "card"])?.id).toBe("crypto");
    expect(nextCheckoutPaymentMethod(methods, ["wata", "card", "crypto"])?.id).toBe("before");
    expect(nextCheckoutPaymentMethod(methods, ["wata", "card", "crypto", "before"])).toBeNull();
  });

  it("respects plan visibility, minimums, balance compatibility and add-on exclusions", () => {
    const eligible = methodsForPlan(
      [
        { id: "wata" },
        { id: "hidden" },
        { id: "expensive", min_amount: 500, min_currency: "RUB" },
        { id: "subscription", balance_supported: false },
        { id: "no-addons" },
        { id: "card" },
      ],
      {
        price: 290,
        currency: "RUB",
        available_payment_method_ids: ["wata", "expensive", "subscription", "no-addons", "card"],
      },
      "user"
    );
    expect(nextCheckoutPaymentMethod(eligible, ["wata"], ["no-addons"])?.id).toBe("card");
    expect(nextCheckoutPaymentMethod([], ["wata"])).toBeNull();
    expect(nextCheckoutPaymentMethod(methods, [])).toBeNull();
  });

  it("accepts only the definitive provider failure code", () => {
    expect(paymentProviderUnavailable({ error: "payment_provider_unavailable" })).toBe(true);
    for (const error of [
      null,
      new Error("offline"),
      { error: "payment_failed" },
      { error: "invalid_plan" },
      { message: "payment_provider_unavailable" },
    ]) {
      expect(paymentProviderUnavailable(error)).toBe(false);
    }
  });

  it("recognizes the provider rejection wrapped by the real HTTP client", async () => {
    const payload = { ok: false, error: "payment_provider_unavailable" };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json(payload, { status: 502 }))
    );
    const client = createApiClient();
    const error = await client.api("/payments", { method: "POST" }).catch((cause) => cause);

    expect(error).toMatchObject({ message: "service_unavailable", status: 502, payload });
    expect(paymentProviderUnavailable(error)).toBe(true);
  });

  it.each([
    { status: 502, payload: { ok: false, error: "payment_failed" } },
    { status: 502, payload: { ok: true, error: "payment_provider_unavailable" } },
    { status: 502, payload: { error: "payment_provider_unavailable" } },
    { status: 503, payload: { ok: false, error: "payment_provider_unavailable" } },
    { status: 429, payload: { ok: false, error: "payment_provider_unavailable" } },
    { status: 502, payload: null },
  ])("does not treat an unrelated HTTP failure as a provider rejection (%o)", (error) => {
    expect(paymentProviderUnavailable(Object.assign(new Error("service_unavailable"), error))).toBe(
      false
    );
  });
});
