import type { ApiClient, PartnerOverviewResponse } from "./publicApi.js";

export type PartnerBalanceSnapshot = {
  available: number;
  scale: number;
};

type CacheEntry = {
  expiresAt: number;
  promise: Promise<PartnerBalanceSnapshot>;
  value?: PartnerBalanceSnapshot;
};

const CACHE_TTL_MS = 30_000;
const cache = new WeakMap<ApiClient["api"], Map<string, CacheEntry>>();

function normalizedCurrency(currency: string): string {
  return String(currency || "")
    .trim()
    .toUpperCase();
}

function apiCache(api: ApiClient["api"]): Map<string, CacheEntry> {
  let entries = cache.get(api);
  if (!entries) {
    entries = new Map();
    cache.set(api, entries);
  }
  return entries;
}

function snapshotFromOverview(
  overview: PartnerOverviewResponse,
  currency: string
): PartnerBalanceSnapshot {
  const balance = overview.balances.find(
    (item) => normalizedCurrency(String(item.currency || "")) === currency
  );
  if (!overview.balance_payment_enabled || overview.profile?.status !== "active" || !balance) {
    return { available: 0, scale: 2 };
  }
  const scale = Number(balance.currency_scale || 0);
  return {
    available: Number(balance.available_minor || 0) / 10 ** scale,
    scale,
  };
}

export function peekPartnerBalanceSnapshot(
  api: ApiClient["api"],
  currency: string
): PartnerBalanceSnapshot | null {
  const key = normalizedCurrency(currency);
  const entry = key ? cache.get(api)?.get(key) : undefined;
  if (!entry || entry.expiresAt <= Date.now()) return null;
  return entry.value || null;
}

export function loadPartnerBalanceSnapshot(
  api: ApiClient["api"],
  currency: string
): Promise<PartnerBalanceSnapshot> {
  const key = normalizedCurrency(currency);
  if (!key) return Promise.resolve({ available: 0, scale: 2 });

  const entries = apiCache(api);
  const cached = entries.get(key);
  if (cached && cached.expiresAt > Date.now()) return cached.promise;

  const entry: CacheEntry = {
    expiresAt: Date.now() + CACHE_TTL_MS,
    promise: Promise.resolve({ available: 0, scale: 2 }),
  };
  entry.promise = (api("/partner/overview") as Promise<PartnerOverviewResponse>)
    .then((overview) => {
      const value = snapshotFromOverview(overview, key);
      entry.value = value;
      return value;
    })
    .catch((error) => {
      if (entries.get(key) === entry) entries.delete(key);
      throw error;
    });
  entries.set(key, entry);
  return entry.promise;
}
