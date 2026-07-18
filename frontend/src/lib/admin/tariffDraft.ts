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
  monthly_gb: string | number;
  traffic_limit_strategy: string;
  premium_monthly_gb: string | number;
  hwid_device_limit: string | number;
  conversion_rate_rub_per_gb: string | number;
  periodRows: DraftRow[];
  topupRows: DraftRow[];
  premiumTopupRows: DraftRow[];
  trafficRows: DraftRow[];
  hwidRows: DraftRow[];
}

type ParsedPeriodRow = {
  months: number | null;
  rub: number | null;
  stars: number | null;
  referral_inviter: number | null;
  referral_referee: number | null;
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

function hasPositiveMonths(row: ParsedPeriodRow): row is ParsedPeriodRow & { months: number } {
  return row.months !== null && row.months > 0;
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
    monthly_gb: 500,
    traffic_limit_strategy: "MONTH",
    premium_monthly_gb: "",
    hwid_device_limit: "",
    conversion_rate_rub_per_gb: "",
    periodRows: [
      { months: 1, rub: 200, stars: "", referral_inviter: 3, referral_referee: 1 },
      { months: 3, rub: 600, stars: "", referral_inviter: 7, referral_referee: 3 },
      { months: 6, rub: 1200, stars: "", referral_inviter: 15, referral_referee: 7 },
      { months: 12, rub: 2400, stars: "", referral_inviter: 30, referral_referee: 15 },
    ],
    topupRows: [],
    premiumTopupRows: [],
    trafficRows: [
      { gb: 10, price: 199, stars: "" },
      { gb: 50, price: 799, stars: "" },
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
  valueKey: string
): DraftRow[] {
  return (packageSet?.[currency] || []).map((pkg) => ({
    [valueKey]: pkg[valueKey],
    price: pkg.price,
    prices: pkg.prices ? cloneValue(pkg.prices) : undefined,
    min_price: pkg.min_price ?? "",
  }));
}

function packageValueSignature(value: unknown): string {
  const num = Number(value);
  return Number.isFinite(num) ? String(num) : String(value || "");
}

export function packageRowsFromPackageSet(
  packageSet: PackageSet | null | undefined,
  currency: string,
  valueKey: string
): DraftRow[] {
  const currencyRows = rowsFromPackages(packageSet, currency, valueKey);
  const starsRows = rowsFromPackages(packageSet, "stars", valueKey);
  const usedStars = new Set();

  const rows: DraftRow[] = currencyRows.map((row) => {
    const rowSignature = packageValueSignature(row[valueKey]);
    const starsIndex = starsRows.findIndex(
      (starsRow, index) =>
        !usedStars.has(index) && packageValueSignature(starsRow[valueKey]) === rowSignature
    );
    const starsRow = starsIndex >= 0 ? starsRows[starsIndex] : null;
    if (starsIndex >= 0) usedStars.add(starsIndex);

    return {
      [valueKey]: row[valueKey],
      price: row.price,
      stars: starsRow?.price ?? "",
      prices: row.prices,
      min_price: row.min_price,
      stars_prices: starsRow?.prices,
      stars_min_price: starsRow?.min_price ?? "",
    };
  });

  starsRows.forEach((starsRow, index) => {
    if (usedStars.has(index)) return;
    rows.push({
      [valueKey]: starsRow[valueKey],
      price: "",
      stars: starsRow.price,
      stars_prices: starsRow.prices,
      stars_min_price: starsRow.min_price ?? "",
    });
  });

  return rows;
}

export function draftFromTariff(tariff: UnknownRecord, defaultCurrency = "rub"): TariffDraft {
  const currency = normalizeCurrencyKey(defaultCurrency);
  const prices = asRecord(tariff.prices);
  const defaultPrices = asRecord(prices[currency]);
  const rubPrices = asRecord(tariff.prices_rub);
  // enabled_periods comes first so its order (the configured purchase order)
  // is preserved; any extra price-only months are appended afterwards.
  const months = new Set([
    ...(Array.isArray(tariff.enabled_periods) ? tariff.enabled_periods : []),
    ...Object.keys(defaultPrices).map(Number),
    ...(currency === "rub" ? Object.keys(asRecord(tariff.prices_rub)).map(Number) : []),
    ...Object.keys(asRecord(tariff.prices_stars)).map(Number),
  ]);
  const periodRows = [...months]
    .filter((month) => Number.isFinite(month) && month > 0)
    .map((month) => ({
      months: month,
      rub:
        (currency === "rub" ? rubPrices[String(month)] : undefined) ??
        defaultPrices?.[String(month)] ??
        "",
      stars: asRecord(tariff.prices_stars)[String(month)] ?? "",
      referral_inviter: asRecord(tariff.referral_bonus_days_inviter)[String(month)] ?? "",
      referral_referee: asRecord(tariff.referral_bonus_days_referee)[String(month)] ?? "",
    }));
  const names = asStringRecord(tariff.names);
  const descriptions = asStringRecord(tariff.descriptions);
  const premiumNames = asStringRecord(tariff.premium_names);

  return {
    ...emptyTariffDraft(),
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
    monthly_gb: scalarDraftValue(tariff.monthly_gb),
    traffic_limit_strategy: String(tariff.traffic_limit_strategy || ""),
    premium_monthly_gb: scalarDraftValue(tariff.premium_monthly_gb),
    hwid_device_limit: scalarDraftValue(tariff.hwid_device_limit),
    conversion_rate_rub_per_gb: scalarDraftValue(tariff.conversion_rate_rub_per_gb),
    periodRows: periodRows.length ? periodRows : emptyTariffDraft().periodRows,
    topupRows: packageRowsFromPackageSet(tariff.topup_packages as PackageSet, currency, "gb"),
    premiumTopupRows: packageRowsFromPackageSet(
      tariff.premium_topup_packages as PackageSet,
      currency,
      "gb"
    ),
    trafficRows: packageRowsFromPackageSet(tariff.traffic_packages as PackageSet, currency, "gb"),
    hwidRows: packageRowsFromPackageSet(
      tariff.hwid_device_packages as PackageSet,
      currency,
      "count"
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
  options: { pricesKey?: string; minPriceKey?: string } = {}
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
      }
      const minPrice = parseNumber(row[minPriceKey]);
      if (minPrice !== null) {
        pkg.min_price = minPrice;
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
  defaultCurrency = "rub"
): PackageSet | null {
  const currency = normalizeCurrencyKey(defaultCurrency);
  const defaultCurrencyPackages = packagesFromPackageRows(rows, valueKey, "price");
  const stars = packagesFromPackageRows(rows, valueKey, "stars", {
    pricesKey: "stars_prices",
    minPriceKey: "stars_min_price",
  });
  if (!defaultCurrencyPackages.length && !stars.length) return null;
  return {
    ...(defaultCurrencyPackages.length ? { [currency]: defaultCurrencyPackages } : {}),
    ...(stars.length ? { stars } : {}),
  };
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
    premium_squad_uuids: normalizeUuidList(draft.premiumSquadUuids),
    billing_model: draft.billing_model,
    enabled: Boolean(draft.enabled),
  };
  const legacyKeys = normalizeUuidList(draft.legacyKeys).filter((item) => item !== key);
  if (legacyKeys.length) tariff.legacy_keys = [...new Set(legacyKeys)];

  const hwidLimit = parseIntNumber(draft.hwid_device_limit);
  if (hwidLimit !== null) tariff.hwid_device_limit = hwidLimit;
  const hwidPackages = packageSetFromRows(draft.hwidRows, "count", defaultCurrency);
  if (hwidPackages) tariff.hwid_device_packages = hwidPackages;
  const premiumMonthlyGb = parseNumber(draft.premium_monthly_gb);
  if (premiumMonthlyGb !== null) tariff.premium_monthly_gb = premiumMonthlyGb;
  const premiumTopupPackages = packageSetFromRows(draft.premiumTopupRows, "gb", defaultCurrency);
  if (premiumTopupPackages) tariff.premium_topup_packages = premiumTopupPackages;
  tariff.premium_topup_always_available = Boolean(draft.premium_topup_always_available);

  if (tariff.billing_model === "period") {
    const trafficLimitStrategy = String(draft.traffic_limit_strategy || "").trim();
    if (trafficLimitStrategy) tariff.traffic_limit_strategy = trafficLimitStrategy;
    const seenMonths = new Set();
    const rows = (draft.periodRows || [])
      .map((row) => ({
        months: parseIntNumber(row.months),
        rub: parseNumber(row.rub, 0),
        stars: parseNumber(row.stars, 0),
        referral_inviter: parseIntNumber(row.referral_inviter),
        referral_referee: parseIntNumber(row.referral_referee),
      }))
      .filter(hasPositiveMonths)
      .filter((row) => {
        if (seenMonths.has(row.months)) return false;
        seenMonths.add(row.months);
        return true;
      });
    tariff.monthly_gb = parseNumber(draft.monthly_gb, 0);
    tariff.enabled_periods = rows.map((row) => row.months);
    const defaultPrices = Object.fromEntries(rows.map((row) => [String(row.months), row.rub || 0]));
    if (defaultCurrency === "rub") {
      tariff.prices_rub = defaultPrices;
    } else {
      tariff.prices = { [defaultCurrency]: defaultPrices };
    }
    tariff.prices_stars = Object.fromEntries(
      rows.map((row) => [String(row.months), row.stars || 0])
    );
    tariff.referral_bonus_days_inviter = Object.fromEntries(
      rows
        .filter((row) => row.referral_inviter !== null)
        .map((row) => [String(row.months), row.referral_inviter])
    );
    tariff.referral_bonus_days_referee = Object.fromEntries(
      rows
        .filter((row) => row.referral_referee !== null)
        .map((row) => [String(row.months), row.referral_referee])
    );
    const topupPackages = packageSetFromRows(draft.topupRows, "gb", defaultCurrency);
    if (topupPackages) tariff.topup_packages = topupPackages;
    tariff.topup_always_available = Boolean(draft.topup_always_available);
  } else {
    const trafficPackages = packageSetFromRows(draft.trafficRows, "gb", defaultCurrency);
    if (trafficPackages) tariff.traffic_packages = trafficPackages;
    const conversion = parseNumber(draft.conversion_rate_rub_per_gb);
    if (conversion !== null) tariff.conversion_rate_rub_per_gb = conversion;
  }

  return tariff;
}
