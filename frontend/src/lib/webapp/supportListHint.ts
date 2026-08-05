/**
 * Last-known support ticket counts, cached per user.
 *
 * The ticket list is empty for most users, so the very first paint of the support screen should
 * not guess "there is something to load" and flash skeleton cards. The counts returned with every
 * list response are cheap to remember, and on the next cold open they answer the only question the
 * screen has before its request resolves: how many cards are about to appear, if any.
 */

const SUPPORT_COUNTS_STORAGE_PREFIX = "rw_webapp_support_counts_v1";
const SUPPORT_COUNTS_TTL_MS = 14 * 24 * 60 * 60 * 1000;
const DEFAULT_SCOPE = "anonymous";

export type SupportTicketCounts = {
  active: number;
  awaiting_admin: number;
  awaiting_user: number;
  closed: number;
  open: number;
  total: number;
};

const COUNT_FIELDS = [
  "active",
  "awaiting_admin",
  "awaiting_user",
  "closed",
  "open",
  "total",
] as const;

// Tabs map onto a single count each; "all" is the whole inbox. Anything else is a filter the
// screen does not know how to size, and an unknown size must stay unknown.
const FILTER_FIELDS: Record<string, keyof SupportTicketCounts> = {
  active: "active",
  awaiting_admin: "awaiting_admin",
  awaiting_user: "awaiting_user",
  closed: "closed",
  open: "open",
};

function safeStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage || null;
  } catch (_error) {
    return null;
  }
}

function countsKey(scope: unknown): string {
  return `${SUPPORT_COUNTS_STORAGE_PREFIX}:${encodeURIComponent(String(scope || DEFAULT_SCOPE))}`;
}

function countValue(value: unknown): number {
  const count = Math.floor(Number(value ?? 0));
  return Number.isFinite(count) && count > 0 ? count : 0;
}

function normalizeCounts(value: unknown): SupportTicketCounts | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const counts = {} as SupportTicketCounts;
  for (const field of COUNT_FIELDS) counts[field] = countValue(record[field]);
  return counts;
}

export function readSupportCountsHint(scope: unknown): SupportTicketCounts | null {
  const storage = safeStorage();
  if (!storage) return null;
  const key = countsKey(scope);

  try {
    const raw = storage.getItem(key);
    if (!raw) return null;

    const envelope = JSON.parse(raw) as { updatedAt?: unknown; counts?: unknown };
    const updatedAt = Number(envelope?.updatedAt || 0);
    if (!updatedAt || Date.now() - updatedAt > SUPPORT_COUNTS_TTL_MS) {
      storage.removeItem(key);
      return null;
    }
    return normalizeCounts(envelope.counts);
  } catch (_error) {
    try {
      storage.removeItem(key);
    } catch (_removeError) {
      void _removeError;
    }
    return null;
  }
}

export function writeSupportCountsHint(scope: unknown, counts: unknown): void {
  const storage = safeStorage();
  const normalized = normalizeCounts(counts);
  if (!storage || !normalized) return;

  try {
    storage.setItem(
      countsKey(scope),
      JSON.stringify({ updatedAt: Date.now(), counts: normalized })
    );
  } catch (_error) {
    void _error;
  }
}

/**
 * How many cards the given tab is expected to render, or `null` when there is nothing to base a
 * guess on. `null` is not "zero": it means the screen must wait instead of committing to either
 * skeletons or the empty state.
 */
export function expectedTicketCount(
  counts: SupportTicketCounts | null,
  filter: unknown
): number | null {
  if (!counts) return null;
  const key = String(filter || "all");
  if (key === "all") return counts.total;
  const field = FILTER_FIELDS[key];
  return field ? counts[field] : null;
}
