import { formatTrafficBytes, formatFraction, roundToHalf } from "./formatters.js";

type WebappRecord = Record<string, unknown>;
type SubscriptionTraffic = WebappRecord & {
  days_left?: number | string;
  end_date_text?: string | null;
  premium_limit?: string | null;
  premium_limit_bytes?: number | string | null;
  premium_next_reset_text?: string | null;
  premium_node_labels?: unknown[];
  premium_squad_labels?: unknown[];
  premium_title?: string | null;
  premium_topup_balance_bytes?: number | string | null;
  premium_unlimited_override?: boolean;
  premium_used?: string | null;
  premium_used_bytes?: number | string | null;
  regular_unlimited_override?: boolean;
  traffic_limit?: string | null;
  traffic_limit_bytes?: number | string | null;
  traffic_limit_strategy?: string | null;
  traffic_next_reset_text?: string | null;
  traffic_used?: string | null;
  traffic_used_bytes?: number | string | null;
};
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type TermLabelDeps = {
  t: TranslateFn;
  termUnitLabel: (value: number, unit: "day" | "month" | "year") => string;
};

export function trafficPercent(sub: SubscriptionTraffic | null | undefined): number {
  const used = Number(sub?.traffic_used_bytes || 0);
  const limit = Number(sub?.traffic_limit_bytes || 0);
  if (!limit || limit <= 0) return 100;
  return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
}

export function regularTrafficLimitVisible(sub: SubscriptionTraffic | null | undefined): boolean {
  return !sub?.regular_unlimited_override && Number(sub?.traffic_limit_bytes || 0) > 0;
}

export function trafficLabel(sub: SubscriptionTraffic | null | undefined, t: TranslateFn): string {
  if (!sub?.traffic_limit_bytes || Number(sub.traffic_limit_bytes) <= 0)
    return t("wa_unlimited_traffic");
  return t("wa_traffic_of", {
    used: sub.traffic_used || "0 GB",
    limit: sub.traffic_limit || "0 GB",
  });
}

function normalizedTrafficResetStrategy(sub: SubscriptionTraffic | null | undefined): string {
  return String(sub?.traffic_limit_strategy || "")
    .trim()
    .toUpperCase();
}

export function trafficResetScheduled(sub: SubscriptionTraffic | null | undefined): boolean {
  const strategy = normalizedTrafficResetStrategy(sub);
  return Boolean(strategy && !strategy.includes("NO_RESET"));
}

export function trafficResetLabel(
  sub: SubscriptionTraffic | null | undefined,
  t: TranslateFn
): string {
  const strategy = normalizedTrafficResetStrategy(sub);
  if (!trafficResetScheduled(sub)) return t("wa_traffic_reset_none");
  if (strategy.includes("MONTH")) return t("wa_traffic_reset_monthly");
  if (strategy.includes("WEEK")) return t("wa_traffic_reset_weekly");
  if (strategy.includes("DAY")) return t("wa_traffic_reset_daily");
  if (strategy.includes("YEAR")) return t("wa_traffic_reset_yearly");
  return t("wa_traffic_reset_policy");
}

export function trafficSummaryTitle(
  sub: SubscriptionTraffic | null | undefined,
  t: TranslateFn
): string {
  return trafficResetScheduled(sub) ? trafficResetLabel(sub, t) : t("wa_home_traffic_used");
}

function nextResetText(value: unknown, t: TranslateFn): string {
  const text = String(value || "").trim();
  return text || t("wa_traffic_next_reset_none");
}

export function trafficNextResetLabel(
  sub: SubscriptionTraffic | null | undefined,
  t: TranslateFn
): string {
  return nextResetText(sub?.traffic_next_reset_text, t);
}

export function premiumTrafficPercent(sub: SubscriptionTraffic | null | undefined): number {
  const used = Number(sub?.premium_used_bytes || 0);
  const limit = Number(sub?.premium_limit_bytes || 0);
  if (!limit || limit <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
}

export function premiumTrafficLimitVisible(sub: SubscriptionTraffic | null | undefined): boolean {
  return !sub?.premium_unlimited_override && Number(sub?.premium_limit_bytes || 0) > 0;
}

export function premiumTrafficLabel(
  sub: SubscriptionTraffic | null | undefined,
  t: TranslateFn
): string {
  return t("wa_traffic_of", {
    used: sub?.premium_used || "0 GB",
    limit: sub?.premium_limit || "0 GB",
  });
}

export function premiumNextResetLabel(
  sub: SubscriptionTraffic | null | undefined,
  t: TranslateFn
): string {
  return nextResetText(sub?.premium_next_reset_text, t);
}

export function premiumTitle(sub: SubscriptionTraffic | null | undefined, t: TranslateFn): string {
  return (
    String(sub?.premium_title || "").trim() || t("wa_premium_traffic_title", {}, "Premium-серверы")
  );
}

export function premiumTrafficLeftLabel(sub: SubscriptionTraffic | null | undefined): string {
  const left = Math.max(
    0,
    Number(sub?.premium_limit_bytes || 0) - Number(sub?.premium_used_bytes || 0)
  );
  return formatTrafficBytes(left);
}

export function premiumTopupBalanceLabel(sub: SubscriptionTraffic | null | undefined): string {
  return formatTrafficBytes(Number(sub?.premium_topup_balance_bytes || 0));
}

export function premiumServerLabels(sub: SubscriptionTraffic | null | undefined): string[] {
  const labels =
    Array.isArray(sub?.premium_node_labels) && sub.premium_node_labels.length
      ? sub.premium_node_labels
      : Array.isArray(sub?.premium_squad_labels)
        ? sub.premium_squad_labels
        : [];
  return labels.map((label) => String(label || "").trim()).filter(Boolean);
}

function extractYear(text: unknown): number {
  const iso = String(text || "").match(/\b(\d{4})-\d{1,2}-\d{1,2}\b/);
  if (iso) return Number(iso[1] || 0);
  const dmy = String(text || "").match(/\b\d{1,2}\.\d{1,2}\.(\d{4})\b/);
  if (dmy) return Number(dmy[1] || 0);
  const any4 = String(text || "").match(/\b(\d{4})\b/);
  if (any4) return Number(any4[1] || 0);
  return 0;
}

export function isForeverSubscription(sub: SubscriptionTraffic | null | undefined): boolean {
  const raw = String(sub?.end_date_text || "").trim();
  if (!raw) return false;
  return extractYear(raw) >= 2099;
}

export function activeSubscriptionTermLabel(
  sub: SubscriptionTraffic | null | undefined,
  { t, termUnitLabel }: TermLabelDeps
): string {
  if (isForeverSubscription(sub)) return t("wa_sub_term_forever");

  const days = Math.max(0, Number(sub?.days_left || 0));
  if (!days) return t("wa_sub_term_value_unit", { value: "0", unit: termUnitLabel(0, "day") });

  if (days < 30) {
    return t("wa_sub_term_value_unit", { value: String(days), unit: termUnitLabel(days, "day") });
  }
  if (days < 365) {
    const months = roundToHalf(days / 30);
    return t("wa_sub_term_value_unit", {
      value: formatFraction(months),
      unit: termUnitLabel(months, "month"),
    });
  }
  const years = roundToHalf(days / 365);
  return t("wa_sub_term_value_unit", {
    value: formatFraction(years),
    unit: termUnitLabel(years, "year"),
  });
}
