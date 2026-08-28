type PaymentDescriptionRow = {
  description?: string | null;
  traffic_premium_gb?: number | string | null;
  traffic_regular_gb?: number | string | null;
};

type PaymentPurchase = {
  kind?: string | null;
  amount?: number | string | null;
  unit?: string | null;
  scope?: string | null;
  mode?: string | null;
};

export type PaymentPurchasesRow = PaymentDescriptionRow & {
  purchases?: PaymentPurchase[] | null;
  purchased_hwid_devices?: number | string | null;
};

export type PaymentPurchaseDisplay = {
  key: string;
  label: string;
  mode: "limit" | "topup";
  tone: "regular" | "premium" | "devices" | "other";
};

type PaymentDiscountRow = {
  checkout_discount_amount?: number | string | null;
  promo_discount_percent?: number | string | null;
  currency?: string | null;
};

type MoneyFormatter = (value: number, currency?: string | null) => string;

type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

const PAYMENT_PROVIDER_LOGO_FILES: Record<string, string> = {
  cloudpayments: "cloudpayments.png",
  cryptopay: "cryptopay.png",
  freekassa: "freekassa.png",
  heleket: "heleket.png",
  lava: "lava.png",
  overpay: "overpay.png",
  pally: "pally.png",
  paykilla: "paykilla.png",
  platega: "platega.png",
  severpay: "severpay.png",
  stars: "telegram-stars.png",
  stripe: "stripe.png",
  telegram_stars: "telegram-stars.png",
  tribute: "tribute.png",
  wata: "wata.png",
  yookassa: "yookassa.png",
};

export type PaymentProviderDisplay = {
  label: string;
  logoUrl: string;
  fallbackEmoji: string;
};

export function paymentProviderDisplay(
  provider: string | null | undefined
): PaymentProviderDisplay {
  const rawLabel = String(provider || "").trim();
  const providerKey = rawLabel
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const logoKey = providerKey.startsWith("platega")
    ? "platega"
    : providerKey.startsWith("wata")
      ? "wata"
      : providerKey;
  const logoFile = PAYMENT_PROVIDER_LOGO_FILES[logoKey];

  if (providerKey === "promo") {
    return { label: rawLabel || "promo", logoUrl: "", fallbackEmoji: "🎁" };
  }
  if (providerKey === "partner_balance") {
    return { label: "balance", logoUrl: "", fallbackEmoji: "💸" };
  }
  return {
    label: rawLabel || "—",
    logoUrl: logoFile ? `/provider-logos/${logoFile}` : "",
    fallbackEmoji: "🧾",
  };
}

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

function fallbackPurchases(payment: PaymentPurchasesRow): PaymentPurchase[] {
  const purchases: PaymentPurchase[] = [];
  if (payment.traffic_regular_gb != null) {
    purchases.push({
      kind: "traffic",
      amount: payment.traffic_regular_gb,
      unit: "gb",
      scope: "regular",
      mode: "topup",
    });
  }
  if (payment.traffic_premium_gb != null) {
    purchases.push({
      kind: "traffic",
      amount: payment.traffic_premium_gb,
      unit: "gb",
      scope: "premium",
      mode: "topup",
    });
  }
  if (payment.purchased_hwid_devices != null && Number(payment.purchased_hwid_devices) > 0) {
    purchases.push({
      kind: "hwid_devices",
      amount: payment.purchased_hwid_devices,
      unit: "device",
      mode: "topup",
    });
  }
  return purchases;
}

export function paymentPurchaseDisplay(
  payment: PaymentPurchasesRow,
  at: TranslateFn
): PaymentPurchaseDisplay[] {
  const source = payment.purchases?.length ? payment.purchases : fallbackPurchases(payment);
  return source.flatMap((purchase, index) => {
    const amount = formatGbAmountPlain(purchase.amount);
    if (!amount) return [];
    const kind = String(purchase.kind || "").toLowerCase();
    const scope = String(purchase.scope || "").toLowerCase();
    const mode = String(purchase.mode || "topup").toLowerCase();
    const displayMode: PaymentPurchaseDisplay["mode"] = mode === "limit" ? "limit" : "topup";
    let label: string;
    let tone: PaymentPurchaseDisplay["tone"];

    if (kind === "traffic" && mode === "limit" && scope === "premium") {
      label = at("payments_purchase_premium_limit", { amount }, `Premium limit · ${amount} GB`);
      tone = "premium";
    } else if (kind === "traffic" && mode === "limit") {
      label = at("payments_purchase_regular_limit", { amount }, `Traffic limit · ${amount} GB`);
      tone = "regular";
    } else if (kind === "traffic" && scope === "premium") {
      label = at("payments_purchase_premium_traffic", { amount }, `Premium · +${amount} GB`);
      tone = "premium";
    } else if (kind === "traffic") {
      label = at("payments_purchase_regular_traffic", { amount }, `Traffic · +${amount} GB`);
      tone = "regular";
    } else if (kind === "hwid_devices") {
      label = at("payments_purchase_devices", { amount }, `Devices · +${amount}`);
      tone = "devices";
    } else {
      const unit = String(purchase.unit || "").trim();
      label = at(
        "payments_purchase_other",
        { kind: kind || "other", amount, unit },
        `${kind || "Other"} · ${amount}${unit ? ` ${unit}` : ""}`
      );
      tone = "other";
    }

    return [
      {
        key: `${kind || "other"}-${scope || "all"}-${displayMode}-${index}`,
        label,
        mode: displayMode,
        tone,
      },
    ];
  });
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
