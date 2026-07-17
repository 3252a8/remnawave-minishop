export const USERS_FILTER_QUERY_PARAM = "users_filter";
export const USERS_PANEL_STATUS_QUERY_PARAM = "users_panel_status";
export const USERS_PREMIUM_TRAFFIC_QUERY_PARAM = "users_premium_traffic";

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

export type UsersRouteFilters = {
  usersFilter: UsersFilter;
  usersPanelStatus: UsersPanelStatusFilter;
  usersPremiumTraffic: UsersPremiumTrafficFilter;
};

export const DEFAULT_USERS_ROUTE_FILTERS: UsersRouteFilters = {
  usersFilter: "all",
  usersPanelStatus: "all",
  usersPremiumTraffic: "all",
};

function normalizedValue<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  const normalized = String(value || "")
    .trim()
    .toLowerCase() as T;
  return allowed.includes(normalized) ? normalized : fallback;
}

export function normalizeUsersRouteFilters(
  filters: Partial<Record<keyof UsersRouteFilters, unknown>>
): UsersRouteFilters {
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
  };
}

export function readUsersRouteFilters(search: string | URLSearchParams): UsersRouteFilters {
  const params = typeof search === "string" ? new URLSearchParams(search) : search;
  return normalizeUsersRouteFilters({
    usersFilter: params.get(USERS_FILTER_QUERY_PARAM),
    usersPanelStatus: params.get(USERS_PANEL_STATUS_QUERY_PARAM),
    usersPremiumTraffic: params.get(USERS_PREMIUM_TRAFFIC_QUERY_PARAM),
  });
}

export function writeUsersRouteFilters(
  search: string | URLSearchParams,
  filters: Partial<Record<keyof UsersRouteFilters, unknown>>
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
  ];

  for (const [key, value, defaultValue] of entries) {
    if (value === defaultValue) params.delete(key);
    else params.set(key, value);
  }
  return params;
}

export function usersRouteFiltersEqual(a: UsersRouteFilters, b: UsersRouteFilters): boolean {
  return (
    a.usersFilter === b.usersFilter &&
    a.usersPanelStatus === b.usersPanelStatus &&
    a.usersPremiumTraffic === b.usersPremiumTraffic
  );
}
