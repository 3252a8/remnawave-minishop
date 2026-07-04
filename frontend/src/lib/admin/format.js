export { structuredCloneSafe } from "../safeClone.js";

export function pretty(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  return String(value);
}

export function fmtDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("ru-RU");
  } catch {
    return String(value);
  }
}

export function fmtDateShort(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString("ru-RU");
  } catch {
    return String(value);
  }
}

export function fmtMoney(amount, currency) {
  const sym = currency === "RUB" ? "₽" : currency || "";
  const num = Number(amount || 0);
  return `${num.toFixed(2)} ${sym}`.trim();
}

export function fmtTrafficBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes || bytes <= 0) return "0 GB";
  const gb = bytes / 1073741824;
  const formatted = gb >= 10 ? gb.toFixed(1) : gb.toFixed(2);
  return `${formatted.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1")} GB`;
}

export function trafficPercentValue(used, limit) {
  const usedBytes = Number(used || 0);
  const limitBytes = Number(limit || 0);
  if (!limitBytes || limitBytes <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((usedBytes / limitBytes) * 100)));
}

export function trafficLeftLabel(used, limit) {
  const limitBytes = Number(limit || 0);
  if (!limitBytes || limitBytes <= 0) return "Без лимита";
  return fmtTrafficBytes(Math.max(0, limitBytes - Number(used || 0)));
}

export function trafficOfLabel(used, limit) {
  const limitBytes = Number(limit || 0);
  if (!limitBytes || limitBytes <= 0) return `${fmtTrafficBytes(used)} / без лимита`;
  return `${fmtTrafficBytes(used)} / ${fmtTrafficBytes(limit)}`;
}

export function paymentStatusVariant(status) {
  if (status === "succeeded") return "success";
  if (typeof status === "string" && status.startsWith("pending")) return "warning";
  return "danger";
}

/**
 * @param {unknown} status
 * @param {((key: string, params?: Record<string, unknown>, fallback?: string) => string) | null} [t]
 */
export function paymentStatusLabel(status, t = null) {
  const raw = String(status || "").trim();
  if (!raw) return "—";
  const normalized = raw.toLowerCase();
  const key = normalized.startsWith("pending")
    ? "pending"
    : normalized.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const fallbacks = {
    succeeded: "Succeeded",
    pending: "Pending",
    failed: "Failed",
    canceled: "Canceled",
    cancelled: "Canceled",
    expired: "Expired",
    waiting_for_capture: "Waiting for capture",
    created: "Created",
    paid: "Paid",
  };
  const fallback = fallbacks[key] || raw;
  return typeof t === "function" ? t(`payment_status_${key}`, {}, fallback) : fallback;
}

export function optionLabel(options, value) {
  return options.find((option) => option.value === value)?.label || value;
}
