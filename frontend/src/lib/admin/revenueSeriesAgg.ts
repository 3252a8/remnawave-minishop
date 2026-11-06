export type RevenuePoint = { date: string; amount: number; fees?: number };

export const REVENUE_PRESETS = [7, 14, 30, 90, 180, 365, 730, 1095, "all"] as const;
export const REVENUE_GRANULARITIES = ["day", "week", "month", "year"] as const;

export type RevenuePreset = (typeof REVENUE_PRESETS)[number];
export type RevenueGranularity = (typeof REVENUE_GRANULARITIES)[number];

export function isRevenuePreset(value: unknown): value is RevenuePreset {
  if (value === "all") return true;
  const days = Number(value);
  return REVENUE_PRESETS.some((preset) => preset === days);
}

export function isRevenueGranularity(value: unknown): value is RevenueGranularity {
  return REVENUE_GRANULARITIES.includes(value as RevenueGranularity);
}

/** UTC ms at noon (stable day bucket) for a YYYY-MM-DD or ISO datetime string. */
function noonUtcMs(iso: string): number {
  const s = String(iso || "");
  const t = Date.parse(s.includes("T") ? s : `${s}T12:00:00Z`);
  return Number.isFinite(t) ? t : 0;
}

/** YYYY-MM-DD UTC for the given ms timestamp. */
function isoUtcDateFromMs(t: number): string {
  const d = new Date(t);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Monday 00:00 UTC for the week containing `iso` (date-only). */
export function utcWeekStartMs(iso: string): number {
  const d = new Date(iso.includes("T") ? iso : `${iso}T12:00:00Z`);
  const dow = d.getUTCDay();
  const offset = (dow + 6) % 7;
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - offset);
}

/** First day of month (UTC) containing `iso`. */
export function utcMonthStartMs(iso: string): number {
  const d = new Date(iso.includes("T") ? iso : `${iso}T12:00:00Z`);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
}

/** First day of year (UTC) containing `iso`. */
export function utcYearStartMs(iso: string): number {
  const d = new Date(iso.includes("T") ? iso : `${iso}T12:00:00Z`);
  return Date.UTC(d.getUTCFullYear(), 0, 1);
}

/** `points` sorted ascending by `date`; `fromIso` / `toIso` are YYYY-MM-DD inclusive. */
export function filterDailyByIsoRange(
  points: RevenuePoint[],
  fromIso: string,
  toIso: string
): RevenuePoint[] {
  if (!fromIso || !toIso) return [];
  return points.filter((p) => p.date >= fromIso && p.date <= toIso);
}

/**
 * Select a trailing UTC calendar range ending at `toIso`. Unlike slicing by
 * point count, this remains correct for sparse series such as partner payouts.
 */
export function filterRevenueByPreset(
  points: RevenuePoint[],
  preset: RevenuePreset,
  toIso = new Date().toISOString().slice(0, 10)
): RevenuePoint[] {
  if (!points?.length) return [];
  if (preset === "all") return points.slice();
  const end = noonUtcMs(toIso);
  if (!end) return [];
  const start = end - (preset - 1) * 86400000;
  return points.filter((point) => {
    const timestamp = noonUtcMs(point.date);
    return timestamp >= start && timestamp <= end;
  });
}

/** A calendar series can be populated entirely with zero-value buckets. */
export function hasChartValues(points: RevenuePoint[]): boolean {
  return points.some((point) => {
    const amount = Number(point.amount);
    return Number.isFinite(amount) && amount !== 0;
  });
}

const bucketStart = { week: utcWeekStartMs, month: utcMonthStartMs, year: utcYearStartMs };

/** `dailySorted` ascending by date, consecutive calendar days. */
export function aggregateRevenueSeries(
  dailySorted: RevenuePoint[],
  granularity: RevenueGranularity
): RevenuePoint[] {
  if (!dailySorted?.length) return [];
  if (granularity === "day") {
    return dailySorted.map((point) => ({ ...point, amount: Number(point.amount) || 0 }));
  }
  const buckets = new Map<number, RevenuePoint>();
  for (const point of dailySorted) {
    const start = bucketStart[granularity](point.date);
    const bucket = buckets.get(start) ?? { date: isoUtcDateFromMs(start), amount: 0 };
    bucket.amount += Number(point.amount) || 0;
    if (point.fees != null) bucket.fees = (bucket.fees ?? 0) + point.fees;
    buckets.set(start, bucket);
  }
  return [...buckets.entries()].sort(([a], [b]) => a - b).map(([, point]) => point);
}

/** For chart hint: calendar span of inclusive range. */
export function inclusiveDaySpan(fromIso: string, toIso: string): number {
  const a = noonUtcMs(fromIso);
  const b = noonUtcMs(toIso);
  if (!a || !b) return 0;
  return Math.max(1, Math.round((b - a) / 86400000) + 1);
}
