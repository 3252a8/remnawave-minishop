export type PaymentOutcome = "fulfilled" | "finalizing" | "review" | "failed" | "pending";

export function paymentOutcome(value: unknown): PaymentOutcome {
  const payment = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  const status = String(payment.status || "")
    .trim()
    .toLowerCase();
  if (status === "succeeded_pending_review") return "review";
  if (status === "succeeded_pending_finalization") return "finalizing";
  if (status === "succeeded" || payment.paid === true) return "fulfilled";
  if (
    status === "failed" ||
    status === "canceled" ||
    status === "cancelled" ||
    status.startsWith("failed_")
  ) {
    return "failed";
  }
  return "pending";
}
