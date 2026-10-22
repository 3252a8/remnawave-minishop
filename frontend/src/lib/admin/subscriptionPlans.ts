import type { components } from "../api/openapi.generated";
import type { TranslateFn } from "$components/patterns/admin/types";
import type { UsersTariffFilter } from "./usersRouteFilters";

export type SubscriptionPlan = components["schemas"]["AdminSubscriptionPlanOut"];
export type TariffOption = components["schemas"]["AdminTariffOptionOut"];
export type ActiveTariff = components["schemas"]["AdminActiveTariffOut"];
type PlanIdentity = Pick<SubscriptionPlan, "kind" | "tariff_key" | "tariff_names">;

export function tariffOptionName(
  option: Pick<TariffOption, "tariff_key" | "tariff_names">,
  language: string
): string {
  const names = option.tariff_names || {};
  return (
    names[language] ||
    names[language.split("-")[0]] ||
    names.en ||
    names.ru ||
    Object.values(names).find(Boolean) ||
    option.tariff_key
  );
}

export function subscriptionPlanLabel(
  plan: PlanIdentity | null | undefined,
  language: string,
  at: TranslateFn
): string {
  if (!plan) return at("users_tariff_no_subscription", {}, "No subscription");
  if (plan.kind === "trial") return at("users_tariff_trial", {}, "Trial");
  if (plan.kind === "unassigned") return at("users_tariff_unassigned", {}, "No tariff");
  return tariffOptionName(
    { tariff_key: plan.tariff_key || "", tariff_names: plan.tariff_names },
    language
  );
}

export function subscriptionPlanFilter(
  plan: Pick<SubscriptionPlan, "kind" | "tariff_key">
): UsersTariffFilter {
  if (plan.kind === "trial") return "trial";
  if (plan.kind === "unassigned" || !plan.tariff_key) return "no_tariff";
  return `tariff:${plan.tariff_key}`;
}

export function tariffFilterOptions(
  options: TariffOption[],
  selected: string,
  language: string,
  at: TranslateFn
): { value: string; label: string }[] {
  const tariffs = [...options];
  if (
    selected.startsWith("tariff:") &&
    !tariffs.some((option) => `tariff:${option.tariff_key}` === selected)
  ) {
    tariffs.push({
      tariff_key: selected.slice(7),
      tariff_names: {},
      is_configured: false,
      is_enabled: null,
    });
  }
  const namedTariffs = tariffs
    .map((option) => {
      const name = tariffOptionName(option, language);
      const duplicateName = tariffs.some(
        (other) =>
          other.tariff_key !== option.tariff_key && tariffOptionName(other, language) === name
      );
      const label = duplicateName ? `${name} (${option.tariff_key})` : name;
      const status = !option.is_configured
        ? at("users_tariff_deleted", {}, "Removed")
        : option.is_enabled === false
          ? at("users_tariff_disabled", {}, "Disabled")
          : "";
      return {
        value: `tariff:${option.tariff_key}`,
        label: status ? `${label} · ${status}` : label,
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label, language));
  return [
    { value: "all", label: at("users_tariff_all", {}, "All tariffs") },
    { value: "trial", label: at("users_tariff_trial", {}, "Trial") },
    { value: "no_subscription", label: at("users_tariff_no_subscription", {}, "No subscription") },
    { value: "no_tariff", label: at("users_tariff_unassigned", {}, "No tariff") },
    ...namedTariffs,
  ];
}
