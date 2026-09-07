export type BalanceUiState = {
  enabled?: boolean | null;
  amount_minor?: number | null;
};

export function shouldShowUserBalance(balance: BalanceUiState): boolean {
  return Boolean(balance.enabled) || Number(balance.amount_minor || 0) > 0;
}
