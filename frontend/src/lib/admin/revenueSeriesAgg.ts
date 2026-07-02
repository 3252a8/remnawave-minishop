export type RevenuePoint = { date: string; amount: number };

export type RevenueGranularity = "day" | "week" | "month";

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

/** `points` sorted ascending by `date`; `fromIso` / `toIso` are YYYY-MM-DD inclusive. */
export function filterDailyByIsoRange(
  points: RevenuePoint[],
  fromIso: string,
  toIso: string
): RevenuePoint[] {
  if (!fromIso || !toIso) return [];
  return points.filter((p) => p.date >= fromIso && p.date <= toIso);
}

/** `points` sorted ascending. */
export function sliceLastDays(points: RevenuePoint[], n: number): RevenuePoint[] {
  if (!points?.length || n <= 0) return [];
  const take = Math.min(n, points.length);
  return points.slice(-take);
}

/** `daily` sorted ascending, day granularity. */
function bucketWeeks(daily: RevenuePoint[]): RevenuePoint[] {
  const sums = new Map<number, number>();
  for (const p of daily) {
    const k = utcWeekStartMs(p.date);
    const amt = Number(p.amount) || 0;
    sums.set(k, (sums.get(k) || 0) + amt);
  }
  return [...sums.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([ms, amount]) => ({ date: isoUtcDateFromMs(ms), amount }));
}

/** `daily` sorted ascending. */
function bucketMonths(daily: RevenuePoint[]): RevenuePoint[] {
  const sums = new Map<number, number>();
  for (const p of daily) {
    const k = utcMonthStartMs(p.date);
    const amt = Number(p.amount) || 0;
    sums.set(k, (sums.get(k) || 0) + amt);
  }
  return [...sums.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([ms, amount]) => ({ date: isoUtcDateFromMs(ms), amount }));
}

/** `dailySorted` ascending by date, consecutive calendar days. */
export function aggregateRevenueSeries(
  dailySorted: RevenuePoint[],
  granularity: RevenueGranularity
): RevenuePoint[] {
  if (!dailySorted?.length) return [];
  if (granularity === "week") return bucketWeeks(dailySorted);
  if (granularity === "month") return bucketMonths(dailySorted);
  return dailySorted.map((p) => ({ date: p.date, amount: Number(p.amount) || 0 }));
}

/** For chart hint: calendar span of inclusive range. */
export function inclusiveDaySpan(fromIso: string, toIso: string): number {
  const a = noonUtcMs(fromIso);
  const b = noonUtcMs(toIso);
  if (!a || !b) return 0;
  return Math.max(1, Math.round((b - a) / 86400000) + 1);
}
