import { describe, expect, it } from "vitest";

import {
  activeTariffName,
  buildTariffCatalog,
  checkoutTariffSummary,
  firstAvailableMethod,
  initialCheckoutTariffKey,
  methodSelectable,
  methodsForPlan,
  paymentMethodMinimum,
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

  it("skips the tariff picker when only one public tariff is available", () => {
    const catalog = buildTariffCatalog([{ tariff_key: "standard", tariff_name: "Standard" }]);

    expect(initialCheckoutTariffKey(catalog, null)).toBe("standard");
    expect(
      initialCheckoutTariffKey(
        buildTariffCatalog([{ tariff_key: "standard" }, { tariff_key: "plus" }]),
        null
      )
    ).toBe("");
    expect(
      initialCheckoutTariffKey(
        buildTariffCatalog([{ tariff_key: "standard" }, { tariff_key: "plus" }]),
        { tariff_key: "plus" }
      )
    ).toBe("plus");
  });

  it("builds a checkout tariff summary with finite and unlimited limits", () => {
    expect(
      checkoutTariffSummary({
        effective_hwid_device_limit: 5,
        monthly_gb: 0,
        premium_enabled: true,
        premium_monthly_gb: 50,
        premium_unlimited: false,
      })
    ).toEqual({
      devices: { known: true, units: 5, unlimited: false },
      traffic: { known: true, units: 0, unlimited: true },
      premiumTraffic: { known: true, units: 50, unlimited: false },
    });

    expect(
      checkoutTariffSummary({
        hwid_device_limit: 0,
        monthly_gb: 100,
        premium_enabled: true,
        premium_monthly_gb: null,
        premium_unlimited: true,
      })
    ).toEqual({
      devices: { known: true, units: 0, unlimited: true },
      traffic: { known: true, units: 100, unlimited: false },
      premiumTraffic: { known: true, units: 0, unlimited: true },
    });
  });

  it("hides fully disabled premium traffic without hiding configurable limits", () => {
    expect(checkoutTariffSummary({ premium_enabled: false }).premiumTraffic).toEqual({
      known: false,
      units: 0,
      unlimited: false,
    });
    expect(checkoutTariffSummary({}).premiumTraffic).toEqual({
      known: false,
      units: 0,
      unlimited: false,
    });
    expect(
      checkoutTariffSummary({
        premium_enabled: false,
        checkout_addons: {
          premium_traffic: {
            kind: "premium_traffic",
            base_units: 0,
            max_total_units: 100,
            options: [
              { extra_units: 0, total_units: 0, price: 0 },
              { extra_units: 50, total_units: 50, price: 100 },
            ],
          },
        },
      }).premiumTraffic
    ).toEqual({
      known: true,
      units: 0,
      unlimited: false,
    });
    expect(
      checkoutTariffSummary({ premium_enabled: true, premium_monthly_gb: 0 }).premiumTraffic
    ).toEqual({
      known: true,
      units: 0,
      unlimited: false,
    });
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
    expect(
      paymentMethodMinimum({
        id: "bank",
        minimum_amount: "500",
        shop_limit_currency: "rub",
      })
    ).toEqual({ amount: 500, currency: "RUB", text: "" });
    expect(
      methodsForPlan([{ id: "bank", minimum_amount: 700, shop_limit_currency: "USD" }], plan)[0]
    ).toMatchObject({ disabled: true });
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

  it("limits payment methods to those available for the selected plan", () => {
    const methods = [{ id: "card" }, { id: "tribute" }, { id: "stars" }];
    const plan = {
      tariff_key: "pro",
      months: 1,
      available_payment_method_ids: ["card", "tribute"],
    };

    expect(methodsForPlan(methods, plan)).toEqual([
      { id: "card", disabled: false },
      { id: "tribute", disabled: false },
      { id: "stars", disabled: true },
    ]);
    expect(methodsForPlan(methods, { ...plan, available_payment_method_ids: [] })).toEqual([
      { id: "card", disabled: true },
      { id: "tribute", disabled: true },
      { id: "stars", disabled: true },
    ]);
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
