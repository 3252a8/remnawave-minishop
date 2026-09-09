import { describe, expect, it } from "vitest";
import { checkoutUnitPrice } from "./checkoutUnitPrice";
import { planUnitHint } from "./tariffs";
import { activeSubscriptionTermLabel } from "./traffic";
import { unitPluralBucket } from "./plurals";
import ru from "../../../../locales/ru.json";

const translate = (key: string, params?: Record<string, unknown>) =>
  Object.entries(params || {}).reduce(
    (text, [name, value]) => text.replace(`{${name}}`, String(value)),
    (ru as Record<string, string>)[key] || key
  );
const termUnitLabel = (count: number, unit: string) =>
  translate(`wa_sub_term_${unit}_${unitPluralBucket(count, "ru")}`);

describe("checkout period display", () => {
  it.each([1, 7, 29])("hides the monthly rate for %i days", (days) => {
    const plan = { duration_days: days, price: 100, stars_price: 50 };
    expect(checkoutUnitPrice(plan, plan, false, false)).toBeNull();
    expect(checkoutUnitPrice(plan, plan, false, true)).toBeNull();
    expect(planUnitHint(plan, { trafficMode: false, selectedMethod: "card", t: translate })).toBe(
      ""
    );
  });
  it("separates the monthly label from the price and keeps the 30-day calculation", () => {
    const plan = { duration_days: 60, price: 380, currency: "RUB" };
    expect(checkoutUnitPrice(plan, plan, false, false)?.price).toBe(190);
    expect(
      planUnitHint(plan, { trafficMode: false, selectedMethod: "card", t: translate })
    ).toMatch(/\sза месяц$/);
  });
  it("keeps traffic unit rates for small packages", () => {
    const plan = { traffic_gb: 7, price: 70 };
    expect(checkoutUnitPrice(plan, plan, true, false)?.price).toBe(10);
  });
  it.each([
    [0, "0 дней"],
    [1, "1 день"],
    [29, "29 дней"],
    [30, "1 месяц"],
    [45, "1.5 месяца"],
    [165, "5.5 месяца"],
    [364, "12 месяцев"],
    [365, "1 год"],
    [548, "1.5 года"],
    [730, "2 года"],
    [1825, "5 лет"],
    [4364, "12 лет"],
    [Number.NaN, "0 дней"],
  ])("adapts the remaining %s days to a readable status", (days, expected) => {
    expect(activeSubscriptionTermLabel({ days_left: days }, { t: translate, termUnitLabel })).toBe(
      expected
    );
  });
});
