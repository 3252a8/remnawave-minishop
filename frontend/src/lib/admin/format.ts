export { structuredCloneSafe } from "../safeClone.js";

type SelectOption = {
  label: string;
  value: string;
};

export type PaymentStatusVariant = "danger" | "success" | "warning";

function dateInput(value: unknown): string | number | Date {
  return value instanceof Date || typeof value === "number" ? value : String(value);
}

export function pretty(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function fmtDate(value: unknown): string {
  if (!value) return "—";
  try {
    return new Date(dateInput(value)).toLocaleString("ru-RU");
  } catch {
    return String(value);
  }
}

/** Date and minutes for timestamps that arrive as ISO strings; unparsable text is kept. */
export function fmtDateTime(value: unknown): string {
  if (!value) return "—";
  const date = new Date(dateInput(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtDateShort(value: unknown): string {
  if (!value) return "—";
  try {
    return new Date(dateInput(value)).toLocaleDateString("ru-RU");
  } catch {
    return String(value);
  }
}

/** Groups thousands with a no-break space; always two decimals, since payments
    are not always whole amounts and columns of money must line up. */
export function fmtAmount(amount: unknown): string {
  const num = Number(amount || 0);
  const fixed = num.toFixed(2);
  const [integer, fraction] = fixed.split(".");
  const sign = integer.startsWith("-") ? "-" : "";
  const digits = sign ? integer.slice(1) : integer;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  return `${sign}${grouped}.${fraction}`;
}

export function fmtMoney(amount: unknown, currency?: string | null): string {
  const code = String(currency || "").trim();
  const sym = code.toUpperCase() === "RUB" ? "₽" : code;
  return `${fmtAmount(amount)}\u00a0${sym}`.trim();
}

export function fmtTrafficBytes(value: unknown): string {
  const bytes = Number(value || 0);
  if (!bytes || bytes <= 0) return "0 GB";
  const gb = bytes / 1073741824;
  const formatted = gb >= 10 ? gb.toFixed(1) : gb.toFixed(2);
  return `${formatted.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1")} GB`;
}

export function trafficPercentValue(used: unknown, limit: unknown): number {
  const usedBytes = Number(used || 0);
  const limitBytes = Number(limit || 0);
  if (!limitBytes || limitBytes <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((usedBytes / limitBytes) * 100)));
}

export function trafficLeftLabel(used: unknown, limit: unknown): string {
  const limitBytes = Number(limit || 0);
  if (!limitBytes || limitBytes <= 0) return "No limit";
  return fmtTrafficBytes(Math.max(0, limitBytes - Number(used || 0)));
}

export function trafficOfLabel(used: unknown, limit: unknown): string {
  const limitBytes = Number(limit || 0);
  if (!limitBytes || limitBytes <= 0) return `${fmtTrafficBytes(used)} / no limit`;
  return `${fmtTrafficBytes(used)} / ${fmtTrafficBytes(limit)}`;
}

export function paymentStatusVariant(status: unknown): PaymentStatusVariant {
  if (status === "succeeded") return "success";
  if (status === "succeeded_pending_finalization" || status === "succeeded_pending_review") {
    return "warning";
  }
  if (typeof status === "string" && status.startsWith("pending")) return "warning";
  return "danger";
}

export function paymentStatusLabel(
  status: unknown,
  at: (key: string, params?: Record<string, unknown>, fallback?: string) => string
): string {
  if (status === "succeeded_pending_finalization" || status === "succeeded_pending_review") {
    return at(`payment_status_${status}`);
  }
  const raw = String(status || "").trim();
  const value = raw.toLowerCase();
  if (!value) return "—";
  if (value === "succeeded" || value === "paid") return at("payment_status_succeeded", {}, "Paid");
  if (value === "refunded") return at("payment_status_refunded", {}, "Refunded");
  if (value === "expired") return at("payment_status_expired", {}, "Expired");
  if (value === "canceled" || value === "cancelled" || value === "pre_cancelled") {
    return at("payment_status_canceled", {}, "Canceled");
  }
  if (value === "failed" || value.startsWith("failed_")) {
    return at("payment_status_failed", {}, "Failed");
  }
  if (value.startsWith("pending")) return at("payment_status_pending", {}, "Pending");
  return raw;
}

export function optionLabel(options: readonly SelectOption[], value: string): string {
  return options.find((option) => option.value === value)?.label || value;
}
