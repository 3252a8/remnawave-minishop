import { describe, expect, it } from "vitest";

import {
  paymentMethodOrderItems,
  reorderVisiblePaymentMethods,
  serializePaymentMethodOrder,
} from "./paymentMethodsOrder";
import type { PaymentMethodOrderOption } from "./stores/settingsStore";

function option(id: string, providerId = id, enabled = true): PaymentMethodOrderOption {
  return {
    id,
    label: id,
    provider_id: providerId,
    provider_label: providerId,
    enabled,
    admin_only: false,
    known: true,
  };
}

describe("paymentMethodsOrder", () => {
  it("expands the legacy Platega slug and appends new provider buttons", () => {
    const options = [
      option("freekassa"),
      option("platega_sbp", "platega"),
      option("platega_card", "platega"),
      option("platega_subscription", "platega"),
      option("stars", "telegram_stars"),
    ];

    expect(paymentMethodOrderItems("stars,platega", options).map((item) => item.id)).toEqual([
      "stars",
      "platega_sbp",
      "platega_card",
      "freekassa",
      "platega_subscription",
    ]);
  });

  it("keeps unknown and duplicate legacy values without duplicating rows", () => {
    const items = paymentMethodOrderItems("custom,stars,CUSTOM", [option("stars")]);

    expect(items.map((item) => item.id)).toEqual(["custom", "stars"]);
    expect(items[0]).toMatchObject({ known: false, enabled: false });
  });

  it("reorders visible buttons while disabled hidden positions stay intact", () => {
    const allItems = [
      option("hidden-a", "a", false),
      option("visible-a"),
      option("hidden-b", "b", false),
      option("visible-b"),
    ];
    const visibleItems = allItems.filter((item) => item.enabled);

    expect(
      reorderVisiblePaymentMethods(allItems, visibleItems, 0, 1).map((item) => item.id)
    ).toEqual(["hidden-a", "visible-b", "hidden-b", "visible-a"]);
  });

  it("serializes a stable comma-separated value for the existing setting contract", () => {
    expect(serializePaymentMethodOrder([option("stars"), option("freekassa")])).toBe(
      "stars,freekassa"
    );
  });
});
