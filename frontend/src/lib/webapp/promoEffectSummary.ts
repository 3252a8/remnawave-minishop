import { formatCompactNumber } from "./formatters.js";
import type { TermUnitLabel } from "./types.js";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

type PromoEffectSummaryDeps = {
  t: Translate;
  termUnitLabel: TermUnitLabel;
};

function positiveNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function nonDefaultMultiplier(value: unknown): number | null {
  const numeric = positiveNumber(value);
  return numeric !== null && numeric !== 1 ? numeric : null;
}

export function formatPromoEffectSummary(
  payload: Record<string, unknown>,
  { t, termUnitLabel }: PromoEffectSummaryDeps
): string {
  const parts: string[] = [];
  const bonusDays = positiveNumber(payload.bonus_days);
  const regularTrafficGb = positiveNumber(payload.regular_traffic_gb);
  const premiumTrafficGb = positiveNumber(payload.premium_traffic_gb);
  const discountPercent = positiveNumber(payload.discount_percent);
  const durationMultiplier = nonDefaultMultiplier(payload.duration_multiplier);
  const trafficMultiplier = nonDefaultMultiplier(payload.traffic_multiplier);
  const minSubscriptionDays = positiveNumber(payload.min_subscription_days);
  const minSubscriptionMonths = positiveNumber(payload.min_subscription_months);
  const minTrafficGb = positiveNumber(payload.min_traffic_gb);

  if (discountPercent !== null) {
    parts.push(
      t(
        "wa_promo_effect_discount",
        { value: formatCompactNumber(discountPercent) },
        "{value}% discount"
      )
    );
  }
  if (durationMultiplier !== null) {
    parts.push(
      t(
        "wa_promo_effect_duration_multiplier",
        { value: formatCompactNumber(durationMultiplier) },
        "Duration ×{value}"
      )
    );
  }
  if (trafficMultiplier !== null) {
    parts.push(
      t(
        "wa_promo_effect_traffic_multiplier",
        { value: formatCompactNumber(trafficMultiplier) },
        "Traffic ×{value}"
      )
    );
  }

  if (bonusDays !== null) {
    parts.push(
      t(
        "wa_promo_effect_bonus_days",
        {
          value: formatCompactNumber(bonusDays),
          unit: termUnitLabel(bonusDays, "day"),
        },
        "+{value} {unit}"
      )
    );
  }
  if (regularTrafficGb !== null) {
    parts.push(
      t(
        "wa_promo_effect_regular_traffic",
        { value: formatCompactNumber(regularTrafficGb) },
        "+{value} GB regular traffic"
      )
    );
  }
  if (premiumTrafficGb !== null) {
    parts.push(
      t(
        "wa_promo_effect_premium_traffic",
        { value: formatCompactNumber(premiumTrafficGb) },
        "+{value} GB premium traffic"
      )
    );
  }

  const minTermValue = minSubscriptionDays ?? minSubscriptionMonths;
  if (minTermValue !== null) {
    const unit = minSubscriptionDays !== null ? "day" : "month";
    parts.push(
      t(
        "wa_promo_condition_min_term",
        {
          value: formatCompactNumber(minTermValue),
          unit: termUnitLabel(minTermValue, unit),
        },
        "From {value} {unit}"
      )
    );
  }
  if (minTrafficGb !== null) {
    parts.push(
      t(
        "wa_promo_condition_min_traffic",
        { value: formatCompactNumber(minTrafficGb) },
        "From {value} GB"
      )
    );
  }

  return parts.length ? parts.join(", ") : String(payload.effect_summary || "").trim();
}
