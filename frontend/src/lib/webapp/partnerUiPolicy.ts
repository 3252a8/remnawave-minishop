export type PartnerBalanceVisibility = {
  open: boolean;
  eligible: boolean;
  currency: string;
  maximumDiscount: number;
};

export type PartnerBalanceLookup = Pick<PartnerBalanceVisibility, "open" | "eligible" | "currency">;

export function partnerBalanceLookupKey({
  open,
  eligible,
  currency,
}: PartnerBalanceLookup): string {
  const normalizedCurrency = String(currency || "").toUpperCase();
  if (!open || !eligible || !normalizedCurrency) return "";
  return normalizedCurrency;
}

export function shouldShowPartnerBalanceDiscount({
  open,
  eligible,
  currency,
  maximumDiscount,
}: PartnerBalanceVisibility): boolean {
  return open && eligible && Boolean(currency) && maximumDiscount > 0;
}

export function partnerLoadingPlaceholder(previewMode: boolean): "dashboard" | "neutral" {
  return previewMode ? "dashboard" : "neutral";
}
