import type { PaymentMethodView } from "./types.js";

export function paymentProviderUnavailable(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "error" in error &&
    error.error === "payment_provider_unavailable"
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
