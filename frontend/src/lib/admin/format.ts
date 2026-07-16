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

export function fmtDateShort(value: unknown): string {
  if (!value) return "—";
  try {
    return new Date(dateInput(value)).toLocaleDateString("ru-RU");
  } catch {
    return String(value);
  }
}

export function fmtMoney(amount: unknown, currency?: string | null): string {
  const sym = currency === "RUB" ? "₽" : currency || "";
  const num = Number(amount || 0);
  return `${num.toFixed(2)} ${sym}`.trim();
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
  if (typeof status === "string" && status.startsWith("pending")) return "warning";
  return "danger";
}

export function optionLabel(options: readonly SelectOption[], value: string): string {
  return options.find((option) => option.value === value)?.label || value;
}
