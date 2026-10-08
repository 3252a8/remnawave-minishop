import { describe, expect, it } from "vitest";
import { DATASET } from "./dataset.js";
import { demoPaymentHistoryItems, paymentHistoryDemoResponse } from "./paymentHistory.js";

describe("payment history demo", () => {
  const userId = Number(DATASET.currentUser?.user_id);

  it("uses only the current user's purchases and omits private administrator fields", () => {
    const ownIds = new Set(
      (DATASET.adminPayments || [])
        .filter((item) => Number(item.user_id) === userId)
        .map((item) => item.payment_id)
    );
    const items = demoPaymentHistoryItems(userId);
    expect(items.length).toBeGreaterThan(10);
    expect(items.every((item) => ownIds.has(item.payment_id))).toBe(true);
    for (const item of items) {
      expect(item).not.toHaveProperty("user_id");
      expect(item).not.toHaveProperty("provider_payment_id");
      expect(item).not.toHaveProperty("idempotence_key");
      expect(item.status).not.toBe("canceled");
      if (item.history_state === "awaiting_payment")
        expect(item.checkout_url).toBe("https://example.com/checkout/mock-payment-history");
      else expect(item.checkout_url).toBeNull();
    }
    expect(new Set(items.map((item) => item.history_state))).toEqual(
      new Set([
        "processing",
        "crediting",
        "review",
        "awaiting_payment",
        "refunded",
        "failed",
        "completed",
      ])
    );
    expect(demoPaymentHistoryItems(-999999)).toEqual([]);
  });

  it("paginates and exposes realistic empty and failed previews", () => {
    const first = paymentHistoryDemoResponse("/payments/history?limit=10&offset=0");
    const second = paymentHistoryDemoResponse("/payments/history?limit=10&offset=10");
    if (!first?.ok || !second?.ok) throw new Error("Expected a payment history page");
    expect(first.items).toHaveLength(10);
    expect(second.items).toHaveLength(Math.min(10, first.total - 10));
    expect(first.total).toBe(second.total);
    expect(second.offset).toBe(10);
    expect(
      first.items.some((item) => second.items.some((other) => item.payment_id === other.payment_id))
    ).toBe(false);
    expect(paymentHistoryDemoResponse("/payments/history", "payment-history-empty")).toMatchObject({
      ok: true,
      items: [],
      total: 0,
    });
    expect(paymentHistoryDemoResponse("/payments/history", "payment-history-error")).toEqual({
      ok: false,
      error: "payment_history_unavailable",
    });
  });
});
