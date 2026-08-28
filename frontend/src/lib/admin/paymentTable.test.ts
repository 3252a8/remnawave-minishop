import { describe, expect, it } from "vitest";

import {
  paymentDiscountDisplay,
  paymentProviderDisplay,
  paymentPurchaseDisplay,
} from "./paymentTable";

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

describe("paymentProviderDisplay", () => {
  it("uses dedicated emoji for promo and partner balance payments", () => {
    expect(paymentProviderDisplay("promo")).toEqual({
      label: "promo",
      logoUrl: "",
      fallbackEmoji: "🎁",
    });
    expect(paymentProviderDisplay("partner_balance")).toEqual({
      label: "balance",
      logoUrl: "",
      fallbackEmoji: "💸",
    });
  });

  it("keeps provider logos and uses a receipt for missing or failed logos", () => {
    expect(paymentProviderDisplay("yookassa")).toEqual({
      label: "yookassa",
      logoUrl: "/provider-logos/yookassa.png",
      fallbackEmoji: "🧾",
    });
    expect(paymentProviderDisplay("rollypay_subscription")).toEqual({
      label: "rollypay_subscription",
      logoUrl: "/provider-logos/rollypay.png",
      fallbackEmoji: "🧾",
    });
    expect(paymentProviderDisplay("custom_provider")).toEqual({
      label: "custom_provider",
      logoUrl: "",
      fallbackEmoji: "🧾",
    });
  });
});

describe("paymentPurchaseDisplay", () => {
  const at = (_key: string, _params: Record<string, unknown> = {}, fallback = "") => fallback;

  it("shows renewal checkout add-ons as one compact list", () => {
    const items = paymentPurchaseDisplay(
      {
        purchases: [
          { kind: "traffic", amount: 150, unit: "gb", scope: "regular", mode: "limit" },
          { kind: "traffic", amount: 30, unit: "gb", scope: "premium", mode: "limit" },
          { kind: "hwid_devices", amount: 2, unit: "device", mode: "limit" },
        ],
      },
      at
    );

    expect(items.map((item) => item.label)).toEqual([
      "Traffic limit · 150 GB",
      "Premium limit · 30 GB",
      "Devices · +2",
    ]);
    expect(items.map((item) => item.mode)).toEqual(["limit", "limit", "limit"]);
  });

  it("keeps legacy standalone top-ups visible", () => {
    expect(
      paymentPurchaseDisplay({ traffic_premium_gb: 12.5, purchased_hwid_devices: 1 }, at).map(
        (item) => item.label
      )
    ).toEqual(["Premium · +12.5 GB", "Devices · +1"]);
  });
});
