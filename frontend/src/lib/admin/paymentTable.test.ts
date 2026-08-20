import { describe, expect, it } from "vitest";

import { paymentDiscountDisplay } from "./paymentTable";

const money = (value: number, currency?: string | null): string =>
  `${value.toFixed(2)} ${currency || ""}`.trim();

describe("paymentDiscountDisplay", () => {
  it("shows the frozen discount amount and promo percentage", () => {
    expect(
      paymentDiscountDisplay(
        { checkout_discount_amount: 250, promo_discount_percent: 25, currency: "RUB" },
        money
      )
    ).toBe("−250.00 RUB (25%)");
  });

  it("shows a percentage when no absolute discount was stored", () => {
    expect(paymentDiscountDisplay({ promo_discount_percent: 12.5 }, money)).toBe("−12.5%");
  });

  it("uses an empty marker when no discount was applied", () => {
    expect(paymentDiscountDisplay({}, money)).toBe("—");
  });
});
