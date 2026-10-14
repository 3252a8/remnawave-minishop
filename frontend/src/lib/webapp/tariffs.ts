import { billingDurationDays, durationParts } from "./subscriptionPeriods.js";
import { formatMoney, formatTrafficGb } from "./formatters.js";
import type { WebappRecord } from "./domainTypes.js";

type TranslateFn = (key: string, params?: Record<string, string>, fallback?: string) => string;
type TermUnitLabel = (value: number, unit: "day" | "month" | "year") => string;

export type CheckoutAddonKind = "devices" | "traffic" | "premium_traffic";
export type CheckoutAddonOption = {
  extra_units: number;
  total_units: number;
  price: number;
  stars_price?: number;
  traffic_bonus_gb?: number;
};
export type CheckoutAddonDefinition = {
  kind: CheckoutAddonKind;
  base_units: number;
  max_total_units: number;
  options: CheckoutAddonOption[];
  initial_units?: number;
};
export type CheckoutAddonSelection = {
  device_count: number;
  regular_limit_gb: number | null;
  premium_limit_gb: number | null;
};

export type CheckoutTariffLimit = {
  known: boolean;
  units: number;
  unlimited: boolean;
};

export type CheckoutTariffSummary = {
  devices: CheckoutTariffLimit;
  traffic: CheckoutTariffLimit;
  premiumTraffic: CheckoutTariffLimit;
};

export type TariffLimitFact = CheckoutTariffLimit & {
  kind: CheckoutAddonKind;
  label: string;
  unavailable: boolean;
  adjustable?: boolean;
  valueText?: string;
};

export type BillingPlan = WebappRecord & {
  access_via_link?: boolean;
  available_payment_method_ids?: string[] | null;
  externally_managed_price_method_ids?: string[] | null;
  billing_model?: string | null;
  checkout_addons?: Partial<Record<CheckoutAddonKind, CheckoutAddonDefinition>>;
  checkout_addons_unavailable_payment_method_ids?: string[] | null;
  currency?: string | null;
  description?: string | null;
  device_count?: number | string | null;
  effective_hwid_device_limit?: number | string | null;
  hwid_renewal?: WebappRecord & {
    available?: boolean;
    currency?: string | null;
    device_count?: number | string | null;
    price?: number | string | null;
    stars_price?: number | string | null;
    traffic_bonus_gb?: number | string | null;
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
  duration_days?: number | string | null;
  monthly_gb?: number | string | null;
  premium_enabled?: boolean | null;
  premium_monthly_gb?: number | string | null;
  premium_title?: string | null;
  premium_traffic_limit_strategy?: string | null;
  premium_unlimited?: boolean | null;
  price?: number | string | null;
  sale_mode?: string | null;
  traffic_bonus_gb?: number | string | null;
  stars_price?: number | string | null;
  subtitle?: string | null;
  tariff_key?: string | null;
  tariff_name?: string | null;
  title?: string | null;
  traffic_gb?: number | string | null;
  traffic_limit_strategy?: string | null;
  traffic_packages?: unknown[];
  valid_until_text?: string | null;
};
export type TariffCatalogEntry = Pick<
  BillingPlan,
  | "checkout_addons"
  | "effective_hwid_device_limit"
  | "premium_enabled"
  | "premium_monthly_gb"
  | "premium_title"
  | "premium_traffic_limit_strategy"
  | "premium_unlimited"
  | "traffic_limit_strategy"
> & {
  billing_model: string;
  description: string;
  is_default: boolean;
  key: string;
  monthly_gb: number | null;
  plans_count: number;
  title: string;
  traffic_packages: number[];
};
export type PaymentMethod = WebappRecord & {
  balance_supported?: boolean;
  disabled?: boolean;
  disabled_reason?: string;
  id?: string | number;
  min_amount?: number | string;
  min_currency?: string;
  minimum_amount?: number | string;
  minimum_amount_text?: string;
  price_managed_externally?: boolean;
  shop_limit_currency?: string;
  shop_min_amount?: number | string;
};

export type PaymentMethodMinimum = {
  amount: number;
  currency: string;
  text: string;
};

function firstFiniteValue(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value !== "number" && typeof value !== "string") continue;
    if (typeof value === "string" && !value.trim()) continue;
    const number = Number(value);
    if (Number.isFinite(number) && number >= 0) return number;
  }
  return null;
}

export function checkoutTariffSummary(plan: BillingPlan | null | undefined): CheckoutTariffSummary {
  const addons = plan?.checkout_addons || {};
  const devices = firstFiniteValue(
    addons.devices?.base_units,
    plan?.effective_hwid_device_limit,
    plan?.hwid_device_limit
  );
  const traffic = firstFiniteValue(
    addons.traffic?.base_units,
    plan?.monthly_gb,
    plan?.billing_model === "traffic" ? plan?.traffic_gb : null
  );
  const premiumEnabled = plan?.premium_enabled;
  const premiumAddon = addons.premium_traffic;
  const premiumAvailable = premiumEnabled !== false || Boolean(premiumAddon);
  const premium = premiumAvailable
    ? firstFiniteValue(premiumAddon?.base_units, plan?.premium_monthly_gb)
    : null;
  const premiumKnown = premiumAvailable && (premium !== null || plan?.premium_unlimited === true);

  return {
    devices: {
      known: devices !== null,
      units: Math.max(0, devices || 0),
      unlimited: devices !== null && devices <= 0,
    },
    traffic: {
      known: traffic !== null,
      units: Math.max(0, traffic || 0),
      unlimited: traffic !== null && traffic <= 0,
    },
    premiumTraffic: {
      known: premiumKnown,
      units: Math.max(0, premium || 0),
      unlimited: premiumEnabled !== false && plan?.premium_unlimited === true,
    },
  };
}

export function tariffLimitTitle(
  plan: BillingPlan | null | undefined,
  kind: CheckoutAddonKind,
  unlimited: boolean,
  { t }: { t: TranslateFn }
): string {
  if (kind === "devices") return t("wa_checkout_addon_devices", {}, "Devices");
  const strategy = String(
    kind === "premium_traffic"
      ? plan?.premium_traffic_limit_strategy || plan?.traffic_limit_strategy || ""
      : plan?.traffic_limit_strategy || ""
  ).toUpperCase();
  const period = unlimited
    ? ""
    : strategy.includes("MONTH")
      ? t("wa_checkout_period_month", {}, "per month")
      : strategy.includes("WEEK")
        ? t("wa_checkout_period_week", {}, "per week")
        : strategy.includes("DAY")
          ? t("wa_checkout_period_day", {}, "per day")
          : strategy.includes("NO_RESET")
            ? t("wa_checkout_period_no_reset", {}, "without reset")
            : "";
  const premiumTitle = String(plan?.premium_title || "").trim();
  if (kind === "premium_traffic" && premiumTitle) {
    if (unlimited) return premiumTitle;
    return period
      ? t(
          "wa_checkout_named_traffic_with_period",
          { name: premiumTitle, period },
          `${premiumTitle} ${period}`
        )
      : t("wa_checkout_named_traffic_period", { name: premiumTitle }, `${premiumTitle} per period`);
  }
  if (unlimited) {
    return kind === "traffic"
      ? t("wa_checkout_addon_traffic", {}, "Traffic")
      : t("wa_checkout_addon_premium_traffic", {}, "Premium traffic");
  }
  if (!period) {
    return kind === "traffic"
      ? t("wa_checkout_tariff_traffic_period", {}, "Traffic per period")
      : t("wa_checkout_tariff_premium_period", {}, "Premium traffic per period");
  }
  return kind === "traffic"
    ? t("wa_checkout_tariff_traffic_with_period", { period }, `Traffic ${period}`)
    : t("wa_checkout_tariff_premium_with_period", { period }, `Premium traffic ${period}`);
}

export function tariffLimitFacts(
  plan: BillingPlan | null | undefined,
  { t }: { t: TranslateFn }
): TariffLimitFact[] {
  const summary = checkoutTariffSummary(plan);
  const kinds: CheckoutAddonKind[] = ["devices", "traffic", "premium_traffic"];
  return kinds.map((kind) => {
    const limit = kind === "premium_traffic" ? summary.premiumTraffic : summary[kind];
    const fact: TariffLimitFact = {
      ...limit,
      kind,
      label: tariffLimitTitle(plan, kind, limit.unlimited, { t }),
      unavailable:
        kind === "premium_traffic" &&
        ((plan?.premium_enabled === false && !plan.checkout_addons?.premium_traffic) ||
          (limit.known && !limit.unlimited && limit.units === 0)),
    };
    if (kind === "traffic" && plan?.billing_model === "traffic") {
      const packages = (plan.traffic_packages || [])
        .map((value) => firstFiniteValue(value))
        .filter((value): value is number => value !== null && value > 0)
        .sort((a, b) => a - b);
      if (packages.length) {
        const min = packages[0];
        const max = packages[packages.length - 1];
        fact.known = true;
        fact.unlimited = false;
        fact.label = tariffLimitTitle(plan, kind, false, { t });
        fact.units = min;
        fact.valueText =
          min === max ? formatTrafficGb(min) : `${formatTrafficGb(min)} – ${formatTrafficGb(max)}`;
      }
    }
    return fact;
  });
}

export const TELEGRAM_STARS_MINI_APP_REQUIRED = "telegram_stars_mini_app_required";

export function paymentMethodMinimum(
  method: PaymentMethod | null | undefined
): PaymentMethodMinimum | null {
  const amount = Number(
    method?.min_amount ?? method?.minimum_amount ?? method?.shop_min_amount ?? 0
  );
  const currency = String(
    method?.min_currency ?? method?.shop_limit_currency ?? method?.currency ?? ""
  ).toUpperCase();
  const text = String(method?.minimum_amount_text || "").trim();
  if (!Number.isFinite(amount) || amount <= 0 || (!currency && !text)) return null;
  return { amount, currency, text };
}

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
    `${plan?.tariff_key || "legacy"}:${plan?.sale_mode || "subscription"}:${plan?.duration_days || plan?.months || plan?.traffic_gb || ""}`
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
        monthly_gb: firstFiniteValue(plan?.monthly_gb),
        effective_hwid_device_limit: firstFiniteValue(
          plan?.effective_hwid_device_limit,
          plan?.hwid_device_limit
        ),
        checkout_addons: plan.checkout_addons,
        premium_enabled: plan.premium_enabled,
        premium_monthly_gb: plan.premium_monthly_gb,
        premium_title: plan.premium_title,
        premium_traffic_limit_strategy: plan.premium_traffic_limit_strategy,
        premium_unlimited: plan.premium_unlimited,
        traffic_limit_strategy: plan.traffic_limit_strategy,
        traffic_packages: [],
        plans_count: 0,
      } satisfies TariffCatalogEntry);
    if (!entry.description && plan?.description) entry.description = String(plan.description);
    if (plan?.is_default_tariff) entry.is_default = true;
    if (entry.monthly_gb === null) entry.monthly_gb = firstFiniteValue(plan.monthly_gb);
    if (entry.effective_hwid_device_limit === null)
      entry.effective_hwid_device_limit = firstFiniteValue(
        plan.effective_hwid_device_limit,
        plan.hwid_device_limit
      );
    entry.checkout_addons ??= plan.checkout_addons;
    entry.premium_enabled ??= plan.premium_enabled;
    entry.premium_monthly_gb ??= plan.premium_monthly_gb;
    entry.premium_title ??= plan.premium_title;
    entry.premium_traffic_limit_strategy ??= plan.premium_traffic_limit_strategy;
    entry.premium_unlimited ??= plan.premium_unlimited;
    entry.traffic_limit_strategy ??= plan.traffic_limit_strategy;
    const trafficGb = Number(plan?.traffic_gb || 0);
    if (trafficGb > 0) entry.traffic_packages.push(trafficGb);
    entry.plans_count += 1;
    byKey.set(key, entry);
  }
  return Array.from(byKey.values());
}

export function initialCheckoutTariffKey(
  catalog: TariffCatalogEntry[],
  linkedPlan: BillingPlan | null | undefined
): string {
  const linkedKey = String(linkedPlan?.tariff_key || "").trim();
  if (linkedKey && catalog.some((entry) => entry.key === linkedKey)) return linkedKey;
  return catalog.length === 1 ? catalog[0].key : "";
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

export function isTrialPaymentPlan(plan: BillingPlan | null | undefined): boolean {
  return String(plan?.sale_mode || "").toLowerCase() === "trial";
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
  if (
    Array.isArray(plan.available_payment_method_ids) &&
    !plan.available_payment_method_ids.includes(String(method.id || "").toLowerCase())
  ) {
    return false;
  }
  const minimumPayment = paymentMethodMinimum(method);
  const minimum = Number(minimumPayment?.amount || 0);
  const minimumCurrency = String(minimumPayment?.currency || "").toUpperCase();
  const planCurrency = String(plan?.currency || "").toUpperCase();
  if (!minimum || !minimumCurrency || minimumCurrency !== planCurrency) return true;
  return methodAmountForPlan(method, plan) >= minimum;
}

export function methodManagesPrice(
  methods: PaymentMethod[],
  plan: BillingPlan | null,
  methodId: string
): boolean {
  const id = methodId.toLowerCase();
  return Boolean(
    plan?.externally_managed_price_method_ids?.some((method) => method.toLowerCase() === id) ||
    methods.find((method) => String(method.id || "").toLowerCase() === id)?.price_managed_externally
  );
}

export function methodMinimumAmount(methods: PaymentMethod[], methodId: string): number {
  const method = methods.find(
    (item) => String(item.id || "").toLowerCase() === methodId.toLowerCase()
  );
  return Math.max(
    0,
    Number(method?.minimum_amount || method?.min_amount || method?.shop_min_amount || 0)
  );
}

export function methodsForPlan(
  methods: PaymentMethod[] | null | undefined,
  plan: BillingPlan | null | undefined,
  balanceSource: "user" | "partner" | null = null
): PaymentMethod[] {
  return (methods || [])
    .filter(
      (method) =>
        !balanceSource ||
        (method.balance_supported !== false &&
          !isStarsPaymentMethod(method.id) &&
          !method.price_managed_externally &&
          !plan?.externally_managed_price_method_ids?.includes(
            String(method.id || "").toLowerCase()
          ))
    )
    .map((method) => ({
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
  const monthly = firstFiniteValue(tariff.monthly_gb);
  if (monthly === null) return t("wa_checkout_tariff_not_specified", {}, "Not specified");
  if (monthly > 0) return formatTrafficGb(monthly);
  return t("wa_unlimited_traffic");
}

export function actionKey(action: BillingPlan | null | undefined): string {
  return `${action?.mode || ""}:${action?.duration_days || action?.months || ""}:${action?.traffic_gb || ""}:${action?.price || ""}`;
}

function formatPeriodForClient(
  value: unknown,
  { t, termUnitLabel }: { t: TranslateFn; termUnitLabel: TermUnitLabel }
): string {
  const parts = durationParts(value);
  if (!parts) return "";
  return t("wa_sub_term_value_unit", {
    value: String(parts.count),
    unit: termUnitLabel(parts.count, parts.unit),
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
  if (billingDurationDays(plan) === 365 && !plan?.title) return t("wa_plan_one_year");
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
  return formatPeriodForClient(billingDurationDays(plan), { t, termUnitLabel });
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
  const days = billingDurationDays(plan);
  if (!days || days < 30) return "";
  if (isStarsPaymentMethod(selectedMethod) && Number(plan?.stars_price || 0) > 0) {
    const rate = (Number(plan?.stars_price) * 30) / days;
    return `${rate < 1 ? "<1" : rate.toFixed(0)} ⭐ ${t("wa_per_month_label")}`;
  }
  return `${formatMoney((Number(plan?.price || 0) * 30) / days, plan?.currency || undefined)} ${t("wa_per_month_label")}`;
}
