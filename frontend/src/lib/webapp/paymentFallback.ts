import type { PaymentMethodView } from "./types.js";

export function paymentProviderUnavailable(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false;
  if ("error" in error && error.error === "payment_provider_unavailable") return true;
  // The HTTP client retains a 502 API envelope inside its service error.
  if (!("status" in error) || error.status !== 502 || !("payload" in error)) return false;
  const payload = error.payload;
  return (
    typeof payload === "object" &&
    payload !== null &&
    "ok" in payload &&
    payload.ok === false &&
    "error" in payload &&
    payload.error === "payment_provider_unavailable"
  );
}

/** Keep the configured order, continuing after the rejected method and wrapping once. */
export function nextCheckoutPaymentMethod(
  methods: PaymentMethodView[],
  failedMethods: string[],
  unavailableMethods: string[] = []
): PaymentMethodView | null {
  const lastFailed = failedMethods.at(-1);
  if (!lastFailed) return null;
  const start = methods.findIndex((method) => method.id === lastFailed) + 1;
  const ordered = [...methods.slice(start), ...methods.slice(0, start)];
  const excluded = new Set([...failedMethods, ...unavailableMethods].map((id) => id.toLowerCase()));
  return (
    ordered.find(
      (method) => method.id && !method.disabled && !excluded.has(String(method.id).toLowerCase())
    ) || null
  );
}
