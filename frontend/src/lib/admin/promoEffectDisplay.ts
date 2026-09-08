export type AdminTranslate = (
  key: string,
  params?: Record<string, unknown>,
  fallback?: string
) => string;

export type PromoEffectSource = {
  bonus_days?: number | string | null;
  regular_traffic_gb?: number | string | null;
  premium_traffic_gb?: number | string | null;
  discount_percent?: number | string | null;
  duration_multiplier?: number | string | null;
  traffic_multiplier?: number | string | null;
  bonus_requires_payment?: boolean | null;
  min_subscription_days?: number | string | null;
  min_subscription_months?: number | string | null;
  min_traffic_gb?: number | string | null;
  effect_summary?: string | null;
};

type EffectValues = {
  bonusDays: number | null;
  regularTrafficGb: number | null;
  premiumTrafficGb: number | null;
  discountPercent: number | null;
  durationMultiplier: number | null;
  trafficMultiplier: number | null;
};

function positiveNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function multiplier(value: unknown): number | null {
  const parsed = positiveNumber(value);
  return parsed !== null && parsed > 1 ? parsed : null;
}

function numberText(value: number): string {
  return String(Math.round(value * 1000) / 1000);
}

function explicitEffectValues(source: PromoEffectSource): EffectValues {
  return {
    bonusDays: positiveNumber(source.bonus_days),
    regularTrafficGb: positiveNumber(source.regular_traffic_gb),
    premiumTrafficGb: positiveNumber(source.premium_traffic_gb),
    discountPercent: positiveNumber(source.discount_percent),
    durationMultiplier: multiplier(source.duration_multiplier),
    trafficMultiplier: multiplier(source.traffic_multiplier),
  };
}

function hasEffect(values: EffectValues): boolean {
  return Object.values(values).some((value) => value !== null);
}

/**
 * Older activation rows may only have the backend's frozen English summary.
 * Recover its known effect tokens so they can still use the current locale,
 * while deliberately leaving eligibility tokens out of the effect column.
 */
function legacyEffectValues(summary: unknown): EffectValues | null {
  const values = explicitEffectValues({});
  for (const token of String(summary || "")
    .split(",")
    .map((part) => part.trim())) {
    let match = token.match(/^\+([\d.]+) days$/i);
    if (match) {
      values.bonusDays = positiveNumber(match[1]);
      continue;
    }
    match = token.match(/^\+([\d.]+) GB regular$/i);
    if (match) {
      values.regularTrafficGb = positiveNumber(match[1]);
      continue;
    }
    match = token.match(/^\+([\d.]+) GB premium$/i);
    if (match) {
      values.premiumTrafficGb = positiveNumber(match[1]);
      continue;
    }
    match = token.match(/^-([\d.]+)%$/);
    if (match) {
      values.discountPercent = positiveNumber(match[1]);
      continue;
    }
    match = token.match(/^[x×]([\d.]+) duration$/i);
    if (match) {
      values.durationMultiplier = multiplier(match[1]);
      continue;
    }
    match = token.match(/^[x×]([\d.]+) traffic$/i);
    if (match) values.trafficMultiplier = multiplier(match[1]);
  }
  return hasEffect(values) ? values : null;
}

function resolvedEffectValues(source: PromoEffectSource): EffectValues | null {
  const explicit = explicitEffectValues(source);
  return hasEffect(explicit) ? explicit : legacyEffectValues(source.effect_summary);
}

export function formatAdminPromoEffect(
  source: PromoEffectSource,
  at: AdminTranslate,
  { includeGrantMode = false }: { includeGrantMode?: boolean } = {}
): string {
  const values = resolvedEffectValues(source);
  if (!values) return String(source.effect_summary || "").trim() || "-";

  const parts: string[] = [];
  if (values.bonusDays !== null) {
    parts.push(
      at("promo_effect_bonus_days_value", { value: numberText(values.bonusDays) }, "+{value} d")
    );
  }
  if (values.regularTrafficGb !== null) {
    parts.push(
      at(
        "promo_effect_regular_traffic_value",
        { value: numberText(values.regularTrafficGb) },
        "+{value} GB regular traffic"
      )
    );
  }
  if (values.premiumTrafficGb !== null) {
    parts.push(
      at(
        "promo_effect_premium_traffic_value",
        { value: numberText(values.premiumTrafficGb) },
        "+{value} GB premium traffic"
      )
    );
  }
  if (values.discountPercent !== null) {
    parts.push(
      at(
        "promo_effect_discount_value",
        { value: numberText(values.discountPercent) },
        "{value}% discount"
      )
    );
  }
  if (values.durationMultiplier !== null) {
    parts.push(
      at(
        "promo_effect_duration_multiplier_value",
        { value: numberText(values.durationMultiplier) },
        "Duration ×{value}"
      )
    );
  }
  if (values.trafficMultiplier !== null) {
    parts.push(
      at(
        "promo_effect_traffic_multiplier_value",
        { value: numberText(values.trafficMultiplier) },
        "Traffic ×{value}"
      )
    );
  }

  const text = parts.join(", ");
  const hasFixedGrant =
    values.bonusDays !== null ||
    values.regularTrafficGb !== null ||
    values.premiumTrafficGb !== null;
  if (!includeGrantMode || !hasFixedGrant) return text;

  const usesCheckout =
    Boolean(source.bonus_requires_payment) ||
    values.discountPercent !== null ||
    values.durationMultiplier !== null ||
    values.trafficMultiplier !== null;
  const mode = usesCheckout
    ? at("promo_bonus_mode_payment_short", {}, "after payment")
    : at("promo_bonus_mode_instant_short", {}, "instant");
  return `${text} · ${mode}`;
}

export function formatAdminPromoEligibility(source: PromoEffectSource, at: AdminTranslate): string {
  const parts: string[] = [];
  const days = positiveNumber(source.min_subscription_days);
  const months = positiveNumber(source.min_subscription_months);
  const trafficGb = positiveNumber(source.min_traffic_gb);

  if (days !== null) {
    parts.push(at("promo_threshold_days", { days: numberText(days) }, "from {days} d"));
  } else if (months !== null) {
    parts.push(at("promo_threshold_months", { months: numberText(months) }, "from {months} mo"));
  }
  if (trafficGb !== null) {
    parts.push(at("promo_threshold_gb", { gb: numberText(trafficGb) }, "from {gb} GB"));
  }
  return parts.join(", ") || "-";
}
