import { describe, expect, it } from "vitest";
import { nextCheckoutPaymentMethod, paymentProviderUnavailable } from "./paymentFallback.js";
import { methodsForPlan } from "./tariffs.js";

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
});
