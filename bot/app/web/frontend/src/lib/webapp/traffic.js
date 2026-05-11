import { formatTrafficBytes, formatFraction, roundToHalf } from "./formatters.js";

export function trafficPercent(sub) {
  const used = Number(sub?.traffic_used_bytes || 0);
  const limit = Number(sub?.traffic_limit_bytes || 0);
  if (!limit || limit <= 0) return 100;
  return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
}

export function trafficLabel(sub, t) {
  if (!sub?.traffic_limit_bytes || Number(sub.traffic_limit_bytes) <= 0) return t("wa_unlimited_traffic");
  return t("wa_traffic_of", { used: sub.traffic_used || "0 GB", limit: sub.traffic_limit || "0 GB" });
}

export function trafficResetLabel(sub, t) {
  const strategy = String(sub?.traffic_limit_strategy || "").trim().toUpperCase();
  if (!strategy || strategy.includes("NO_RESET")) return t("wa_traffic_reset_none");
  if (strategy.includes("MONTH")) return t("wa_traffic_reset_monthly");
  if (strategy.includes("WEEK")) return t("wa_traffic_reset_weekly");
  if (strategy.includes("DAY")) return t("wa_traffic_reset_daily");
  if (strategy.includes("YEAR")) return t("wa_traffic_reset_yearly");
  return t("wa_traffic_reset_policy");
}

export function premiumTrafficPercent(sub) {
  const used = Number(sub?.premium_used_bytes || 0);
  const limit = Number(sub?.premium_limit_bytes || 0);
  if (!limit || limit <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
}

export function premiumTrafficLabel(sub, t) {
  return t("wa_traffic_of", { used: sub?.premium_used || "0 GB", limit: sub?.premium_limit || "0 GB" });
}

export function premiumTitle(sub, t) {
  return String(sub?.premium_title || "").trim() || t("wa_premium_traffic_title", {}, "Premium-серверы");
}

export function premiumTrafficLeftLabel(sub) {
  const left = Math.max(0, Number(sub?.premium_limit_bytes || 0) - Number(sub?.premium_used_bytes || 0));
  return formatTrafficBytes(left);
}

export function premiumTopupBalanceLabel(sub) {
  return formatTrafficBytes(Number(sub?.premium_topup_balance_bytes || 0));
}

export function premiumServerLabels(sub) {
  const labels =
    Array.isArray(sub?.premium_node_labels) && sub.premium_node_labels.length
      ? sub.premium_node_labels
      : sub?.premium_squad_labels || [];
  return labels.map((label) => String(label || "").trim()).filter(Boolean);
}

function extractYear(text) {
  const iso = String(text || "").match(/\b(\d{4})-\d{1,2}-\d{1,2}\b/);
  if (iso) return Number(iso[1] || 0);
  const dmy = String(text || "").match(/\b\d{1,2}\.\d{1,2}\.(\d{4})\b/);
  if (dmy) return Number(dmy[1] || 0);
  const any4 = String(text || "").match(/\b(\d{4})\b/);
  if (any4) return Number(any4[1] || 0);
  return 0;
}

export function isForeverSubscription(sub) {
  const raw = String(sub?.end_date_text || "").trim();
  if (!raw) return false;
  return extractYear(raw) >= 2099;
}

export function activeSubscriptionTermLabel(sub, { t, termUnitLabel }) {
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
