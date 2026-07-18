import { formatMoney, formatTrafficGb } from "./formatters.js";
import type { WebappRecord } from "./domainTypes.js";

type TranslateFn = (key: string, params?: Record<string, string>, fallback?: string) => string;
type TermUnitLabel = (value: number, unit: "month") => string;

export type BillingPlan = WebappRecord & {
  billing_model?: string | null;
  currency?: string | null;
  description?: string | null;
  device_count?: number | string | null;
  hwid_renewal?: WebappRecord & {
    available?: boolean;
    currency?: string | null;
    device_count?: number | string | null;
    price?: number | string | null;
    stars_price?: number | string | null;
    valid_from_text?: string | null;
    valid_until_text?: string | null;
  };
  id?: string | number | null;
  is_default_tariff?: boolean;
  key?: string;
  min_amount?: number | string | null;
  min_currency?: string | null;
  mode?: string | null;
  months?: number | string | null;
  monthly_gb?: number | string | null;
  price?: number | string | null;
  sale_mode?: string | null;
  stars_price?: number | string | null;
  subtitle?: string | null;
  tariff_key?: string | null;
  tariff_name?: string | null;
  title?: string | null;
  traffic_gb?: number | string | null;
  traffic_packages?: unknown[];
  valid_until_text?: string | null;
};
export type TariffCatalogEntry = {
  billing_model: string;
  description: string;
  is_default: boolean;
  key: string;
  monthly_gb: number;
  plans_count: number;
  title: string;
  traffic_packages: number[];
};
export type PaymentMethod = WebappRecord & {
  disabled?: boolean;
  disabled_reason?: string;
  id?: string | number;
  min_amount?: number | string;
  min_currency?: string;
};

export const TELEGRAM_STARS_MINI_APP_REQUIRED = "telegram_stars_mini_app_required";

export function isStarsPaymentMethod(methodId: unknown): boolean {
  return String(methodId || "")
    .toLowerCase()
    .includes("stars");
}

export function paymentMethodsForContext(
  methods: PaymentMethod[] | null | undefined,
  telegramMiniAppContext: boolean
): PaymentMethod[] {
  return (methods || []).map((method) =>
    !telegramMiniAppContext && isStarsPaymentMethod(method.id)
      ? {
          ...method,
          disabled: true,
          disabled_reason: TELEGRAM_STARS_MINI_APP_REQUIRED,
        }
      : method
  );
}

export function planKey(plan: BillingPlan | null | undefined): string | number {
  return (
    plan?.id ||
    `${plan?.tariff_key || "legacy"}:${plan?.sale_mode || "subscription"}:${plan?.months || plan?.traffic_gb || ""}`
  );
}

export function buildTariffCatalog(
  planList: BillingPlan[] | null | undefined
): TariffCatalogEntry[] {
  const byKey = new Map<string, TariffCatalogEntry>();
  for (const plan of planList || []) {
    const key = String(plan?.tariff_key || planKey(plan) || "").trim();
    if (!key) continue;
    const entry =
      byKey.get(key) ||
      ({
        key,
        title: String(plan?.tariff_name || plan?.title || key),
        description: String(plan?.description || ""),
        billing_model: String(
          plan?.billing_model ||
            (plan?.sale_mode === "traffic_package" || plan?.sale_mode === "traffic"
              ? "traffic"
              : "period")
        ),
        is_default: Boolean(plan?.is_default_tariff),
        monthly_gb: Number(plan?.monthly_gb || 0),
        traffic_packages: [],
        plans_count: 0,
      } satisfies TariffCatalogEntry);
    if (!entry.description && plan?.description) entry.description = String(plan.description);
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

export function activeTariffName(
  sub: BillingPlan | null | undefined,
  planList: BillingPlan[] | null | undefined
): string {
  const direct = String(sub?.tariff_name || "").trim();
  if (direct) return direct;
  const key = String(sub?.tariff_key || "").trim();
  if (!key) return "";
  const plan = (planList || []).find((item) => item?.tariff_key === key);
  return String(plan?.tariff_name || plan?.title || key).trim();
}

export function priceLabel(plan: BillingPlan | null | undefined, methodId = ""): string {
  if (isStarsPaymentMethod(methodId) && Number(plan?.stars_price || 0) > 0) {
    return `${Number(plan?.stars_price)} ⭐`;
  }
  return formatMoney(plan?.price || 0, plan?.currency || undefined);
}

export function methodAmountForPlan(
  method: PaymentMethod | null | undefined,
  plan: BillingPlan | null | undefined
): number {
  if (!method || !plan) return 0;
  if (isStarsPaymentMethod(method?.id) && Number(plan?.stars_price || 0) > 0) {
    return Number(plan.stars_price || 0);
  }
  return Number(plan?.price || 0);
}

export function methodAvailableForPlan(
  method: PaymentMethod | null | undefined,
  plan: BillingPlan | null | undefined
): boolean {
  if (!method) return true;
  if (method.disabled) return false;
  if (!plan) return true;
  const minimum = Number(method?.min_amount || 0);
  const minimumCurrency = String(method?.min_currency || "").toUpperCase();
  const planCurrency = String(plan?.currency || "").toUpperCase();
  if (!minimum || !minimumCurrency || minimumCurrency !== planCurrency) return true;
  return methodAmountForPlan(method, plan) >= minimum;
}

export function methodsForPlan(
  methods: PaymentMethod[] | null | undefined,
  plan: BillingPlan | null | undefined
): PaymentMethod[] {
  return (methods || []).map((method) => ({
    ...method,
    disabled: !methodAvailableForPlan(method, plan),
  }));
}

export function firstAvailableMethod(methods: PaymentMethod[] | null | undefined): string {
  return String((methods || []).find((method) => !method?.disabled)?.id || "");
}

export function methodSelectable(
  methods: PaymentMethod[] | null | undefined,
  methodId: unknown
): boolean {
  return Boolean((methods || []).find((method) => method?.id === methodId && !method?.disabled));
}

export function tariffLimitLabel(
  tariff: BillingPlan | TariffCatalogEntry | null | undefined,
  { t }: { t: TranslateFn }
): string {
  if (!tariff) return "";
  if (String(tariff.billing_model || "") === "traffic") {
    const values = (Array.isArray(tariff.traffic_packages) ? tariff.traffic_packages : [])
      .map((value) => Number(value))
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

export function actionKey(action: BillingPlan | null | undefined): string {
  return `${action?.mode || ""}:${action?.months || ""}:${action?.traffic_gb || ""}:${action?.price || ""}`;
}

function formatMonthsForClient(
  value: unknown,
  { t, termUnitLabel }: { t: TranslateFn; termUnitLabel: TermUnitLabel }
): string {
  const months = Number(value || 0);
  if (months === 12) return t("wa_plan_one_year");
  return t("wa_sub_term_value_unit", {
    value: String(months),
    unit: termUnitLabel(months, "month"),
  });
}

export function planDisplayTitle(
  plan: BillingPlan | null | undefined,
  { trafficMode, t }: { trafficMode: boolean; t: TranslateFn }
): string {
  if (plan?.tariff_key) {
    return String(plan?.tariff_name || plan?.title || plan?.tariff_key);
  }
  if (trafficMode || plan?.sale_mode === "traffic") {
    return String(plan?.title || formatTrafficGb(plan?.traffic_gb || plan?.months));
  }
  const months = Number(plan?.months || 0);
  if (months === 12) return t("wa_plan_one_year");
  return String(plan?.title || "");
}

export function planSubtitle(
  plan: BillingPlan | null | undefined,
  { t, termUnitLabel }: { t: TranslateFn; termUnitLabel: TermUnitLabel }
): string {
  if (!plan?.tariff_key) return "";
  if (plan?.subtitle) return String(plan.subtitle);
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

export function planUnitHint(
  plan: BillingPlan | null | undefined,
  {
    trafficMode,
    selectedMethod,
    t,
  }: { trafficMode: boolean; selectedMethod: string; t: TranslateFn }
): string {
  if (
    trafficMode ||
    plan?.sale_mode === "traffic" ||
    plan?.sale_mode === "traffic_package" ||
    plan?.sale_mode === "topup" ||
    plan?.sale_mode === "premium_topup"
  ) {
    const gb = Number(plan?.traffic_gb || plan?.months || 0);
    if (!gb) return "";
    if (isStarsPaymentMethod(selectedMethod) && Number(plan?.stars_price || 0) > 0) {
      return `${Number(Number(plan?.stars_price) / gb).toFixed(0)} ⭐${t("wa_per_gb_short")}`;
    }
    return `${formatMoney(Number(plan?.price || 0) / gb, plan?.currency || undefined)}${t("wa_per_gb_short")}`;
  }
  const months = Number(plan?.months || 0);
  if (!months || months <= 1) return "";
  if (isStarsPaymentMethod(selectedMethod) && Number(plan?.stars_price || 0) > 0) {
    return `${Number(Number(plan?.stars_price) / months).toFixed(0)} ⭐${t("wa_per_month_short")}`;
  }
  return `${formatMoney(Number(plan?.price || 0) / months, plan?.currency || undefined)}${t("wa_per_month_short")}`;
}
