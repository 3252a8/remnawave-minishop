import { unitPluralBucket } from "./plurals.js";

export function legacyMonthsToDays(value: unknown): number | null {
  const months = Number(value);
  if (typeof value === "boolean" || !Number.isSafeInteger(months) || months <= 0) return null;
  return Math.floor(months / 12) * 365 + (months % 12) * 30;
}

export function billingDurationDays(
  plan: { duration_days?: unknown; months?: unknown } | null | undefined
): number | null {
  if (plan?.duration_days == null) return legacyMonthsToDays(plan?.months);
  const days = Number(plan.duration_days);
  return typeof plan.duration_days !== "boolean" && Number.isSafeInteger(days) && days > 0
    ? days
    : null;
}

export function durationParts(
  value: unknown
): { count: number; unit: "day" | "month" | "year" } | null {
  const days = Number(value);
  if (typeof value === "boolean" || !Number.isSafeInteger(days) || days <= 0) return null;
  if (days % 365 === 0) return { count: days / 365, unit: "year" };
  if (days % 30 === 0) return { count: days / 30, unit: "month" };
  return { count: days, unit: "day" };
}

export function formatDurationDays(
  value: unknown,
  translate: (key: string) => string,
  language: string
): string {
  const parts = durationParts(value);
  if (!parts) return "";
  const bucket = unitPluralBucket(parts.count, language);
  return `${parts.count} ${translate(`wa_sub_term_${parts.unit}_${bucket}`)}`;
}

export function daysToLegacyMonths(value: unknown): number | null {
  const days = Number(value);
  if (!durationParts(value)) return null;
  const years = Math.floor(days / 365);
  const remainder = days % 365;
  return remainder % 30 === 0 && remainder / 30 < 12 ? years * 12 + remainder / 30 : null;
}
