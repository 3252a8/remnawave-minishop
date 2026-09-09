import { describe, expect, it } from "vitest";

import en from "../../../../locales/en.json";
import ru from "../../../../locales/ru.json";
import { createI18n } from "../webapp/i18n";
import { formatAdminPromoEffect, formatAdminPromoEligibility } from "./promoEffectDisplay";

function adminTranslate(language: "en" | "ru") {
  const { t } = createI18n({ messages: { ru, en }, defaultLang: language });
  return (key: string, params: Record<string, unknown> = {}, fallback = "") =>
    t(`admin_${key}`, params, fallback);
}

describe("formatAdminPromoEffect", () => {
  it.each([
    [{ bonus_days: 7 }, "+7 дн.", "+7 d"],
    [{ regular_traffic_gb: 50 }, "+50 ГБ обычного трафика", "+50 GB regular traffic"],
    [{ premium_traffic_gb: 20 }, "+20 ГБ премиум-трафика", "+20 GB premium traffic"],
    [{ discount_percent: 25 }, "Скидка 25%", "25% discount"],
    [{ duration_multiplier: 2 }, "Срок ×2", "Duration ×2"],
    [{ traffic_multiplier: 1.5 }, "Трафик ×1.5", "Traffic ×1.5"],
  ])("localizes every supported effect %#", (effect, expectedRu, expectedEn) => {
    expect(formatAdminPromoEffect(effect, adminTranslate("ru"))).toBe(expectedRu);
    expect(formatAdminPromoEffect(effect, adminTranslate("en"))).toBe(expectedEn);
  });

  it("keeps purchase conditions out of the effect and labels the grant mode", () => {
    expect(
      formatAdminPromoEffect(
        {
          bonus_days: 7,
          discount_percent: 25,
          bonus_requires_payment: true,
          min_subscription_days: 90,
          effect_summary: "-25%, +7 days, from 90 days",
        },
        adminTranslate("ru"),
        { includeGrantMode: true }
      )
    ).toBe("+7 дн., Скидка 25% · после оплаты");
  });

  it("localizes known legacy summaries without leaking their conditions", () => {
    expect(
      formatAdminPromoEffect(
        {
          effect_summary:
            "-25%, x2 duration, x1.5 traffic, +7 days, +5.5 GB regular, +2 GB premium, from 90 days",
        },
        adminTranslate("ru")
      )
    ).toBe(
      "+7 дн., +5.5 ГБ обычного трафика, +2 ГБ премиум-трафика, Скидка 25%, Срок ×2, Трафик ×1.5"
    );
  });
});

describe("formatAdminPromoEligibility", () => {
  it("uses days for the current subscription threshold field", () => {
    expect(formatAdminPromoEligibility({ min_subscription_days: 90 }, adminTranslate("ru"))).toBe(
      "от 90 дн."
    );
  });

  it("supports legacy month and traffic thresholds", () => {
    expect(
      formatAdminPromoEligibility(
        { min_subscription_months: 3, min_traffic_gb: 12.5 },
        adminTranslate("ru")
      )
    ).toBe("от 3 мес., от 12.5 ГБ");
  });
});
