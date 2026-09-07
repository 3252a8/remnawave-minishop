import { describe, expect, it } from "vitest";

import {
  isQaPaymentUrl,
  qaPaymentIdFromSearch,
  qaPaymentStateForStatus,
  stripQaPaymentQuery,
} from "./qaPayment";

describe("QA payment query", () => {
  it("accepts only positive integer payment ids", () => {
    expect(qaPaymentIdFromSearch("?qa_payment_id=42")).toBe(42);
    expect(qaPaymentIdFromSearch("?qa_payment_id=-1")).toBeNull();
    expect(qaPaymentIdFromSearch("?qa_payment_id=4.2")).toBeNull();
  });

  it("maps terminal and pending statuses", () => {
    expect(qaPaymentStateForStatus("pending_qa")).toBe("pending");
    expect(qaPaymentStateForStatus("succeeded")).toBe("success");
    expect(qaPaymentStateForStatus("expired")).toBe("failed");
  });

  it("recognizes the local QA checkout URL", () => {
    expect(isQaPaymentUrl("/?qa_payment_id=42")).toBe(true);
    expect(isQaPaymentUrl("https://payments.example.test/checkout/42")).toBe(false);
  });

  it("removes only the QA payment parameter", () => {
    expect(stripQaPaymentQuery(new URL("https://example.test/?qa_payment_id=7&lang=en#home"))).toBe(
      "/?lang=en#home"
    );
  });
});
