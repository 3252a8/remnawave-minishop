import { describe, expect, it, vi } from "vitest";

import {
  checkoutPromoAffectsQuotedPlan,
  checkoutPromoBlockVisible,
  checkoutPromoMatchesPlan,
  checkoutPromoPaymentMethods,
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
    expect(checkoutPromoBlockVisible(true, true, true)).toBe(true);
    expect(checkoutPromoBlockVisible(true, false, true)).toBe(false);
  });

  it("keeps code-compatible methods in configured order and respects plan availability", () => {
    const methods = [
      { id: "wata_subscription" },
      { id: "rollypay_subscription" },
      { id: "platega_subscription" },
      { id: "tribute" },
      { id: "external", price_managed_externally: true },
      { id: "disabled", disabled: true },
      { id: "minimum", minimum_amount: 200, min_currency: "RUB" },
      { id: "card" },
      { id: "stars" },
    ];
    const compatible = checkoutPromoPaymentMethods(methods, {
      sale_mode: "subscription",
      price: 100,
      currency: "RUB",
      available_payment_method_ids: methods.map((method) => method.id),
    });

    expect(compatible.map((method) => method.id)).toEqual(["disabled", "minimum", "card", "stars"]);
    expect(compatible.filter((method) => !method.disabled).map((method) => method.id)).toEqual([
      "card",
      "stars",
    ]);
    expect(
      checkoutPromoPaymentMethods(methods, {
        available_payment_method_ids: ["stars"],
        externally_managed_price_method_ids: ["card"],
      }).filter((method) => !method.disabled)
    ).toEqual([{ id: "stars", disabled: false }]);
  });

  it("keeps one-time locally priced Tribute purchases compatible", () => {
    expect(checkoutPromoPaymentMethods([{ id: "tribute" }], { sale_mode: "traffic" })).toEqual([
      { id: "tribute", disabled: false },
    ]);
    expect(checkoutPromoPaymentMethods([{ id: "WATA_SUBSCRIPTION" }], null)).toEqual([]);
  });

  it("preserves a supported local Tribute quote without admitting fixed recurring methods", () => {
    expect(
      checkoutPromoPaymentMethods(
        [{ id: "tribute" }, { id: "wata_subscription" }],
        { sale_mode: "subscription" },
        true
      )
    ).toEqual([{ id: "tribute", disabled: false }]);
    expect(
      checkoutPromoPaymentMethods(
        [{ id: "tribute", price_managed_externally: true }],
        { sale_mode: "subscription" },
        true
      )
    ).toEqual([]);
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
