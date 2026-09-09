import { describe, expect, it, vi } from "vitest";

import {
  checkoutPromoAffectsQuotedPlan,
  checkoutPromoBlockVisible,
  checkoutPromoMatchesPlan,
  discountedCheckoutPlan,
  normalizedCheckoutPromoDiscount,
  selectPaymentMethodWithPromoReset,
} from "./checkoutPromoPolicy.js";

describe("checkout promo policy", () => {
  it("selects Tribute before clearing a recurring checkout promo for a fresh quote", () => {
    const calls: string[] = [];

    selectPaymentMethodWithPromoReset(
      "TrIbUtE",
      { sale_mode: "subscription" },
      (methodId) => calls.push(`select:${methodId}`),
      () => calls.push("clear")
    );

    expect(calls).toEqual(["select:TrIbUtE", "clear"]);
  });

  it("keeps the promo when selecting another method or a one-time Tribute checkout", () => {
    const clearCheckoutPromo = vi.fn();
    const selectMethod = vi.fn();

    selectPaymentMethodWithPromoReset(
      "card",
      { sale_mode: "subscription" },
      selectMethod,
      clearCheckoutPromo
    );
    selectPaymentMethodWithPromoReset(
      "tribute",
      { sale_mode: "traffic" },
      selectMethod,
      clearCheckoutPromo
    );

    expect(selectMethod).toHaveBeenCalledTimes(2);
    expect(clearCheckoutPromo).not.toHaveBeenCalled();
  });

  it("allows a reapplied discount promo for a locally priced Tribute subscription", () => {
    expect(checkoutPromoBlockVisible(false, true)).toBe(true);
    expect(checkoutPromoAffectsQuotedPlan(20, true, true)).toBe(true);
  });

  it("still hides checkout promos when the provider manages its own price", () => {
    expect(checkoutPromoBlockVisible(true, true)).toBe(false);
  });

  it("normalizes checkout discounts and applies them to local prices", () => {
    expect(normalizedCheckoutPromoDiscount("SAVE", 125)).toBe(100);
    expect(normalizedCheckoutPromoDiscount("", 20)).toBe(0);
    expect(discountedCheckoutPlan({ price: 190, stars_price: 200 }, 20)).toMatchObject({
      price: 152,
      stars_price: 160,
    });
  });

  it("matches promo scope and thresholds against the selected plan", () => {
    expect(
      checkoutPromoMatchesPlan({ sale_mode: "subscription", months: 3 }, "subscription", 90, null)
    ).toBe(true);
    expect(
      checkoutPromoMatchesPlan({ sale_mode: "subscription", months: 1 }, "subscription", 90, null)
    ).toBe(false);
    expect(
      checkoutPromoMatchesPlan({ sale_mode: "traffic", traffic_gb: 50 }, "traffic", null, 100)
    ).toBe(false);
  });
});
