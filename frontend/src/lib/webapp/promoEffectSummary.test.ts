import { describe, expect, it } from "vitest";

import { createI18n } from "./i18n.js";
import { formatPromoEffectSummary } from "./promoEffectSummary.js";

const i18n = createI18n({
  defaultLang: "ru",
  messages: {
    ru: {
      wa_promo_effect_bonus_days: "+{value} {unit}",
      wa_promo_effect_regular_traffic: "+{value} ГБ обычного трафика",
      wa_promo_effect_premium_traffic: "+{value} ГБ премиум-трафика",
      wa_promo_effect_discount: "Скидка {value}%",
      wa_promo_effect_duration_multiplier: "Срок ×{value}",
      wa_promo_effect_traffic_multiplier: "Трафик ×{value}",
      wa_promo_condition_min_term: "От {value} {unit}",
      wa_promo_condition_min_traffic: "От {value} ГБ",
      wa_sub_term_day_one: "день",
      wa_sub_term_day_few: "дня",
      wa_sub_term_day_many: "дней",
    },
  },
});

describe("formatPromoEffectSummary", () => {
  it.each([
    [1, "+1 день"],
    [2, "+2 дня"],
    [3, "+3 дня"],
    [5, "+5 дней"],
    [11, "+11 дней"],
    [21, "+21 день"],
  ])("localizes a %i-day bonus", (bonusDays, expected) => {
    expect(
      formatPromoEffectSummary(
        { bonus_days: bonusDays, effect_summary: `+${bonusDays} days` },
        i18n
      )
    ).toBe(expected);
  });

  it("localizes regular and premium traffic grants in a combined effect", () => {
    expect(
      formatPromoEffectSummary(
        {
          bonus_days: 3,
          regular_traffic_gb: 5.5,
          premium_traffic_gb: 2,
          effect_summary: "+3 days, +5.5 GB regular, +2 GB premium",
        },
        i18n
      )
    ).toBe("+3 дня, +5.5 ГБ обычного трафика, +2 ГБ премиум-трафика");
  });

  it("keeps the backend summary when structured effect fields are unavailable", () => {
    expect(formatPromoEffectSummary({ effect_summary: "Custom effect" }, i18n)).toBe(
      "Custom effect"
    );
  });

  it("localizes checkout effects and the exact minimum term in days", () => {
    expect(
      formatPromoEffectSummary(
        {
          discount_percent: 25,
          min_subscription_days: 90,
          effect_summary: "-25%, from 90 days",
        },
        i18n
      )
    ).toBe("Скидка 25%, От 90 дней");
  });
});
