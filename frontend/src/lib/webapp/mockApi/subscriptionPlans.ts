import type { ActiveTariff, SubscriptionPlan, TariffOption } from "$lib/admin/subscriptionPlans";
import { subscriptionPlanFilter } from "$lib/admin/subscriptionPlans";
import { stringDate } from "../demoMockRuntime";
import { DATASET, type DemoAdminUser, type DemoRecord } from "./dataset";
import { demoTariffs } from "./state";

export function demoSubscriptionRows(user: DemoAdminUser): DemoRecord[] {
  const detail = DATASET.adminUserDetails?.[String(user.user_id)] || {};
  const subscriptions = Array.isArray(detail.subscriptions)
    ? (detail.subscriptions as DemoRecord[])
    : [];
  return detail.active_subscription
    ? [detail.active_subscription, ...subscriptions]
    : subscriptions;
}

export function isDemoActiveSubscription(subscription: DemoRecord): boolean {
  return (
    subscription.is_active === true &&
    stringDate(subscription.end_date as string | null | undefined) > Date.now()
  );
}

function trial(subscription: DemoRecord): boolean {
  return (
    String(subscription.provider || "").toLowerCase() === "trial" ||
    String(subscription.status_from_panel || "").toUpperCase() === "TRIAL"
  );
}

function priority(subscription: DemoRecord): number {
  return trial(subscription) ? 1 : subscription.provider ? 0 : 2;
}

function catalogOptions(): TariffOption[] {
  const catalog = demoTariffs();
  return (Array.isArray(catalog.tariffs) ? (catalog.tariffs as DemoRecord[]) : []).map(
    (tariff) => ({
      tariff_key: String(tariff.key),
      tariff_names: Object.fromEntries(
        Object.entries(tariff.names && typeof tariff.names === "object" ? tariff.names : {}).filter(
          (entry): entry is [string, string] => typeof entry[1] === "string"
        )
      ),
      is_configured: true,
      is_enabled: tariff.enabled !== false,
    })
  );
}

function configuredOption(key: string | null): TariffOption | undefined {
  const options = catalogOptions();
  const exact = options.find((option) => option.tariff_key === key);
  if (exact || key === null) return exact;
  const catalog = demoTariffs();
  const alias = (Array.isArray(catalog.tariffs) ? (catalog.tariffs as DemoRecord[]) : []).find(
    (tariff) => Array.isArray(tariff.legacy_keys) && tariff.legacy_keys.includes(key)
  );
  return alias ? options.find((option) => option.tariff_key === alias.key) : undefined;
}

export function demoSubscriptionPlan(user: DemoAdminUser): SubscriptionPlan | null {
  const subscriptions = demoSubscriptionRows(user);
  const live = subscriptions.filter(isDemoActiveSubscription);
  const representative = [...(live.length ? live : subscriptions)].sort(
    (a, b) =>
      (live.length ? priority(a) - priority(b) : 0) ||
      stringDate(b.end_date as string) - stringDate(a.end_date as string) ||
      Number(b.subscription_id) - Number(a.subscription_id)
  )[0];
  if (!representative) return null;
  const isTrial = trial(representative);
  const key = String(representative.tariff_key || "");
  const tariffKey = !isTrial && key.trim() ? key : null;
  const option = configuredOption(tariffKey);
  return {
    kind: isTrial ? "trial" : tariffKey ? "tariff" : "unassigned",
    tariff_key: tariffKey,
    tariff_names: option?.tariff_names || {},
    is_configured: option?.is_configured || false,
    is_enabled: option?.is_enabled ?? null,
    is_active: live.length > 0,
  };
}

export function demoTariffOptions(): TariffOption[] {
  const options = catalogOptions();
  for (const user of DATASET.adminUsers || []) {
    const plan = demoSubscriptionPlan(user);
    if (
      plan?.kind === "tariff" &&
      plan.tariff_key &&
      !options.some((option) => option.tariff_key === plan.tariff_key)
    ) {
      options.push({
        tariff_key: plan.tariff_key,
        tariff_names: plan.tariff_names,
        is_configured: plan.is_configured,
        is_enabled: plan.is_enabled,
      });
    }
  }
  return options;
}

export function demoHasUnmappedActiveSubscription(user: DemoAdminUser): boolean {
  const keys = new Set(catalogOptions().map((option) => option.tariff_key));
  return demoSubscriptionRows(user).some(
    (subscription) =>
      isDemoActiveSubscription(subscription) &&
      !keys.has(String(subscription.tariff_key || "").trim())
  );
}

export function demoActiveTariffs(): ActiveTariff[] {
  const rows: ActiveTariff[] = demoTariffOptions().map((option) => ({
    ...option,
    kind: "tariff",
    active_users: 0,
  }));
  for (const kind of ["trial", "unassigned"] as const)
    rows.push({
      kind,
      tariff_key: null,
      tariff_names: {},
      is_configured: false,
      is_enabled: null,
      active_users: 0,
    });
  for (const user of DATASET.adminUsers || []) {
    const plan = demoSubscriptionPlan(user);
    if (!plan?.is_active) continue;
    const row = rows.find((item) => subscriptionPlanFilter(item) === subscriptionPlanFilter(plan));
    if (row) row.active_users += 1;
  }
  return rows;
}
