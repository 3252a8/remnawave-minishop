import { structuredCloneSafe } from "./format.js";
import { legacyMonthsToDays, durationParts } from "../webapp/subscriptionPeriods";

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as RecordValue) : {};

export function parseDurationDays(value: unknown): number | null {
  if (typeof value !== "number" && (typeof value !== "string" || !/^\d+$/.test(value.trim())))
    return null;
  const days = Number(value);
  return Number.isInteger(days) && days > 0 && days <= 2147483647 ? days : null;
}

export function normalizeDayTariff(source: RecordValue): RecordValue {
  const tariff = structuredCloneSafe(source) as RecordValue;
  if ((tariff.billing_model || "period") !== "period" || tariff.period_unit === "day")
    return tariff;
  const convert = (value: unknown): RecordValue =>
    Object.fromEntries(
      Object.entries(record(value)).map(([key, item]) => [String(legacyMonthsToDays(key)), item])
    );
  const periods = Array.isArray(tariff.enabled_periods) ? tariff.enabled_periods : [];
  tariff.enabled_periods = periods.map(legacyMonthsToDays);
  tariff.period_unit = "day";
  tariff.addon_period_factors = Object.fromEntries(
    periods.map((period) => [String(legacyMonthsToDays(period)), period])
  );
  for (const field of [
    "prices_rub",
    "prices_stars",
    "referral_bonus_days_inviter",
    "referral_bonus_days_referee",
  ]) {
    if (field in tariff) tariff[field] = convert(tariff[field]);
  }
  tariff.prices = Object.fromEntries(
    Object.entries(record(tariff.prices)).map(([currency, prices]) => [currency, convert(prices)])
  );
  if (tariff.tribute) {
    const tribute = record(tariff.tribute);
    for (const field of ["period_ids", "period_links", "period_subscription_ids"]) {
      if (field in tribute) tribute[field] = convert(tribute[field]);
    }
    tribute.period_unit = "day";
  }
  for (const packages of Object.values(record(tariff.hwid_device_packages))) {
    if (!Array.isArray(packages)) continue;
    for (const value of packages) {
      const pkg = record(value);
      pkg.prices = {
        ...Object.fromEntries(
          periods.map((period) => [
            String(legacyMonthsToDays(period)),
            Number(pkg.price || 0) * Number(period),
          ])
        ),
        ...convert(pkg.prices),
      };
      pkg.period_unit = "day";
    }
  }
  return tariff;
}

export function adminDurationLabel(
  value: unknown,
  at: (key: string, params?: Record<string, unknown>, fallback?: string) => string
): string {
  const parts = durationParts(value);
  if (!parts) return "";
  const language = at("period_plural_locale", {}, "en");
  const category = new Intl.PluralRules(language).select(parts.count);
  const form = category === "one" || category === "few" ? category : "many";
  return at(
    `period_${parts.unit}_${form}`,
    { count: parts.count },
    `${parts.count} ${parts.unit}(s)`
  );
}

/** Disabling a period keeps its dormant prices and external bindings available for history. */
export function preserveInactivePeriodMetadata(tariff: RecordValue, original: RecordValue): void {
  if (tariff.billing_model !== "period") return;
  const active = new Set(((tariff.enabled_periods as number[]) || []).map(String));
  const merge = (old: unknown, current: unknown): RecordValue => ({
    ...Object.fromEntries(Object.entries(record(old)).filter(([key]) => !active.has(key))),
    ...record(current),
  });
  for (const field of [
    "prices_rub",
    "prices_stars",
    "referral_bonus_days_inviter",
    "referral_bonus_days_referee",
  ]) {
    tariff[field] = merge(original[field], tariff[field]);
  }
  const prices = record(tariff.prices);
  for (const [currency, oldPrices] of Object.entries(record(original.prices))) {
    prices[currency] = merge(oldPrices, prices[currency]);
  }
  tariff.prices = prices;
  const tribute = record(tariff.tribute);
  const previous = record(original.tribute);
  for (const field of ["period_ids", "period_links", "period_subscription_ids"]) {
    const entries = merge(previous[field], tribute[field]);
    if (Object.keys(entries).length) tribute[field] = entries;
  }
  if (Object.keys(tribute).length) tariff.tribute = { ...tribute, period_unit: "day" };
}
