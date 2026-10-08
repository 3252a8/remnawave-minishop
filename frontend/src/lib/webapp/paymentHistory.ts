import type { PaymentHistoryResponse } from "./publicApiContracts";
import type { Translate } from "./types";

export type PaymentHistoryPage = Extract<PaymentHistoryResponse, { ok: true }>;
export type PaymentHistoryItem = PaymentHistoryPage["items"][number];

/** Shared payment cells request semantic keys; user copy stays in the webapp scope. */
export function paymentHistoryTranslate(t: Translate): Translate {
  return (key, params, fallback) =>
    t(`wa_payment_history_${key.replace(/^payments_/, "")}`, params, fallback);
}

export function paymentHistoryStatus(
  item: PaymentHistoryItem,
  t: Translate
): {
  label: string;
  hint: string;
  variant: "success" | "outline" | "muted" | "destructive";
} {
  const state = item.history_state;
  return {
    label: t(`wa_payment_history_state_${state}`),
    hint: t(`wa_payment_history_hint_${state}`),
    variant:
      state === "completed"
        ? "success"
        : state === "failed"
          ? "destructive"
          : state === "refunded"
            ? "muted"
            : "outline",
  };
}
