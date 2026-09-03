import {
  normalizeDayTariff,
  parseDurationDays,
  preserveInactivePeriodMetadata,
} from "./tariffPeriods";
import { structuredCloneSafe } from "./format.js";

type UnknownRecord = Record<string, unknown>;
type DraftRow = UnknownRecord;
type PackageSet = Record<string, DraftRow[]>;

export interface TariffCatalogDraft extends UnknownRecord {
  default_tariff: string;
  default_currency: string;
  topup_packages_default: unknown;
  tariffs: unknown[];
}

export interface TariffDraft extends UnknownRecord {
  defaultCurrency: string;
  key: string;
  legacyKeys: unknown;
  nameRu: string;
  nameEn: string;
  descriptionRu: string;
  descriptionEn: string;
  premiumNameRu: string;
  premiumNameEn: string;
  squadUuids: unknown;
  premiumSquadUuids: unknown;
  billing_model: string;
  enabled: boolean;
  topup_always_available: boolean;
  premium_topup_always_available: boolean;
  checkout_devices_enabled: boolean;
  checkout_devices_max_extra: string | number;
  checkout_devices_price_per_device: string | number;
  checkout_devices_stars_price_per_device: string | number;
  checkout_traffic_enabled: boolean;
  checkout_premium_traffic_enabled: boolean;
  flexible_traffic_step_gb: string | number;
  flexible_traffic_max_total_gb: string | number;
  flexible_traffic_price_per_step: string | number;
  flexible_traffic_stars_price_per_step: string | number;
  premium_flexible_traffic_step_gb: string | number;
  premium_flexible_traffic_max_total_gb: string | number;
  premium_flexible_traffic_price_per_step: string | number;
  premium_flexible_traffic_stars_price_per_step: string | number;
  monthly_gb: string | number;
  traffic_limit_strategy: string;
  premium_monthly_gb: string | number;
  premium_unlimited: boolean;
  premium_traffic_limit_strategy: string;
  hwid_device_limit: string | number;
  conversion_rate_rub_per_gb: string | number;
  tributeLink: string;
  tributeSubscriptionId: string | number;
  periodRows: DraftRow[];
  topupRows: DraftRow[];
  premiumTopupRows: DraftRow[];
  trafficRows: DraftRow[];
  hwidRows: DraftRow[];
}

type ParsedPeriodRow = {
  duration_days: number | null;
  rub: number | null;
  stars: number | null;
  referral_inviter: number | null;
  referral_referee: number | null;
  tribute_period_id: number | null;
  tribute_link: string;
  tribute_subscription_id: number | null;
};

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function asRecord(value: unknown): UnknownRecord {
  return isRecord(value) ? value : {};
}

function asStringRecord(value: unknown): Record<string, string> {
  const record = asRecord(value);
  return Object.fromEntries(Object.entries(record).map(([key, item]) => [key, String(item ?? "")]));
}

function cloneValue<T>(value: T): T {
  return structuredCloneSafe(value) as T;
}

function hasPositiveMonths(
  row: ParsedPeriodRow
): row is ParsedPeriodRow & { duration_days: number } {
  return row.duration_days !== null && row.duration_days > 0;
}

function scalarDraftValue(value: unknown): string | number {
  return typeof value === "string" || typeof value === "number" ? value : "";
}

export function emptyTariffDraft(): TariffDraft {
  return {
    defaultCurrency: "rub",
    key: "",
    legacyKeys: [],
    nameRu: "",
    nameEn: "",
    descriptionRu: "",
    descriptionEn: "",
    premiumNameRu: "",
    premiumNameEn: "",
    squadUuids: [],
    premiumSquadUuids: [],
    billing_model: "period",
    enabled: true,
    topup_always_available: false,
    premium_topup_always_available: false,
    checkout_devices_enabled: false,
    checkout_devices_max_extra: "",
    checkout_devices_price_per_device: "",
    checkout_devices_stars_price_per_device: "",
    checkout_traffic_enabled: false,
    checkout_premium_traffic_enabled: false,
    flexible_traffic_step_gb: "",
    flexible_traffic_max_total_gb: "",
    flexible_traffic_price_per_step: "",
    flexible_traffic_stars_price_per_step: "",
    premium_flexible_traffic_step_gb: "",
    premium_flexible_traffic_max_total_gb: "",
    premium_flexible_traffic_price_per_step: "",
    premium_flexible_traffic_stars_price_per_step: "",
    monthly_gb: 500,
    traffic_limit_strategy: "MONTH",
    premium_monthly_gb: "",
    premium_unlimited: false,
    premium_traffic_limit_strategy: "",
    hwid_device_limit: "",
    conversion_rate_rub_per_gb: "",
    tributeLink: "",
    tributeSubscriptionId: "",
    periodRows: [
      {
        duration_days: 30,
        rub: 200,
        stars: "",
        referral_inviter: 3,
        referral_referee: 1,
        tribute_period_id: "",
        tribute_link: "",
        tribute_subscription_id: "",
      },
      {
        duration_days: 90,
        rub: 600,
        stars: "",
        referral_inviter: 7,
        referral_referee: 3,
        tribute_period_id: "",
        tribute_link: "",
        tribute_subscription_id: "",
      },
      {
        duration_days: 180,
        rub: 1200,
        stars: "",
        referral_inviter: 15,
        referral_referee: 7,
        tribute_period_id: "",
        tribute_link: "",
        tribute_subscription_id: "",
      },
      {
        duration_days: 365,
        rub: 2400,
        stars: "",
        referral_inviter: 30,
        referral_referee: 15,
        tribute_period_id: "",
        tribute_link: "",
        tribute_subscription_id: "",
      },
    ],
    topupRows: [],
    premiumTopupRows: [],
    trafficRows: [
      {
        gb: 10,
        price: 199,
        stars: "",
        tribute_product_id: "",
        tribute_product_link: "",
      },
      {
        gb: 50,
        price: 799,
        stars: "",
        tribute_product_id: "",
        tribute_product_link: "",
      },
    ],
    hwidRows: [],
  };
}

export function cloneCatalog<T>(catalog: T | null | undefined): T & TariffCatalogDraft {
  const source = asRecord(catalog);
  return cloneValue({
    ...source,
    default_tariff: String(source.default_tariff || ""),
    default_currency: normalizeCurrencyKey(source.default_currency || "rub"),
    topup_packages_default: source.topup_packages_default || { rub: [], stars: [] },
    tariffs: Array.isArray(source.tariffs) ? source.tariffs : [],
  }) as T & TariffCatalogDraft;
}

export function normalizeCurrencyKey(value: unknown, fallback = "rub"): string {
  const text = String(value || "")
    .trim()
    .toLowerCase();
  if (!text) return fallback;
  if (text === "rur") return "rub";
  if (["xtr", "star", "stars"].includes(text)) return "stars";
  return text.replace(/[^a-z0-9_-]/g, "") || fallback;
}

export function rowsFromPackages(
  packageSet: PackageSet | null | undefined,
  currency: string,
  valueKey: string,
  options: { sharedNumberKeys?: string[] } = {}
): DraftRow[] {
  return (packageSet?.[currency] || []).map((pkg) => {
    const row: DraftRow = {
      [valueKey]: pkg[valueKey],
      price: pkg.price,
      prices: pkg.prices ? cloneValue(pkg.prices) : undefined,
      min_price: pkg.min_price ?? "",
    };
    for (const key of options.sharedNumberKeys || []) {
      row[key] = pkg[key];
    }
    return row;
  });
}

function packageValueSignature(value: unknown): string {
  const num = Number(value);
  return Number.isFinite(num) ? String(num) : String(value || "");
}

function rowsWithTributeProducts(
  rows: DraftRow[],
  valueKey: string,
  productsValue: unknown
): DraftRow[] {
  const products = asRecord(productsValue);
  return rows.map((row) => {
    const product = asRecord(products[packageValueSignature(row[valueKey])]);
    return {
      ...row,
      tribute_product_id: scalarDraftValue(product.product_id),
      tribute_product_link: String(product.link || ""),
    };
  });
}

export function packageRowsFromPackageSet(
  packageSet: PackageSet | null | undefined,
  currency: string,
  valueKey: string,
  options: { sharedNumberKeys?: string[] } = {}
): DraftRow[] {
  const currencyRows = rowsFromPackages(packageSet, currency, valueKey, options);
  const starsRows = rowsFromPackages(packageSet, "stars", valueKey, options);
  const usedStars = new Set();

  const rows: DraftRow[] = currencyRows.map((row) => {
    const rowSignature = packageValueSignature(row[valueKey]);
    const starsIndex = starsRows.findIndex(
      (starsRow, index) =>
        !usedStars.has(index) && packageValueSignature(starsRow[valueKey]) === rowSignature
    );
    const starsRow = starsIndex >= 0 ? starsRows[starsIndex] : null;
    if (starsIndex >= 0) usedStars.add(starsIndex);

    const merged: DraftRow = {
      [valueKey]: row[valueKey],
      price: row.price,
      stars: starsRow?.price ?? "",
      prices: row.prices,
      min_price: row.min_price,
      stars_prices: starsRow?.prices,
      stars_min_price: starsRow?.min_price ?? "",
    };
    for (const key of options.sharedNumberKeys || []) {
      merged[key] = row[key] ?? starsRow?.[key] ?? 0;
    }
    return merged;
  });

  starsRows.forEach((starsRow, index) => {
    if (usedStars.has(index)) return;
    const merged: DraftRow = {
      [valueKey]: starsRow[valueKey],
      price: "",
      stars: starsRow.price,
      stars_prices: starsRow.prices,
      stars_min_price: starsRow.min_price ?? "",
    };
    for (const key of options.sharedNumberKeys || []) {
      merged[key] = starsRow[key] ?? 0;
    }
    rows.push(merged);
  });

  return rows;
}

export function draftFromTariff(tariff: UnknownRecord, defaultCurrency = "rub"): TariffDraft {
  tariff = normalizeDayTariff(tariff);
  const currency = normalizeCurrencyKey(defaultCurrency);
  const prices = asRecord(tariff.prices);
  const defaultPrices = asRecord(prices[currency]);
  const rubPrices = asRecord(tariff.prices_rub);
  const tribute = asRecord(tariff.tribute);
  const tributePeriodIds = asRecord(tribute.period_ids);
  const tributePeriodLinks = asRecord(tribute.period_links);
  const tributePeriodSubscriptionIds = asRecord(tribute.period_subscription_ids);
  // enabled_periods comes first so its order (the configured purchase order)
  // is preserved; any extra price-only months are appended afterwards.
  const months = new Set([
    ...(Array.isArray(tariff.enabled_periods) ? tariff.enabled_periods : []),
    ...Object.keys(defaultPrices).map(Number),
    ...(currency === "rub" ? Object.keys(asRecord(tariff.prices_rub)).map(Number) : []),
    ...Object.keys(asRecord(tariff.prices_stars)).map(Number),
    ...Object.keys(tributePeriodIds).map(Number),
  ]);
  const periodRows = [...months]
    .filter((month) => Number.isFinite(month) && month > 0)
    .map((month) => ({
      duration_days: month,
      rub:
        (currency === "rub" ? rubPrices[String(month)] : undefined) ??
        defaultPrices?.[String(month)] ??
        "",
      stars: asRecord(tariff.prices_stars)[String(month)] ?? "",
      referral_inviter: asRecord(tariff.referral_bonus_days_inviter)[String(month)] ?? "",
      referral_referee: asRecord(tariff.referral_bonus_days_referee)[String(month)] ?? "",
      tribute_period_id: tributePeriodIds[String(month)] ?? "",
      tribute_link: String(tributePeriodLinks[String(month)] ?? ""),
      tribute_subscription_id: scalarDraftValue(tributePeriodSubscriptionIds[String(month)]),
    }));
  const names = asStringRecord(tariff.names);
  const descriptions = asStringRecord(tariff.descriptions);
  const premiumNames = asStringRecord(tariff.premium_names);
  const checkoutAddons = asRecord(tariff.checkout_addons);
  const checkoutDevices = asRecord(checkoutAddons.devices);
  const checkoutTraffic = asRecord(checkoutAddons.traffic);
  const checkoutPremiumTraffic = asRecord(checkoutAddons.premium_traffic);
  const flexibleTrafficLimit = asRecord(tariff.flexible_traffic_limit);
  const premiumFlexibleTrafficLimit = asRecord(tariff.premium_flexible_traffic_limit);

  return {
    ...emptyTariffDraft(),
    originalPeriodPrices: cloneValue(prices),
    originalPeriodMetadata: cloneValue(tariff),
    addonPeriodFactors: cloneValue(tariff.addon_period_factors || {}),
    defaultCurrency: currency,
    key: String(tariff.key || ""),
    legacyKeys: tariff.legacy_keys || [],
    nameRu: names.ru || "",
    nameEn: names.en || "",
    descriptionRu: descriptions.ru || "",
    descriptionEn: descriptions.en || "",
    premiumNameRu: premiumNames.ru || "",
    premiumNameEn: premiumNames.en || "",
    squadUuids: tariff.squad_uuids || [],
    premiumSquadUuids: tariff.premium_squad_uuids || [],
    billing_model: String(tariff.billing_model || "period"),
    enabled: tariff.enabled !== false,
    topup_always_available: tariff.topup_always_available === true,
    premium_topup_always_available: tariff.premium_topup_always_available === true,
    checkout_devices_enabled: checkoutDevices.enabled === true,
    checkout_devices_max_extra: scalarDraftValue(checkoutDevices.max_extra_devices),
    checkout_devices_price_per_device: scalarDraftValue(checkoutDevices.price_per_device),
    checkout_devices_stars_price_per_device: scalarDraftValue(
      checkoutDevices.stars_price_per_device
    ),
    checkout_traffic_enabled: checkoutTraffic.enabled === true,
    checkout_premium_traffic_enabled: checkoutPremiumTraffic.enabled === true,
    flexible_traffic_step_gb: scalarDraftValue(flexibleTrafficLimit.step_gb),
    flexible_traffic_max_total_gb: scalarDraftValue(flexibleTrafficLimit.max_total_gb),
    flexible_traffic_price_per_step: scalarDraftValue(flexibleTrafficLimit.price_per_step),
    flexible_traffic_stars_price_per_step: scalarDraftValue(
      flexibleTrafficLimit.stars_price_per_step
    ),
    premium_flexible_traffic_step_gb: scalarDraftValue(premiumFlexibleTrafficLimit.step_gb),
    premium_flexible_traffic_max_total_gb: scalarDraftValue(
      premiumFlexibleTrafficLimit.max_total_gb
    ),
    premium_flexible_traffic_price_per_step: scalarDraftValue(
      premiumFlexibleTrafficLimit.price_per_step
    ),
    premium_flexible_traffic_stars_price_per_step: scalarDraftValue(
      premiumFlexibleTrafficLimit.stars_price_per_step
    ),
    monthly_gb: scalarDraftValue(tariff.monthly_gb),
    traffic_limit_strategy: String(tariff.traffic_limit_strategy || ""),
    premium_monthly_gb: scalarDraftValue(tariff.premium_monthly_gb),
    premium_unlimited: tariff.premium_unlimited === true,
    premium_traffic_limit_strategy: String(tariff.premium_traffic_limit_strategy || ""),
    hwid_device_limit: scalarDraftValue(tariff.hwid_device_limit),
    conversion_rate_rub_per_gb: scalarDraftValue(tariff.conversion_rate_rub_per_gb),
    tributeLink: String(tribute.link || ""),
    tributeSubscriptionId: scalarDraftValue(tribute.subscription_id),
    periodRows: periodRows.length ? periodRows : emptyTariffDraft().periodRows,
    topupRows: rowsWithTributeProducts(
      packageRowsFromPackageSet(tariff.topup_packages as PackageSet, currency, "gb"),
      "gb",
      tribute.traffic_products
    ),
    premiumTopupRows: rowsWithTributeProducts(
      packageRowsFromPackageSet(tariff.premium_topup_packages as PackageSet, currency, "gb"),
      "gb",
      tribute.premium_traffic_products
    ),
    trafficRows: rowsWithTributeProducts(
      packageRowsFromPackageSet(tariff.traffic_packages as PackageSet, currency, "gb"),
      "gb",
      tribute.traffic_products
    ),
    hwidRows: packageRowsFromPackageSet(
      tariff.hwid_device_packages as PackageSet,
      currency,
      "count",
      { sharedNumberKeys: ["traffic_bonus_gb"] }
    ),
  };
}

export function parseNumber(value: unknown, fallback: number | null = null): number | null {
  if (value === "" || value === null || value === undefined) return fallback;
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

export function parseIntNumber(value: unknown, fallback: number | null = null): number | null {
  const num = parseNumber(value, fallback);
  return num === null ? fallback : Math.trunc(num);
}

export function compactMap(obj: UnknownRecord): UnknownRecord {
  return Object.fromEntries(
    Object.entries(obj).filter(([, value]) => value !== "" && value !== null && value !== undefined)
  );
}

export function packagesFromRows(rows: DraftRow[], valueKey: string): DraftRow[] {
  return (rows || [])
    .map((row) => {
      const pkg: DraftRow = {
        [valueKey]: parseNumber(row[valueKey]),
        price: parseNumber(row.price),
      };
      if (row.prices && typeof row.prices === "object") {
        pkg.prices = cloneValue(row.prices);
      }
      const minPrice = parseNumber(row.min_price);
      if (minPrice !== null) {
        pkg.min_price = minPrice;
      }
      return pkg;
    })
    .filter(
      (row) => Number(row[valueKey] || 0) > 0 && row.price !== null && Number(row.price) >= 0
    );
}

export function packagesFromPackageRows(
  rows: DraftRow[],
  valueKey: string,
  priceKey: string,
  options: { pricesKey?: string; minPriceKey?: string; sharedNumberKeys?: string[] } = {}
): DraftRow[] {
  const pricesKey = options.pricesKey || "prices";
  const minPriceKey = options.minPriceKey || "min_price";
  return (rows || [])
    .map((row) => {
      const pkg: DraftRow = {
        [valueKey]: parseNumber(row[valueKey]),
        price: parseNumber(row[priceKey]),
      };
      if (row[pricesKey] && typeof row[pricesKey] === "object") {
        pkg.prices = cloneValue(row[pricesKey]);
        if (valueKey === "count") pkg.period_unit = "day";
      }
      const minPrice = parseNumber(row[minPriceKey]);
      if (minPrice !== null) {
        pkg.min_price = minPrice;
      }
      for (const key of options.sharedNumberKeys || []) {
        pkg[key] = parseNumber(row[key], 0) ?? 0;
      }
      return pkg;
    })
    .filter(
      (row) => Number(row[valueKey] || 0) > 0 && row.price !== null && Number(row.price) >= 0
    );
}

export function packageSetFromRows(
  rows: DraftRow[],
  valueKey: string,
  defaultCurrency = "rub",
  options: { sharedNumberKeys?: string[] } = {}
): PackageSet | null {
  const currency = normalizeCurrencyKey(defaultCurrency);
  const defaultCurrencyPackages = packagesFromPackageRows(rows, valueKey, "price", options);
  const stars = packagesFromPackageRows(rows, valueKey, "stars", {
    pricesKey: "stars_prices",
    minPriceKey: "stars_min_price",
    sharedNumberKeys: options.sharedNumberKeys,
  });
  if (!defaultCurrencyPackages.length && !stars.length) return null;
  return {
    ...(defaultCurrencyPackages.length ? { [currency]: defaultCurrencyPackages } : {}),
    ...(stars.length ? { stars } : {}),
  };
}

export function tributeProductsFromRows(rows: DraftRow[], valueKey: string): UnknownRecord {
  const products: UnknownRecord = {};
  for (const row of rows || []) {
    const unit = parseNumber(row[valueKey]);
    if (unit === null || unit <= 0) continue;
    const productId = parseNumber(row.tribute_product_id);
    const link = String(row.tribute_product_link || "").trim();
    if (productId === null && !link) continue;
    products[String(unit)] = {
      product_id: productId,
      link,
    };
  }
  return products;
}

export function normalizeUuidList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  return String(value || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function tariffFromDraft(draft: TariffDraft, fallbackCurrency = "rub"): UnknownRecord {
  const defaultCurrency = normalizeCurrencyKey(draft.defaultCurrency || fallbackCurrency);
  const key = draft.key.trim();
  const premiumSquadUuids = normalizeUuidList(draft.premiumSquadUuids);
  const hasPremiumSquads = premiumSquadUuids.length > 0;
  const names = compactMap({ ru: draft.nameRu.trim(), en: draft.nameEn.trim() });
  const descriptions = compactMap({
    ru: draft.descriptionRu.trim(),
    en: draft.descriptionEn.trim(),
  });
  const premiumNames = compactMap({
    ru: draft.premiumNameRu.trim(),
    en: draft.premiumNameEn.trim(),
  });
  const tariff: UnknownRecord = {
    key,
    names,
    descriptions,
    premium_names: premiumNames,
    squad_uuids: normalizeUuidList(draft.squadUuids),
    premium_squad_uuids: premiumSquadUuids,
    billing_model: draft.billing_model,
    enabled: Boolean(draft.enabled),
    checkout_addons: {
      devices: {
        enabled: Boolean(draft.checkout_devices_enabled),
        max_extra_devices: parseIntNumber(draft.checkout_devices_max_extra),
        price_per_device: parseNumber(draft.checkout_devices_price_per_device),
        stars_price_per_device: parseIntNumber(draft.checkout_devices_stars_price_per_device),
      },
      traffic: {
        enabled: Boolean(draft.checkout_traffic_enabled),
      },
      premium_traffic: {
        enabled: hasPremiumSquads && Boolean(draft.checkout_premium_traffic_enabled),
      },
    },
  };
  const legacyKeys = normalizeUuidList(draft.legacyKeys).filter((item) => item !== key);
  if (legacyKeys.length) tariff.legacy_keys = [...new Set(legacyKeys)];

  const hwidLimit = parseIntNumber(draft.hwid_device_limit);
  if (hwidLimit !== null) tariff.hwid_device_limit = hwidLimit;
  const hwidPackages = packageSetFromRows(draft.hwidRows, "count", defaultCurrency, {
    sharedNumberKeys: ["traffic_bonus_gb"],
  });
  if (hwidPackages) tariff.hwid_device_packages = hwidPackages;
  const tribute: UnknownRecord = {};
  const premiumMonthlyGb = parseNumber(draft.premium_monthly_gb);
  if (hasPremiumSquads && premiumMonthlyGb !== null) {
    tariff.premium_monthly_gb = premiumMonthlyGb;
  }
  tariff.premium_unlimited = Boolean(draft.premium_unlimited);
  const premiumTrafficLimitStrategy = String(draft.premium_traffic_limit_strategy || "").trim();
  if (premiumTrafficLimitStrategy) {
    tariff.premium_traffic_limit_strategy = premiumTrafficLimitStrategy;
  }
  if (hasPremiumSquads) {
    const premiumTopupPackages = packageSetFromRows(draft.premiumTopupRows, "gb", defaultCurrency);
    if (premiumTopupPackages) tariff.premium_topup_packages = premiumTopupPackages;
    const premiumFlexibleStepGb = parseNumber(draft.premium_flexible_traffic_step_gb);
    const premiumFlexibleMaxTotalGb = parseNumber(draft.premium_flexible_traffic_max_total_gb);
    const premiumFlexiblePricePerStep = parseNumber(draft.premium_flexible_traffic_price_per_step);
    if (
      premiumFlexibleStepGb !== null &&
      premiumFlexibleMaxTotalGb !== null &&
      premiumFlexiblePricePerStep !== null
    ) {
      tariff.premium_flexible_traffic_limit = {
        step_gb: premiumFlexibleStepGb,
        max_total_gb: premiumFlexibleMaxTotalGb,
        price_per_step: premiumFlexiblePricePerStep,
        stars_price_per_step: parseIntNumber(draft.premium_flexible_traffic_stars_price_per_step),
      };
    }
    const premiumTrafficProducts = tributeProductsFromRows(draft.premiumTopupRows, "gb");
    if (Object.keys(premiumTrafficProducts).length) {
      tribute.premium_traffic_products = premiumTrafficProducts;
    }
  }
  tariff.premium_topup_always_available = Boolean(draft.premium_topup_always_available);

  if (tariff.billing_model === "period") {
    const trafficLimitStrategy = String(draft.traffic_limit_strategy || "").trim();
    if (trafficLimitStrategy) tariff.traffic_limit_strategy = trafficLimitStrategy;
    const seenMonths = new Set();
    if (
      (draft.periodRows || []).some((row) => parseDurationDays(row.duration_days) === null) ||
      new Set(draft.periodRows.map((row) => Number(row.duration_days))).size !==
        draft.periodRows.length
    ) {
      throw new Error("invalid_subscription_periods");
    }
    tariff.period_unit = "day";
    tariff.addon_period_factors = cloneValue(draft.addonPeriodFactors || {});
    const rows = (draft.periodRows || [])
      .map((row) => ({
        duration_days: parseDurationDays(row.duration_days),
        rub: parseNumber(row.rub, 0),
        stars: parseNumber(row.stars, 0),
        referral_inviter: parseIntNumber(row.referral_inviter),
        referral_referee: parseIntNumber(row.referral_referee),
        tribute_period_id: parseNumber(row.tribute_period_id),
        tribute_link: String(row.tribute_link || "").trim(),
        tribute_subscription_id: parseNumber(row.tribute_subscription_id),
      }))
      .filter(hasPositiveMonths)
      .filter((row) => {
        if (seenMonths.has(row.duration_days)) return false;
        seenMonths.add(row.duration_days);
        return true;
      });
    tariff.monthly_gb = parseNumber(draft.monthly_gb, 0);
    tariff.enabled_periods = rows.map((row) => row.duration_days);
    const defaultPrices = Object.fromEntries(
      rows.map((row) => [String(row.duration_days), row.rub || 0])
    );
    tariff.prices = { ...asRecord(draft.originalPeriodPrices), [defaultCurrency]: defaultPrices };
    if (defaultCurrency === "rub") tariff.prices_rub = defaultPrices;
    tariff.prices_stars = Object.fromEntries(
      rows.map((row) => [String(row.duration_days), row.stars || 0])
    );
    tariff.referral_bonus_days_inviter = Object.fromEntries(
      rows
        .filter((row) => row.referral_inviter !== null)
        .map((row) => [String(row.duration_days), row.referral_inviter])
    );
    tariff.referral_bonus_days_referee = Object.fromEntries(
      rows
        .filter((row) => row.referral_referee !== null)
        .map((row) => [String(row.duration_days), row.referral_referee])
    );
    const tributeLink = String(draft.tributeLink || "").trim();
    const tributeSubscriptionId = parseNumber(draft.tributeSubscriptionId);
    const tributePeriodIds = Object.fromEntries(
      rows
        .filter((row) => row.tribute_period_id !== null)
        .map((row) => [String(row.duration_days), row.tribute_period_id])
    );
    // A period may be sold by its own Tribute subscription; the tariff-level
    // pair stays as the default for the periods that do not name one.
    const tributePeriodLinks = Object.fromEntries(
      rows
        .filter((row) => row.tribute_link)
        .map((row) => [String(row.duration_days), row.tribute_link])
    );
    const tributePeriodSubscriptionIds = Object.fromEntries(
      rows
        .filter((row) => row.tribute_subscription_id !== null)
        .map((row) => [String(row.duration_days), row.tribute_subscription_id])
    );
    if (
      tributeLink ||
      tributeSubscriptionId !== null ||
      Object.keys(tributePeriodIds).length > 0 ||
      Object.keys(tributePeriodLinks).length > 0 ||
      Object.keys(tributePeriodSubscriptionIds).length > 0
    ) {
      if (tributeLink) tribute.link = tributeLink;
      if (tributeSubscriptionId !== null) tribute.subscription_id = tributeSubscriptionId;
      tribute.period_unit = "day";
      tribute.period_ids = tributePeriodIds;
      if (Object.keys(tributePeriodLinks).length) {
        tribute.period_links = tributePeriodLinks;
      }
      if (Object.keys(tributePeriodSubscriptionIds).length) {
        tribute.period_subscription_ids = tributePeriodSubscriptionIds;
      }
    }
    const topupPackages = packageSetFromRows(draft.topupRows, "gb", defaultCurrency);
    if (topupPackages) tariff.topup_packages = topupPackages;
    const flexibleStepGb = parseNumber(draft.flexible_traffic_step_gb);
    const flexibleMaxTotalGb = parseNumber(draft.flexible_traffic_max_total_gb);
    const flexiblePricePerStep = parseNumber(draft.flexible_traffic_price_per_step);
    if (flexibleStepGb !== null && flexibleMaxTotalGb !== null && flexiblePricePerStep !== null) {
      tariff.flexible_traffic_limit = {
        step_gb: flexibleStepGb,
        max_total_gb: flexibleMaxTotalGb,
        price_per_step: flexiblePricePerStep,
        stars_price_per_step: parseIntNumber(draft.flexible_traffic_stars_price_per_step),
      };
    }
    const trafficProducts = tributeProductsFromRows(draft.topupRows, "gb");
    if (Object.keys(trafficProducts).length) {
      tribute.traffic_products = trafficProducts;
    }
    tariff.topup_always_available = Boolean(draft.topup_always_available);
  } else {
    const trafficPackages = packageSetFromRows(draft.trafficRows, "gb", defaultCurrency);
    if (trafficPackages) tariff.traffic_packages = trafficPackages;
    const trafficProducts = tributeProductsFromRows(draft.trafficRows, "gb");
    if (Object.keys(trafficProducts).length) {
      tribute.traffic_products = trafficProducts;
    }
    const conversion = parseNumber(draft.conversion_rate_rub_per_gb);
    if (conversion !== null) tariff.conversion_rate_rub_per_gb = conversion;
  }
  if (Object.keys(tribute).length) {
    tariff.tribute = tribute;
  }

  preserveInactivePeriodMetadata(tariff, asRecord(draft.originalPeriodMetadata));
  return tariff;
}
