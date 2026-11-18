export const USERS_FILTER_QUERY_PARAM = "users_filter";
export const USERS_PANEL_STATUS_QUERY_PARAM = "users_panel_status";
export const USERS_PREMIUM_TRAFFIC_QUERY_PARAM = "users_premium_traffic";
export const USERS_TARIFF_QUERY_PARAM = "users_tariff";
export const USERS_EXTENSION_FILTER_QUERY_PARAM = "extension_filter";

export const USERS_FILTER_VALUES = [
  "all",
  "active",
  "banned",
  "active_today",
  "referred",
  "active_subscription",
  "paid",
  "free",
  "trial",
  "inactive_subscription",
  "expired_subscription",
  "unmapped_tariff",
  "tg_linked",
  "no_tg",
  "email_linked",
  "no_email",
  "panel_linked",
] as const;

export const USERS_PANEL_STATUS_VALUES = ["all", "active", "expired", "limited"] as const;
export const USERS_PREMIUM_TRAFFIC_VALUES = [
  "all",
  "none",
  "unlimited",
  "good",
  "warn",
  "critical",
] as const;

export type UsersFilter = (typeof USERS_FILTER_VALUES)[number];
export type UsersPanelStatusFilter = (typeof USERS_PANEL_STATUS_VALUES)[number];
export type UsersPremiumTrafficFilter = (typeof USERS_PREMIUM_TRAFFIC_VALUES)[number];
export type UsersTariffFilter =
  "all" | "trial" | "no_subscription" | "no_tariff" | `tariff:${string}`;
export type UsersExtensionSelections = Record<string, string>;

export type UsersRouteFilters = {
  usersFilter: UsersFilter;
  usersPanelStatus: UsersPanelStatusFilter;
  usersPremiumTraffic: UsersPremiumTrafficFilter;
  usersTariffFilter: UsersTariffFilter;
  usersExtensionFilters: UsersExtensionSelections;
};
export type UsersBuiltInFilterKey = Exclude<keyof UsersRouteFilters, "usersExtensionFilters">;
type UsersFilterInput = Partial<Record<UsersBuiltInFilterKey, unknown>> &
  Partial<Pick<UsersRouteFilters, "usersExtensionFilters">>;

export const DEFAULT_USERS_ROUTE_FILTERS: UsersRouteFilters = {
  usersFilter: "all",
  usersPanelStatus: "all",
  usersPremiumTraffic: "all",
  usersTariffFilter: "all",
  usersExtensionFilters: {},
};

export function normalizeUsersTariffFilter(value: unknown): UsersTariffFilter {
  const normalized = String(value || "").trim();
  if (normalized.startsWith("tariff:") && normalized.slice(7).trim()) {
    return normalized as UsersTariffFilter;
  }
  if (["trial", "no_subscription", "no_tariff"].includes(normalized)) {
    return normalized as UsersTariffFilter;
  }
  return "all";
}

function normalizedValue<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  const normalized = String(value || "")
    .trim()
    .toLowerCase() as T;
  return allowed.includes(normalized) ? normalized : fallback;
}

export function normalizeUsersRouteFilters(filters: UsersFilterInput): UsersRouteFilters {
  return {
    usersFilter: normalizedValue(
      filters.usersFilter,
      USERS_FILTER_VALUES,
      DEFAULT_USERS_ROUTE_FILTERS.usersFilter
    ),
    usersPanelStatus: normalizedValue(
      filters.usersPanelStatus,
      USERS_PANEL_STATUS_VALUES,
      DEFAULT_USERS_ROUTE_FILTERS.usersPanelStatus
    ),
    usersPremiumTraffic: normalizedValue(
      filters.usersPremiumTraffic,
      USERS_PREMIUM_TRAFFIC_VALUES,
      DEFAULT_USERS_ROUTE_FILTERS.usersPremiumTraffic
    ),
    usersTariffFilter: normalizeUsersTariffFilter(filters.usersTariffFilter),
    usersExtensionFilters: filters.usersExtensionFilters ?? {},
  };
}

export function readUsersRouteFilters(search: string | URLSearchParams): UsersRouteFilters {
  const params = typeof search === "string" ? new URLSearchParams(search) : search;
  return normalizeUsersRouteFilters({
    usersFilter: params.get(USERS_FILTER_QUERY_PARAM),
    usersPanelStatus: params.get(USERS_PANEL_STATUS_QUERY_PARAM),
    usersPremiumTraffic: params.get(USERS_PREMIUM_TRAFFIC_QUERY_PARAM),
    usersTariffFilter: params.get(USERS_TARIFF_QUERY_PARAM),
    usersExtensionFilters: Object.fromEntries(
      params.getAll(USERS_EXTENSION_FILTER_QUERY_PARAM).flatMap((selection) => {
        const separator = selection.indexOf("=");
        return separator > 0 && separator < selection.length - 1
          ? [[selection.slice(0, separator), selection.slice(separator + 1)]]
          : [];
      })
    ),
  });
}

export function writeUsersExtensionFilters(
  params: URLSearchParams,
  selections: UsersExtensionSelections
): void {
  params.delete(USERS_EXTENSION_FILTER_QUERY_PARAM);
  for (const [id, value] of Object.entries(selections)) {
    if (value) params.append(USERS_EXTENSION_FILTER_QUERY_PARAM, `${id}=${value}`);
  }
}

export function writeUsersRouteFilters(
  search: string | URLSearchParams,
  filters: UsersFilterInput
): URLSearchParams {
  const params = new URLSearchParams(typeof search === "string" ? search : search.toString());
  const normalized = normalizeUsersRouteFilters(filters);

  const entries: Array<[string, string, string]> = [
    [USERS_FILTER_QUERY_PARAM, normalized.usersFilter, DEFAULT_USERS_ROUTE_FILTERS.usersFilter],
    [
      USERS_PANEL_STATUS_QUERY_PARAM,
      normalized.usersPanelStatus,
      DEFAULT_USERS_ROUTE_FILTERS.usersPanelStatus,
    ],
    [
      USERS_PREMIUM_TRAFFIC_QUERY_PARAM,
      normalized.usersPremiumTraffic,
      DEFAULT_USERS_ROUTE_FILTERS.usersPremiumTraffic,
    ],
    [
      USERS_TARIFF_QUERY_PARAM,
      normalized.usersTariffFilter,
      DEFAULT_USERS_ROUTE_FILTERS.usersTariffFilter,
    ],
  ];

  for (const [key, value, defaultValue] of entries) {
    if (value === defaultValue) params.delete(key);
    else params.set(key, value);
  }
  writeUsersExtensionFilters(params, normalized.usersExtensionFilters);
  return params;
}

export function usersRouteFiltersEqual(a: UsersRouteFilters, b: UsersRouteFilters): boolean {
  const extensions = Object.entries(a.usersExtensionFilters);
  return (
    a.usersFilter === b.usersFilter &&
    a.usersPanelStatus === b.usersPanelStatus &&
    a.usersPremiumTraffic === b.usersPremiumTraffic &&
    a.usersTariffFilter === b.usersTariffFilter &&
    extensions.length === Object.keys(b.usersExtensionFilters).length &&
    extensions.every(([id, value]) => b.usersExtensionFilters[id] === value)
  );
}
