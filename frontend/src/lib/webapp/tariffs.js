import { formatMoney, formatTrafficGb } from "./formatters.js";

export function planKey(plan) {
  return (
    plan?.id ||
    `${plan?.tariff_key || "legacy"}:${plan?.sale_mode || "subscription"}:${plan?.months || plan?.traffic_gb || ""}`
  );
}

export function buildTariffCatalog(planList) {
  const byKey = new Map();
  for (const plan of planList || []) {
    const key = String(plan?.tariff_key || planKey(plan) || "").trim();
    if (!key) continue;
    const entry = byKey.get(key) || {
      key,
      title: plan?.tariff_name || plan?.title || key,
      description: plan?.description || "",
      billing_model:
        plan?.billing_model ||
        (plan?.sale_mode === "traffic_package" || plan?.sale_mode === "traffic"
          ? "traffic"
          : "period"),
      is_default: Boolean(plan?.is_default_tariff),
      monthly_gb: Number(plan?.monthly_gb || 0),
      traffic_packages: [],
      plans_count: 0,
    };
    if (!entry.description && plan?.description) entry.description = plan.description;
    if (plan?.is_default_tariff) entry.is_default = true;
    if (!entry.monthly_gb && Number(plan?.monthly_gb || 0) > 0)
      entry.monthly_gb = Number(plan.monthly_gb);
    const trafficGb = Number(plan?.traffic_gb || 0);
    if (trafficGb > 0) entry.traffic_packages.push(trafficGb);
    entry.plans_count += 1;
    byKey.set(key, entry);
  }
  return Array.from(byKey.values());
}

export function activeTariffName(sub, planList) {
  const direct = String(sub?.tariff_name || "").trim();
  if (direct) return direct;
  const key = String(sub?.tariff_key || "").trim();
  if (!key) return "";
  const plan = (planList || []).find((item) => item?.tariff_key === key);
  return String(plan?.tariff_name || plan?.title || key).trim();
}

export function priceLabel(plan, methodId = "") {
  if (
    String(methodId || "")
      .toLowerCase()
      .includes("stars") &&
    Number(plan?.stars_price || 0) > 0
  ) {
    return `${Number(plan.stars_price)} ⭐`;
  }
  return formatMoney(plan?.price || 0, plan?.currency);
}

export function methodAmountForPlan(method, plan) {
  if (!method || !plan) return 0;
  if (
    String(method?.id || "")
      .toLowerCase()
      .includes("stars") &&
    Number(plan?.stars_price || 0) > 0
  ) {
    return Number(plan.stars_price || 0);
  }
  return Number(plan?.price || 0);
}

export function methodAvailableForPlan(method, plan) {
  if (!method || !plan) return true;
  const minimum = Number(method?.min_amount || 0);
  const minimumCurrency = String(method?.min_currency || "").toUpperCase();
  const planCurrency = String(plan?.currency || "").toUpperCase();
  if (!minimum || !minimumCurrency || minimumCurrency !== planCurrency) return true;
  return methodAmountForPlan(method, plan) >= minimum;
}

export function methodsForPlan(methods, plan) {
  return (methods || []).map((method) => ({
    ...method,
    disabled: !methodAvailableForPlan(method, plan),
  }));
}

export function firstAvailableMethod(methods) {
  return (methods || []).find((method) => !method?.disabled)?.id || "";
}

export function methodSelectable(methods, methodId) {
  return Boolean((methods || []).find((method) => method?.id === methodId && !method?.disabled));
}

export function tariffLimitLabel(tariff, { t }) {
  if (!tariff) return "";
  if (String(tariff.billing_model || "") === "traffic") {
    const values = (tariff.traffic_packages || [])
      .filter((value) => Number(value) > 0)
      .sort((a, b) => a - b);
    if (!values.length) return t("wa_tariff_model_traffic");
    const min = values[0];
    const max = values[values.length - 1];
    return min === max ? formatTrafficGb(min) : `${formatTrafficGb(min)} - ${formatTrafficGb(max)}`;
  }
  if (Number(tariff.monthly_gb || 0) > 0) return formatTrafficGb(tariff.monthly_gb);
  return t("wa_unlimited_traffic");
}

export function actionKey(action) {
  return `${action?.mode || ""}:${action?.months || ""}:${action?.traffic_gb || ""}:${action?.price || ""}`;
}

function formatMonthsForClient(value, { t, termUnitLabel }) {
  const months = Number(value || 0);
  if (months === 12) return t("wa_plan_one_year");
  return t("wa_sub_term_value_unit", {
    value: String(months),
    unit: termUnitLabel(months, "month"),
  });
}

export function planDisplayTitle(plan, { trafficMode, t }) {
  if (plan?.tariff_key) {
    return plan?.tariff_name || plan?.title || plan?.tariff_key;
  }
  if (trafficMode || plan?.sale_mode === "traffic") {
    return plan?.title || formatTrafficGb(plan?.traffic_gb || plan?.months);
  }
  const months = Number(plan?.months || 0);
  if (months === 12) return t("wa_plan_one_year");
  return plan?.title || "";
}

export function planSubtitle(plan, { t, termUnitLabel }) {
  if (!plan?.tariff_key) return "";
  if (plan?.subtitle) return plan.subtitle;
  if (
    plan?.sale_mode === "traffic_package" ||
    plan?.sale_mode === "topup" ||
    plan?.sale_mode === "premium_topup" ||
    plan?.billing_model === "traffic"
  ) {
    return formatTrafficGb(plan?.traffic_gb || plan?.months);
  }
  return formatMonthsForClient(plan?.months, { t, termUnitLabel });
}

export function planUnitHint(plan, { trafficMode, selectedMethod, t }) {
  if (
    trafficMode ||
    plan?.sale_mode === "traffic" ||
    plan?.sale_mode === "traffic_package" ||
    plan?.sale_mode === "topup" ||
    plan?.sale_mode === "premium_topup"
  ) {
    const gb = Number(plan?.traffic_gb || plan?.months || 0);
    if (!gb) return "";
    if (
      String(selectedMethod || "")
        .toLowerCase()
        .includes("stars") &&
      Number(plan?.stars_price || 0) > 0
    ) {
      return `${Number(plan.stars_price / gb).toFixed(0)} ⭐${t("wa_per_gb_short")}`;
    }
    return `${formatMoney(Number(plan?.price || 0) / gb, plan?.currency)}${t("wa_per_gb_short")}`;
  }
  const months = Number(plan?.months || 0);
  if (!months || months <= 1) return "";
  if (
    String(selectedMethod || "")
      .toLowerCase()
      .includes("stars") &&
    Number(plan?.stars_price || 0) > 0
  ) {
    return `${Number(plan.stars_price / months).toFixed(0)} ⭐${t("wa_per_month_short")}`;
  }
  return `${formatMoney(Number(plan?.price || 0) / months, plan?.currency)}${t("wa_per_month_short")}`;
}
