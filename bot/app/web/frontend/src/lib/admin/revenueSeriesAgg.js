/** @typedef {{ date: string, amount: number }} RevenuePoint */

/**
 * @param {string} iso
 * @returns {number} UTC ms at noon (stable day bucket)
 */
function noonUtcMs(iso) {
  const s = String(iso || "");
  const t = Date.parse(s.includes("T") ? s : `${s}T12:00:00Z`);
  return Number.isFinite(t) ? t : 0;
}

/**
 * @param {number} t
 * @returns {string} YYYY-MM-DD UTC
 */
function isoUtcDateFromMs(t) {
  const d = new Date(t);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * Monday 00:00 UTC for the week containing `iso` (date-only).
 * @param {string} iso
 */
export function utcWeekStartMs(iso) {
  const d = new Date(iso.includes("T") ? iso : `${iso}T12:00:00Z`);
  const dow = d.getUTCDay();
  const offset = (dow + 6) % 7;
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - offset);
}

/**
 * First day of month (UTC) containing `iso`.
 * @param {string} iso
 */
export function utcMonthStartMs(iso) {
  const d = new Date(iso.includes("T") ? iso : `${iso}T12:00:00Z`);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
}

/**
 * @param {RevenuePoint[]} points sorted ascending by `date`
 * @param {string} fromIso YYYY-MM-DD inclusive
 * @param {string} toIso YYYY-MM-DD inclusive
 * @returns {RevenuePoint[]}
 */
export function filterDailyByIsoRange(points, fromIso, toIso) {
  if (!fromIso || !toIso) return [];
  return points.filter((p) => p.date >= fromIso && p.date <= toIso);
}

/**
 * @param {RevenuePoint[]} points sorted ascending
 * @param {number} n
 */
export function sliceLastDays(points, n) {
  if (!points?.length || n <= 0) return [];
  const take = Math.min(n, points.length);
  return points.slice(-take);
}

/**
 * @param {RevenuePoint[]} daily sorted ascending, day granularity
 * @returns {RevenuePoint[]}
 */
function bucketWeeks(daily) {
  /** @type {Map<number, number>} */
  const sums = new Map();
  for (const p of daily) {
    const k = utcWeekStartMs(p.date);
    const amt = Number(p.amount) || 0;
    sums.set(k, (sums.get(k) || 0) + amt);
  }
  return [...sums.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([ms, amount]) => ({ date: isoUtcDateFromMs(ms), amount }));
}

/**
 * @param {RevenuePoint[]} daily sorted ascending
 * @returns {RevenuePoint[]}
 */
function bucketMonths(daily) {
  /** @type {Map<number, number>} */
  const sums = new Map();
  for (const p of daily) {
    const k = utcMonthStartMs(p.date);
    const amt = Number(p.amount) || 0;
    sums.set(k, (sums.get(k) || 0) + amt);
  }
  return [...sums.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([ms, amount]) => ({ date: isoUtcDateFromMs(ms), amount }));
}

/**
 * @param {RevenuePoint[]} dailySorted ascending by date, consecutive calendar days
 * @param {"day" | "week" | "month"} granularity
 */
export function aggregateRevenueSeries(dailySorted, granularity) {
  if (!dailySorted?.length) return [];
  if (granularity === "week") return bucketWeeks(dailySorted);
  if (granularity === "month") return bucketMonths(dailySorted);
  return dailySorted.map((p) => ({ date: p.date, amount: Number(p.amount) || 0 }));
}

/**
 * For chart hint: calendar span of inclusive range.
 * @param {string} fromIso
 * @param {string} toIso
 */
export function inclusiveDaySpan(fromIso, toIso) {
  const a = noonUtcMs(fromIso);
  const b = noonUtcMs(toIso);
  if (!a || !b) return 0;
  return Math.max(1, Math.round((b - a) / 86400000) + 1);
}
