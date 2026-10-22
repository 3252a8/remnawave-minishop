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

function normalizedId(value: unknown): string {
  return String(value || "")
    .trim()
    .toLowerCase();
}

function providerId(method: PaymentMethodView): string {
  return normalizedId(method.provider_id) || normalizedId(method.id);
}

/** Continue within the payment group, without retrying a rejected provider. */
export function nextCheckoutPaymentMethod(
  methods: PaymentMethodView[],
  failedMethods: string[],
  unavailableMethods: string[] = []
): PaymentMethodView | null {
  const lastFailed = failedMethods.at(-1);
  if (!lastFailed) return null;
  const lastFailedIndex = methods.findIndex(
    (method) => normalizedId(method.id) === normalizedId(lastFailed)
  );
  const group = methods[lastFailedIndex]?.group;
  if (!group || !["fiat", "crypto", "stars", "mixed"].includes(group)) return null;
  const start = lastFailedIndex + 1;
  const ordered = [...methods.slice(start), ...methods.slice(0, start)];
  const excluded = new Set([...failedMethods, ...unavailableMethods].map(normalizedId));
  const failedIds = new Set(failedMethods.map(normalizedId));
  // Eligibility changes may hide a rejected method; its unknown provider is unsafe to retry.
  if ([...failedIds].some((id) => !methods.some((method) => normalizedId(method.id) === id)))
    return null;
  const failedProviders = new Set(
    methods.filter((method) => failedIds.has(normalizedId(method.id))).map(providerId)
  );
  return (
    ordered.find(
      (method) =>
        method.id &&
        method.group === group &&
        !method.disabled &&
        !excluded.has(normalizedId(method.id)) &&
        !failedProviders.has(providerId(method))
    ) || null
  );
}
