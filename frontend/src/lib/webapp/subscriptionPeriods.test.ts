import { describe, expect, it } from "vitest";
import {
  billingDurationDays,
  durationParts,
  formatDurationDays,
  legacyMonthsToDays,
  daysToLegacyMonths,
} from "./subscriptionPeriods";
import {
  parseDurationDays,
  normalizeDayTariff,
  preserveInactivePeriodMetadata,
} from "../admin/tariffPeriods";
import { checkoutPromoMatchesPlan } from "./checkoutPromoPolicy";
import ru from "../../../../locales/ru.json";
import en from "../../../../locales/en.json";

describe("day subscription periods", () => {
  it.each([
    [1, 30],
    [12, 365],
    [13, 395],
    [18, 545],
    [24, 730],
  ])("converts %i legacy months to %i days", (months, days) => {
    expect(legacyMonthsToDays(months)).toBe(days);
    expect(daysToLegacyMonths(days)).toBe(months);
  });
  it("keeps 360 days distinct from a year and prioritizes years", () => {
    expect(durationParts(360)).toEqual({ count: 12, unit: "month" });
    expect(durationParts(365)).toEqual({ count: 1, unit: "year" });
    expect(durationParts(10950)).toEqual({ count: 30, unit: "year" });
    expect(daysToLegacyMonths(360)).toBeNull();
    expect(billingDurationDays({ duration_days: 7, months: 1 })).toBe(7);
  });
  it.each([
    [1, "1 день"],
    [11, "11 дней"],
    [21, "21 день"],
    [22, "22 дня"],
    [25, "25 дней"],
    [30, "1 месяц"],
    [60, "2 месяца"],
    [150, "5 месяцев"],
    [365, "1 год"],
    [730, "2 года"],
    [1825, "5 лет"],
    [4015, "11 лет"],
    [7665, "21 год"],
  ])("formats Russian %i days", (days, text) => {
    expect(formatDurationDays(days, (key) => (ru as Record<string, string>)[key], "ru")).toBe(text);
  });
  it.each([
    [1, "1 day"],
    [7, "7 days"],
    [30, "1 month"],
    [60, "2 months"],
    [365, "1 year"],
    [730, "2 years"],
  ])("formats English %i days", (days, text) => {
    expect(formatDurationDays(days, (key) => (en as Record<string, string>)[key], "en")).toBe(text);
  });
  it.each([true, false, 0, -1, 1.5, "1.5", "1e3", "", null, 2147483648])(
    "rejects invalid admin input %s",
    (value) => {
      expect(parseDurationDays(value)).toBeNull();
    }
  );
  it("preserves annual prices, bonus days and all currencies when editing old catalogs", () => {
    const old = {
      billing_model: "period",
      enabled_periods: [12],
      prices: { usd: { 12: 10 } },
      referral_bonus_days_inviter: { 12: 7 },
      hwid_device_packages: { rub: [{ price: 5 }] },
    };
    const migrated = normalizeDayTariff(old);
    expect(migrated).toMatchObject({
      period_unit: "day",
      prices: { usd: { 365: 10 } },
      referral_bonus_days_inviter: { 365: 7 },
      hwid_device_packages: { rub: [{ prices: { 365: 60 } }] },
    });
    expect(normalizeDayTariff(migrated)).toEqual(migrated);
    expect(old.enabled_periods).toEqual([12]);
  });
  it("compares promo thresholds to paid days without adding bonuses", () => {
    expect(checkoutPromoMatchesPlan({ duration_days: 360 }, "subscription", 365, null)).toBe(false);
    expect(checkoutPromoMatchesPlan({ duration_days: 365 }, "subscription", 365, null)).toBe(true);
  });
  it("keeps disabled period prices, bonuses and external IDs when editing a catalog", () => {
    const current = {
      billing_model: "period",
      enabled_periods: [30],
      prices_rub: { 30: 200 },
      prices: { usd: { 30: 2 } },
      referral_bonus_days_inviter: { 30: 1 },
    };
    preserveInactivePeriodMetadata(current, {
      prices_rub: { 30: 100, 365: 1000 },
      prices: { usd: { 30: 1, 365: 10 } },
      referral_bonus_days_inviter: { 30: 5, 365: 7 },
      tribute: { period_ids: { 365: 99 } },
    });
    expect(current).toMatchObject({
      prices_rub: { 30: 200, 365: 1000 },
      prices: { usd: { 30: 2, 365: 10 } },
      referral_bonus_days_inviter: { 30: 1, 365: 7 },
      tribute: { period_ids: { 365: 99 } },
    });
  });
});
