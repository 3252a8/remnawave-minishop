type PaymentDescriptionRow = {
  description?: string | null;
  traffic_premium_gb?: number | string | null;
  traffic_regular_gb?: number | string | null;
};

type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

function formatGbAmountPlain(value: number | string | null | undefined): string {
  if (value == null || value === "") return "";
  const amount = Number(value);
  if (Number.isNaN(amount)) return "";
  if (Math.abs(amount - Math.round(amount)) < 1e-9) return String(Math.round(amount));
  return String(Math.round(amount * 100) / 100);
}

export function formatPaymentTrafficGb(value: number | string | null | undefined): string {
  const amount = formatGbAmountPlain(value);
  return amount ? `${amount} GB` : "—";
}

export function paymentDescriptionDisplay(payment: PaymentDescriptionRow, at: TranslateFn): string {
  const regularGb = payment.traffic_regular_gb;
  const premiumGb = payment.traffic_premium_gb;
  if (regularGb != null && premiumGb == null) {
    const gb = formatGbAmountPlain(regularGb);
    return at(
      "payments_desc_traffic_package_regular",
      { gb },
      `Traffic package ${gb} GB (standard)`
    );
  }
  if (premiumGb != null && regularGb == null) {
    const gb = formatGbAmountPlain(premiumGb);
    return at(
      "payments_desc_traffic_package_premium",
      { gb },
      `Traffic package ${gb} GB (premium)`
    );
  }
  const raw = payment.description && String(payment.description).trim();
  return raw || "—";
}
