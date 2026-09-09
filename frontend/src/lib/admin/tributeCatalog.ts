import { daysToLegacyMonths } from "../webapp/subscriptionPeriods";
import type { components } from "../api/openapi.generated";

/**
 * Creator-fallback binding helpers for the tariff editor.
 *
 * Tribute exposes `subscription_id`, `period_id` and `product_id` only through
 * its Creator API, and it never receives the local price, so the two sides
 * drift silently. These helpers fill the bindings in from the fetched catalog
 * and report every divergence the admin has to resolve in Tribute itself.
 */

export type TributeCatalogSubscription = components["schemas"]["AdminTributeSubscriptionOut"];
export type TributeCatalogPeriod = components["schemas"]["AdminTributeSubscriptionPeriodOut"];
export type TributeCatalogProduct = components["schemas"]["AdminTributeProductOut"];

export type TributeCatalog = {
  subscriptions: TributeCatalogSubscription[];
  products: TributeCatalogProduct[];
};

export type TributeDraftRow = Record<string, unknown>;

export type TributeRowUpdate = {
  index: number;
  values: Record<string, string | number>;
};

export type TributeIssue =
  | { kind: "missing_period"; months: number }
  | { kind: "unknown_subscription"; months: number; subscriptionId: number }
  | { kind: "unknown_period"; months: number; periodId: number; subscriptionId: number }
  | { kind: "period_months_mismatch"; months: number; periodId: number; actualPeriod: string }
  | { kind: "price_mismatch"; months: number; localPrice: number; tributePrice: number }
  | { kind: "currency_mismatch"; months: number; expected: string; actual: string }
  | { kind: "unknown_product"; gb: number; productId: number }
  | { kind: "product_price_mismatch"; gb: number; localPrice: number; tributePrice: number }
  | { kind: "product_currency_mismatch"; gb: number; expected: string; actual: string };

export type TributeApplyResult = {
  updates: TributeRowUpdate[];
  issues: TributeIssue[];
};

export type TributeRowApplyResult = {
  values: Record<string, string | number>;
  issues: TributeIssue[];
};

// Prices are compared in major units, so anything below half a cent is noise.
const PRICE_EPSILON = 0.005;

export function emptyTributeCatalog(): TributeCatalog {
  return { subscriptions: [], products: [] };
}

export function normalizeTributeCatalog(value: unknown): TributeCatalog {
  const record = (value || {}) as Partial<TributeCatalog>;
  return {
    subscriptions: Array.isArray(record.subscriptions) ? record.subscriptions : [],
    products: Array.isArray(record.products) ? record.products : [],
  };
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function positiveInt(value: unknown): number | null {
  const parsed = numberValue(value);
  if (parsed === null || !Number.isInteger(parsed) || parsed <= 0) return null;
  return parsed;
}

function currencyCode(value: unknown): string {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function pricesDiffer(local: number, tribute: number): boolean {
  return Math.abs(local - tribute) > PRICE_EPSILON;
}

export function subscriptionOptionLabel(subscription: TributeCatalogSubscription): string {
  const name = (subscription.name || "").trim();
  return name ? `${name} · #${subscription.subscription_id}` : `#${subscription.subscription_id}`;
}

export function productOptionLabel(product: TributeCatalogProduct): string {
  const name = (product.name || "").trim();
  return name ? `${name} · #${product.product_id}` : `#${product.product_id}`;
}

export function findSubscription(
  catalog: TributeCatalog,
  subscriptionId: number | null
): TributeCatalogSubscription | null {
  if (subscriptionId === null) return null;
  return catalog.subscriptions.find((item) => item.subscription_id === subscriptionId) || null;
}

/** Periods Minishop can sell, keyed by their local duration in months. */
export function periodsByMonths(
  subscription: TributeCatalogSubscription
): Map<number, TributeCatalogPeriod> {
  const periods = new Map<number, TributeCatalogPeriod>();
  for (const period of subscription.periods || []) {
    const months = period.months;
    if (typeof months !== "number" || months <= 0) continue;
    // Tribute allows several periods of the same length; the first one wins so
    // that repeated applies stay deterministic.
    if (!periods.has(months)) periods.set(months, period);
  }
  return periods;
}

/**
 * Bind every period row to the chosen subscription.
 *
 * The share link is deliberately left alone: the Creator API does not expose
 * it, so only a human can supply it.
 */
export function applySubscriptionToPeriodRows(
  subscription: TributeCatalogSubscription,
  rows: TributeDraftRow[],
  tariffCurrency: string
): TributeApplyResult {
  const periods = periodsByMonths(subscription);
  const updates: TributeRowUpdate[] = [];
  const issues: TributeIssue[] = [];
  const expected = currencyCode(tariffCurrency);
  const actual = currencyCode(subscription.currency);

  rows.forEach((row, index) => {
    const months =
      row.duration_days != null ? daysToLegacyMonths(row.duration_days) : positiveInt(row.months);
    if (months === null) return;
    const period = periods.get(months);
    if (!period) {
      issues.push({ kind: "missing_period", months });
      return;
    }
    updates.push({
      index,
      values: {
        tribute_subscription_id: subscription.subscription_id,
        tribute_period_id: period.period_id,
      },
    });
    if (expected && actual && expected !== actual) {
      issues.push({ kind: "currency_mismatch", months, expected, actual });
    }
    const localPrice = numberValue(row.rub);
    if (localPrice !== null && pricesDiffer(localPrice, period.price)) {
      issues.push({ kind: "price_mismatch", months, localPrice, tributePrice: period.price });
    }
  });

  return { updates, issues };
}

/** Verify the bindings already stored in the draft against the live catalog. */
export function checkPeriodRows(
  catalog: TributeCatalog,
  rows: TributeDraftRow[],
  tariffCurrency: string
): TributeIssue[] {
  const issues: TributeIssue[] = [];
  const expected = currencyCode(tariffCurrency);

  rows.forEach((row) => {
    const months =
      row.duration_days != null ? daysToLegacyMonths(row.duration_days) : positiveInt(row.months);
    const subscriptionId = positiveInt(row.tribute_subscription_id);
    const periodId = positiveInt(row.tribute_period_id);
    if (months === null || subscriptionId === null || periodId === null) return;

    const subscription = findSubscription(catalog, subscriptionId);
    if (!subscription) {
      issues.push({ kind: "unknown_subscription", months, subscriptionId });
      return;
    }
    const period = (subscription.periods || []).find((item) => item.period_id === periodId);
    if (!period) {
      issues.push({ kind: "unknown_period", months, periodId, subscriptionId });
      return;
    }
    if (period.months !== months) {
      issues.push({
        kind: "period_months_mismatch",
        months,
        periodId,
        actualPeriod: period.period,
      });
    }
    const actual = currencyCode(subscription.currency);
    if (expected && actual && expected !== actual) {
      issues.push({ kind: "currency_mismatch", months, expected, actual });
    }
    const localPrice = numberValue(row.rub);
    if (localPrice !== null && pricesDiffer(localPrice, period.price)) {
      issues.push({ kind: "price_mismatch", months, localPrice, tributePrice: period.price });
    }
  });

  return issues;
}

export function findProduct(
  catalog: TributeCatalog,
  productId: number | null
): TributeCatalogProduct | null {
  if (productId === null) return null;
  return catalog.products.find((item) => item.product_id === productId) || null;
}

/** Bind one traffic package to a Digital Product, link included. */
export function applyProductToTrafficRow(
  product: TributeCatalogProduct,
  row: TributeDraftRow,
  tariffCurrency: string
): TributeRowApplyResult {
  const values: Record<string, string | number> = { tribute_product_id: product.product_id };
  // Products, unlike subscriptions, do publish their checkout link.
  if (product.link) values.tribute_product_link = product.link;
  return { values, issues: productIssues(product, row, tariffCurrency) };
}

/** Verify the product bindings already stored in the draft. */
export function checkTrafficRows(
  catalog: TributeCatalog,
  rows: TributeDraftRow[],
  tariffCurrency: string
): TributeIssue[] {
  const issues: TributeIssue[] = [];

  rows.forEach((row) => {
    const productId = positiveInt(row.tribute_product_id);
    if (productId === null) return;
    const gb = numberValue(row.gb) ?? 0;
    const product = findProduct(catalog, productId);
    if (!product) {
      issues.push({ kind: "unknown_product", gb, productId });
      return;
    }
    issues.push(...productIssues(product, row, tariffCurrency));
  });

  return issues;
}

function productIssues(
  product: TributeCatalogProduct,
  row: TributeDraftRow,
  tariffCurrency: string
): TributeIssue[] {
  const issues: TributeIssue[] = [];
  const gb = numberValue(row.gb) ?? 0;
  const expected = currencyCode(tariffCurrency);
  const actual = currencyCode(product.currency);
  if (expected && actual && expected !== actual) {
    issues.push({ kind: "product_currency_mismatch", gb, expected, actual });
  }
  const localPrice = numberValue(row.price);
  if (localPrice !== null && pricesDiffer(localPrice, product.price)) {
    issues.push({
      kind: "product_price_mismatch",
      gb,
      localPrice,
      tributePrice: product.price,
    });
  }
  return issues;
}
