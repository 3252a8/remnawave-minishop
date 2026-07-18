import { describe, expect, it } from "vitest";

import {
  activeTariffName,
  buildTariffCatalog,
  firstAvailableMethod,
  methodSelectable,
  methodsForPlan,
  paymentMethodsForContext,
  planDisplayTitle,
  planKey,
  planSubtitle,
  planUnitHint,
  priceLabel,
  tariffLimitLabel,
  TELEGRAM_STARS_MINI_APP_REQUIRED,
} from "./tariffs.js";

describe("webapp tariff helpers", () => {
  const t = (key: string, params: Record<string, unknown> = {}) =>
    `${key}:${JSON.stringify(params)}`;
  const termUnitLabel = (value: unknown, unit: unknown) => `${value} ${unit}`;

  it("groups plans into a tariff catalog", () => {
    expect(
      buildTariffCatalog([
        {
          tariff_key: "pro",
          tariff_name: "Pro",
          description: "Fast",
          monthly_gb: 500,
          is_default_tariff: true,
          months: 1,
        },
        {
          tariff_key: "pro",
          sale_mode: "traffic_package",
          traffic_gb: 50,
          months: 0,
        },
        {
          tariff_key: "traffic",
          title: "Traffic",
          sale_mode: "traffic",
          traffic_gb: "10",
        },
      ])
    ).toEqual([
      {
        key: "pro",
        title: "Pro",
        description: "Fast",
        billing_model: "period",
        is_default: true,
        monthly_gb: 500,
        traffic_packages: [50],
        plans_count: 2,
      },
      {
        key: "traffic",
        title: "Traffic",
        description: "",
        billing_model: "traffic",
        is_default: false,
        monthly_gb: 0,
        traffic_packages: [10],
        plans_count: 1,
      },
    ]);
  });

  it("formats plan identity, prices and method availability", () => {
    const plan = {
      tariff_key: "pro",
      sale_mode: "subscription",
      months: 3,
      price: 600,
      currency: "USD",
      stars_price: 250,
    };

    expect(planKey(plan)).toBe("pro:subscription:3");
    expect(priceLabel(plan, "telegram-stars")).toBe("250 ⭐");
    expect(priceLabel(plan, "card")).toBe("600 USD");
    expect(methodsForPlan([{ id: "card", min_amount: 700, min_currency: "USD" }], plan)).toEqual([
      { id: "card", min_amount: 700, min_currency: "USD", disabled: true },
    ]);
    expect(firstAvailableMethod([{ id: "card", disabled: true }, { id: "stars" }])).toBe("stars");
    expect(methodSelectable([{ id: "card" }], "card")).toBe(true);
  });

  it("disables Stars outside Telegram without changing other payment methods", () => {
    const methods = [{ id: "telegram-stars" }, { id: "yookassa" }];

    expect(paymentMethodsForContext(methods, false)).toEqual([
      {
        id: "telegram-stars",
        disabled: true,
        disabled_reason: TELEGRAM_STARS_MINI_APP_REQUIRED,
      },
      { id: "yookassa" },
    ]);
    expect(paymentMethodsForContext(methods, true)).toEqual(methods);
    expect(methodsForPlan(paymentMethodsForContext(methods, false), null)[0]).toMatchObject({
      disabled: true,
      disabled_reason: TELEGRAM_STARS_MINI_APP_REQUIRED,
    });
  });

  it("builds display labels for active and selectable tariffs", () => {
    expect(activeTariffName({ tariff_key: "pro" }, [{ tariff_key: "pro", title: "Pro" }])).toBe(
      "Pro"
    );
    expect(tariffLimitLabel({ billing_model: "traffic", traffic_packages: [50, 10] }, { t })).toBe(
      "10 GB - 50 GB"
    );
    expect(tariffLimitLabel({ billing_model: "period", monthly_gb: 500 }, { t })).toBe("500 GB");
    expect(planDisplayTitle({ months: 12 }, { trafficMode: false, t })).toBe("wa_plan_one_year:{}");
    expect(planSubtitle({ tariff_key: "pro", months: 3 }, { t, termUnitLabel })).toBe(
      'wa_sub_term_value_unit:{"value":"3","unit":"3 month"}'
    );
    expect(
      planUnitHint(
        { sale_mode: "traffic_package", traffic_gb: 10, price: 100, currency: "USD" },
        { trafficMode: false, selectedMethod: "card", t: () => "/GB" }
      )
    ).toBe("10 USD/GB");
  });
});
