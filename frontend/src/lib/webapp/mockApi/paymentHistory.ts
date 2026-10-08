import { DEV_MOCK } from "../previewMock.js";
import type { PaymentHistoryItem, PaymentHistoryPage } from "../paymentHistory.js";
import { DATASET, type DemoRecord } from "./dataset.js";

function numberOrNull(value: unknown): number | null {
  return value == null ? null : Number(value);
}

function textOrNull(value: unknown): string | null {
  return value == null ? null : String(value);
}

/** Reuse the current account's payments without leaking administrator-only fields. */
export function demoPaymentHistoryItems(userId: number): PaymentHistoryItem[] {
  return (DATASET.adminPayments || [])
    .filter((payment) => Number(payment.user_id) === userId && payment.status === "succeeded")
    .sort(
      (a, b) =>
        String(b.created_at).localeCompare(String(a.created_at)) ||
        Number(b.payment_id) - Number(a.payment_id)
    )
    .map((payment, index) => {
      const historyStates = [
        "processing",
        "crediting",
        "review",
        "awaiting_payment",
        "refunded",
        "failed",
      ] as const;
      const statuses = [
        "waiting_for_capture",
        "succeeded_pending_finalization",
        "succeeded_pending_review",
        "pending",
        "refunded",
        "failed",
      ];
      const historyState = historyStates[index] || "completed";
      const item: PaymentHistoryItem = {
        payment_id: Number(payment.payment_id),
        provider: textOrNull(payment.provider),
        amount: Number(payment.amount),
        currency: textOrNull(payment.currency),
        status: statuses[index] || "succeeded",
        history_state: historyState,
        checkout_url:
          historyState === "awaiting_payment"
            ? "https://example.com/checkout/mock-payment-history"
            : null,
        description: textOrNull(payment.description),
        created_at: textOrNull(payment.created_at),
        traffic_regular_gb: numberOrNull(payment.traffic_regular_gb),
        traffic_premium_gb: numberOrNull(payment.traffic_premium_gb),
        checkout_discount_amount: index === 0 ? 90 : numberOrNull(payment.checkout_discount_amount),
        subscription_duration_months: numberOrNull(payment.subscription_duration_months),
        subscription_duration_days: numberOrNull(payment.subscription_duration_days),
        period_semantics: textOrNull(payment.period_semantics),
        sale_mode: textOrNull(payment.sale_mode),
        purchased_gb: numberOrNull(payment.purchased_gb),
        purchased_hwid_devices: numberOrNull(payment.purchased_hwid_devices),
        purchases:
          index === 0
            ? [
                { kind: "traffic", amount: 150, unit: "gb", scope: "regular", mode: "limit" },
                { kind: "traffic", amount: 50, unit: "gb", scope: "premium", mode: "limit" },
                { kind: "hwid_devices", amount: 2, unit: "device", scope: null, mode: "limit" },
              ]
            : [],
        funding_source: String(payment.funding_source || "external"),
      };
      return item;
    });
}

export function paymentHistoryDemoResponse(
  path: string,
  scenario = typeof window === "undefined"
    ? ""
    : new URLSearchParams(window.location.search).get("mock") || ""
): PaymentHistoryPage | { ok: false; error: string } | undefined {
  if (path.split("?")[0] !== "/payments/history") return undefined;
  if (scenario === "payment-history-error")
    return { ok: false, error: "payment_history_unavailable" };
  const params = new URLSearchParams(path.split("?")[1] || "");
  const limit = Math.min(100, Math.max(1, Math.floor(Number(params.get("limit") || 10))));
  const offset = Math.max(0, Math.floor(Number(params.get("offset") || 0)));
  const user = (DEV_MOCK.data.user || {}) as DemoRecord;
  const userId = Number(user.user_id ?? user.id ?? DATASET.currentUser?.user_id);
  const source = scenario === "payment-history-empty" ? [] : demoPaymentHistoryItems(userId);
  return {
    ok: true,
    items: source.slice(offset, offset + limit),
    total: source.length,
    limit,
    offset,
  };
}
