import { structuredCloneSafe } from "./format.js";

export function emptyTariffDraft() {
  return {
    defaultCurrency: "rub",
    key: "",
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
    monthly_gb: 500,
    premium_monthly_gb: "",
    hwid_device_limit: "",
    conversion_rate_rub_per_gb: "",
    periodRows: [
      { months: 1, rub: 200, stars: "", referral_inviter: 3, referral_referee: 1 },
      { months: 3, rub: 600, stars: "", referral_inviter: 7, referral_referee: 3 },
      { months: 6, rub: 1200, stars: "", referral_inviter: 15, referral_referee: 7 },
      { months: 12, rub: 2400, stars: "", referral_inviter: 30, referral_referee: 15 },
    ],
    topupRubRows: [],
    topupStarsRows: [],
    premiumTopupRubRows: [],
    premiumTopupStarsRows: [],
    trafficRubRows: [
      { gb: 10, price: 199 },
      { gb: 50, price: 799 },
    ],
    trafficStarsRows: [],
    hwidRubRows: [],
    hwidStarsRows: [],
  };
}

export function cloneCatalog(catalog) {
  return structuredCloneSafe({
    default_tariff: catalog?.default_tariff || "",
    default_currency: normalizeCurrencyKey(catalog?.default_currency || "rub"),
    topup_packages_default: catalog?.topup_packages_default || { rub: [], stars: [] },
    tariffs: catalog?.tariffs || [],
  });
}

export function normalizeCurrencyKey(value, fallback = "rub") {
  const text = String(value || "")
    .trim()
    .toLowerCase();
  if (!text) return fallback;
  if (text === "rur") return "rub";
  if (["xtr", "star", "stars"].includes(text)) return "stars";
  return text.replace(/[^a-z0-9_-]/g, "") || fallback;
}

export function rowsFromPackages(packageSet, currency, valueKey) {
  return (packageSet?.[currency] || []).map((pkg) => ({
    [valueKey]: pkg[valueKey],
    price: pkg.price,
    prices: pkg.prices ? structuredCloneSafe(pkg.prices) : undefined,
    min_price: pkg.min_price ?? "",
  }));
}

export function draftFromTariff(tariff, defaultCurrency = "rub") {
  const currency = normalizeCurrencyKey(defaultCurrency);
  const defaultPrices = tariff.prices?.[currency] || {};
  const months = new Set([
    ...(tariff.enabled_periods || []),
    ...Object.keys(defaultPrices).map(Number),
    ...(currency === "rub" ? Object.keys(tariff.prices_rub || {}).map(Number) : []),
    ...Object.keys(tariff.prices_stars || {}).map(Number),
  ]);
  const periodRows = [...months]
    .filter((month) => Number.isFinite(month) && month > 0)
    .sort((a, b) => a - b)
    .map((month) => ({
      months: month,
      rub:
        (currency === "rub" ? tariff.prices_rub?.[String(month)] : undefined) ??
        defaultPrices?.[String(month)] ??
        "",
      stars: tariff.prices_stars?.[String(month)] ?? "",
      referral_inviter: tariff.referral_bonus_days_inviter?.[String(month)] ?? "",
      referral_referee: tariff.referral_bonus_days_referee?.[String(month)] ?? "",
    }));

  return {
    ...emptyTariffDraft(),
    defaultCurrency: currency,
    key: tariff.key || "",
    nameRu: tariff.names?.ru || "",
    nameEn: tariff.names?.en || "",
    descriptionRu: tariff.descriptions?.ru || "",
    descriptionEn: tariff.descriptions?.en || "",
    premiumNameRu: tariff.premium_names?.ru || "",
    premiumNameEn: tariff.premium_names?.en || "",
    squadUuids: tariff.squad_uuids || [],
    premiumSquadUuids: tariff.premium_squad_uuids || [],
    billing_model: tariff.billing_model || "period",
    enabled: tariff.enabled !== false,
    monthly_gb: tariff.monthly_gb ?? "",
    premium_monthly_gb: tariff.premium_monthly_gb ?? "",
    hwid_device_limit: tariff.hwid_device_limit ?? "",
    conversion_rate_rub_per_gb: tariff.conversion_rate_rub_per_gb ?? "",
    periodRows: periodRows.length ? periodRows : emptyTariffDraft().periodRows,
    topupRubRows: rowsFromPackages(tariff.topup_packages, currency, "gb"),
    topupStarsRows: rowsFromPackages(tariff.topup_packages, "stars", "gb"),
    premiumTopupRubRows: rowsFromPackages(tariff.premium_topup_packages, currency, "gb"),
    premiumTopupStarsRows: rowsFromPackages(tariff.premium_topup_packages, "stars", "gb"),
    trafficRubRows: rowsFromPackages(tariff.traffic_packages, currency, "gb"),
    trafficStarsRows: rowsFromPackages(tariff.traffic_packages, "stars", "gb"),
    hwidRubRows: rowsFromPackages(tariff.hwid_device_packages, currency, "count"),
    hwidStarsRows: rowsFromPackages(tariff.hwid_device_packages, "stars", "count"),
  };
}

export function parseNumber(value, fallback = null) {
  if (value === "" || value === null || value === undefined) return fallback;
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

export function parseIntNumber(value, fallback = null) {
  const num = parseNumber(value, fallback);
  return num === null ? fallback : Math.trunc(num);
}

export function compactMap(obj) {
  return Object.fromEntries(
    Object.entries(obj).filter(([, value]) => value !== "" && value !== null && value !== undefined)
  );
}

export function packagesFromRows(rows, valueKey) {
  return (rows || [])
    .map((row) => {
      const pkg = {
        [valueKey]: parseNumber(row[valueKey]),
        price: parseNumber(row.price),
      };
      if (row.prices && typeof row.prices === "object") {
        pkg.prices = structuredCloneSafe(row.prices);
      }
      const minPrice = parseNumber(row.min_price);
      if (minPrice !== null) {
        pkg.min_price = minPrice;
      }
      return pkg;
    })
    .filter((row) => row[valueKey] > 0 && row.price !== null && row.price >= 0);
}

export function packageSetFromRows(rubRows, starsRows, valueKey, defaultCurrency = "rub") {
  const currency = normalizeCurrencyKey(defaultCurrency);
  const defaultCurrencyPackages = packagesFromRows(rubRows, valueKey);
  const stars = packagesFromRows(starsRows, valueKey);
  if (!defaultCurrencyPackages.length && !stars.length) return null;
  return {
    ...(defaultCurrencyPackages.length ? { [currency]: defaultCurrencyPackages } : {}),
    ...(stars.length ? { stars } : {}),
  };
}

export function normalizeUuidList(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  return String(value || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function tariffFromDraft(draft, fallbackCurrency = "rub") {
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
  const tariff = {
    key,
    names,
    descriptions,
    premium_names: premiumNames,
    squad_uuids: normalizeUuidList(draft.squadUuids),
    premium_squad_uuids: normalizeUuidList(draft.premiumSquadUuids),
    billing_model: draft.billing_model,
    enabled: Boolean(draft.enabled),
  };

  const hwidLimit = parseIntNumber(draft.hwid_device_limit);
  if (hwidLimit !== null) tariff.hwid_device_limit = hwidLimit;
  const hwidPackages = packageSetFromRows(
    draft.hwidRubRows,
    draft.hwidStarsRows,
    "count",
    defaultCurrency
  );
  if (hwidPackages) tariff.hwid_device_packages = hwidPackages;
  const premiumMonthlyGb = parseNumber(draft.premium_monthly_gb);
  if (premiumMonthlyGb !== null) tariff.premium_monthly_gb = premiumMonthlyGb;
  const premiumTopupPackages = packageSetFromRows(
    draft.premiumTopupRubRows,
    draft.premiumTopupStarsRows,
    "gb",
    defaultCurrency
  );
  if (premiumTopupPackages) tariff.premium_topup_packages = premiumTopupPackages;

  if (tariff.billing_model === "period") {
    const seenMonths = new Set();
    const rows = (draft.periodRows || [])
      .map((row) => ({
        months: parseIntNumber(row.months),
        rub: parseNumber(row.rub, 0),
        stars: parseNumber(row.stars, 0),
        referral_inviter: parseIntNumber(row.referral_inviter),
        referral_referee: parseIntNumber(row.referral_referee),
      }))
      .filter((row) => row.months > 0)
      .filter((row) => {
        if (seenMonths.has(row.months)) return false;
        seenMonths.add(row.months);
        return true;
      })
      .sort((a, b) => a.months - b.months);
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
    const topupPackages = packageSetFromRows(
      draft.topupRubRows,
      draft.topupStarsRows,
      "gb",
      defaultCurrency
    );
    if (topupPackages) tariff.topup_packages = topupPackages;
  } else {
    const trafficPackages = packageSetFromRows(
      draft.trafficRubRows,
      draft.trafficStarsRows,
      "gb",
      defaultCurrency
    );
    if (trafficPackages) tariff.traffic_packages = trafficPackages;
    const conversion = parseNumber(draft.conversion_rate_rub_per_gb);
    if (conversion !== null) tariff.conversion_rate_rub_per_gb = conversion;
  }

  return tariff;
}
