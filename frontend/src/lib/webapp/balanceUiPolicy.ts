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
