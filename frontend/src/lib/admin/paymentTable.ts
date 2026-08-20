type PaymentDescriptionRow = {
  description?: string | null;
  traffic_premium_gb?: number | string | null;
  traffic_regular_gb?: number | string | null;
};

type PaymentDiscountRow = {
  checkout_discount_amount?: number | string | null;
  promo_discount_percent?: number | string | null;
  currency?: string | null;
};

type MoneyFormatter = (value: number, currency?: string | null) => string;

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

export function paymentDiscountDisplay(
  payment: PaymentDiscountRow,
  fmtMoney: MoneyFormatter
): string {
  const amount = Number(payment.checkout_discount_amount || 0);
  const percent = Number(payment.promo_discount_percent || 0);
  const percentLabel = percent > 0 ? `${Math.round(percent * 100) / 100}%` : "";
  if (amount > 0) {
    const amountLabel = `−${fmtMoney(amount, payment.currency)}`;
    return percentLabel ? `${amountLabel} (${percentLabel})` : amountLabel;
  }
  return percentLabel ? `−${percentLabel}` : "—";
}
