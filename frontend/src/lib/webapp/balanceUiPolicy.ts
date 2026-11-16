import type { BalanceResponse } from "./publicApi.js";

export type BalanceUiState = {
  enabled?: boolean | null;
  amount_minor?: number | null;
};

export function decimalTopupAmount(value: string, scale: number): number | null {
  const precision = Math.max(0, Math.min(3, Math.trunc(scale)));
  const pattern = precision ? new RegExp(`^\\d+(?:[.,]\\d{1,${precision}})?$`) : /^\d+$/;
  if (!pattern.test(value)) return null;
  const amount = Number(value.replace(",", "."));
  return Number.isFinite(amount) && amount > 0 ? amount : null;
}

export function shouldShowUserBalance(balance: BalanceUiState): boolean {
  return Boolean(balance.enabled) || Number(balance.amount_minor || 0) > 0;
}

export function balanceRecurringEligible(
  plan: { sale_mode?: string | null } | null | undefined,
  gift = false
): boolean {
  const saleMode = String(plan?.sale_mode || "subscription")
    .split("@", 1)[0]
    .toLowerCase();
  return Boolean(plan) && !gift && saleMode === "subscription";
}

export function balanceSourceSupportsRenewal(
  response: BalanceResponse | null | undefined,
  source: string | null,
  plan: Parameters<typeof balanceRecurringEligible>[0],
  gift: boolean
): boolean {
  return Boolean(
    balanceRecurringEligible(plan, gift) &&
    response?.recurring_enabled &&
    response.sources.some((entry) => entry.id === source && entry.recurring_available)
  );
}

const SUBSCRIPTION_ONLY_METHODS = new Set([
  "platega_subscription",
  "rollypay_subscription",
  "wata_subscription",
  "tribute",
]);

export function availableBalanceTopupMethods<
  T extends { id?: string | number | null; price_managed_externally?: boolean | null },
>(methods: T[]): T[] {
  return methods.filter((method) => {
    const id = String(method.id || "").toLowerCase();
    return (
      !["stars", "partner_balance", "user_balance"].includes(id) &&
      !SUBSCRIPTION_ONLY_METHODS.has(id) &&
      !method.price_managed_externally
    );
  });
}
