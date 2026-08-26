export type PartnerBalanceVisibility = {
  open: boolean;
  eligible: boolean;
  currency: string;
  maximumDiscount: number;
};

export type PartnerBalanceLookup = Pick<PartnerBalanceVisibility, "open" | "eligible" | "currency">;

export type PartnerBalancePlaceholderVisibility = PartnerBalanceLookup & {
  loading: boolean;
  requestKey: string;
};

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

export function shouldShowPartnerBalancePlaceholder({
  open,
  eligible,
  currency,
  loading,
  requestKey,
}: PartnerBalancePlaceholderVisibility): boolean {
  const lookupKey = partnerBalanceLookupKey({ open, eligible, currency });
  return Boolean(lookupKey) && (loading || requestKey !== lookupKey);
}

export function partnerLoadingPlaceholder(previewMode: boolean): "dashboard" | "neutral" {
  return previewMode ? "dashboard" : "neutral";
}
