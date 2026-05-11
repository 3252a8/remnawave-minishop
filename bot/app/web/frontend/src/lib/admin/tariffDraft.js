import { structuredCloneSafe } from "./format.js";

export function emptyTariffDraft() {
  return {
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
      { months: 1, rub: 150, stars: "" },
      { months: 3, rub: 400, stars: "" },
      { months: 6, rub: 750, stars: "" },
      { months: 12, rub: 1400, stars: "" },
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
    topup_packages_default: catalog?.topup_packages_default || { rub: [], stars: [] },
    tariffs: catalog?.tariffs || [],
  });
}

export function rowsFromPackages(packageSet, currency, valueKey) {
  return (packageSet?.[currency] || []).map((pkg) => ({
    [valueKey]: pkg[valueKey],
    price: pkg.price,
  }));
}

export function draftFromTariff(tariff) {
  const months = new Set([
    ...(tariff.enabled_periods || []),
    ...Object.keys(tariff.prices_rub || {}).map(Number),
    ...Object.keys(tariff.prices_stars || {}).map(Number),
  ]);
  const periodRows = [...months]
    .filter((month) => Number.isFinite(month) && month > 0)
    .sort((a, b) => a - b)
    .map((month) => ({
      months: month,
      rub: tariff.prices_rub?.[String(month)] ?? "",
      stars: tariff.prices_stars?.[String(month)] ?? "",
    }));

  return {
    ...emptyTariffDraft(),
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
    topupRubRows: rowsFromPackages(tariff.topup_packages, "rub", "gb"),
    topupStarsRows: rowsFromPackages(tariff.topup_packages, "stars", "gb"),
    premiumTopupRubRows: rowsFromPackages(tariff.premium_topup_packages, "rub", "gb"),
    premiumTopupStarsRows: rowsFromPackages(tariff.premium_topup_packages, "stars", "gb"),
    trafficRubRows: rowsFromPackages(tariff.traffic_packages, "rub", "gb"),
    trafficStarsRows: rowsFromPackages(tariff.traffic_packages, "stars", "gb"),
    hwidRubRows: rowsFromPackages(tariff.hwid_device_packages, "rub", "count"),
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
    Object.entries(obj).filter(([, value]) => value !== "" && value !== null && value !== undefined),
  );
}

export function packagesFromRows(rows, valueKey) {
  return (rows || [])
    .map((row) => ({
      [valueKey]: parseNumber(row[valueKey]),
      price: parseNumber(row.price),
    }))
    .filter((row) => row[valueKey] > 0 && row.price !== null && row.price >= 0);
}

export function packageSetFromRows(rubRows, starsRows, valueKey) {
  const rub = packagesFromRows(rubRows, valueKey);
  const stars = packagesFromRows(starsRows, valueKey);
  return rub.length || stars.length ? { rub, stars } : null;
}

export function normalizeUuidList(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  return String(value || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function tariffFromDraft(draft) {
  const key = draft.key.trim();
  const names = compactMap({ ru: draft.nameRu.trim(), en: draft.nameEn.trim() });
  const descriptions = compactMap({ ru: draft.descriptionRu.trim(), en: draft.descriptionEn.trim() });
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
  const hwidPackages = packageSetFromRows(draft.hwidRubRows, draft.hwidStarsRows, "count");
  if (hwidPackages) tariff.hwid_device_packages = hwidPackages;
  const premiumMonthlyGb = parseNumber(draft.premium_monthly_gb);
  if (premiumMonthlyGb !== null) tariff.premium_monthly_gb = premiumMonthlyGb;
  const premiumTopupPackages = packageSetFromRows(
    draft.premiumTopupRubRows,
    draft.premiumTopupStarsRows,
    "gb",
  );
  if (premiumTopupPackages) tariff.premium_topup_packages = premiumTopupPackages;

  if (tariff.billing_model === "period") {
    const seenMonths = new Set();
    const rows = (draft.periodRows || [])
      .map((row) => ({
        months: parseIntNumber(row.months),
        rub: parseNumber(row.rub, 0),
        stars: parseNumber(row.stars, 0),
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
    tariff.prices_rub = Object.fromEntries(rows.map((row) => [String(row.months), row.rub || 0]));
    tariff.prices_stars = Object.fromEntries(rows.map((row) => [String(row.months), row.stars || 0]));
    const topupPackages = packageSetFromRows(draft.topupRubRows, draft.topupStarsRows, "gb");
    if (topupPackages) tariff.topup_packages = topupPackages;
  } else {
    const trafficPackages = packageSetFromRows(draft.trafficRubRows, draft.trafficStarsRows, "gb");
    if (trafficPackages) tariff.traffic_packages = trafficPackages;
    const conversion = parseNumber(draft.conversion_rate_rub_per_gb);
    if (conversion !== null) tariff.conversion_rate_rub_per_gb = conversion;
  }

  return tariff;
}
