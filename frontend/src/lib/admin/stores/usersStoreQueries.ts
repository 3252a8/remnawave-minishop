import { adminErrorMessage } from "../errors.js";
import {
  buildAdminUserLogsPath,
  buildAdminUserPath,
  buildAdminUserReferralsPath,
  buildAdminUsersPath,
} from "../../webapp/publicApi";
import {
  USER_LOGS_PAGE_SIZE,
  USERS_PAGE_SIZE,
  type AdminApi,
  type AdminErrorResponse,
  type AdminLogsResponse,
  type AdminStoreState,
  type AdminUserDetailResponse,
  type AdminUserReferralsResponse,
  type AdminUsersListResponse,
  type TranslateFn,
} from "./usersStoreState";
import {
  fetchAdminQuery,
  invalidateAdminQuery,
  type AdminQueryClient,
  type AdminQueryKey,
} from "./adminQueryCache";

const USERS_QUERY_KEY = ["admin", "users"] as const;
const USER_DETAIL_QUERY_KEY = ["admin", "users", "detail"] as const;
const USER_LOGS_QUERY_KEY = ["admin", "users", "logs"] as const;
const USER_REFERRALS_QUERY_KEY = ["admin", "users", "referrals"] as const;

export class AdminUsersError extends Error {
  payload: AdminErrorResponse;

  constructor(message: string, payload: AdminErrorResponse) {
    super(message);
    this.payload = payload;
  }
}

export function createUsersStoreQueries({
  api,
  at,
  queryClient,
}: {
  api: AdminApi;
  at: TranslateFn;
  queryClient?: AdminQueryClient | null;
}) {
  function usersListParams(s: AdminStoreState): URLSearchParams {
    const params = new URLSearchParams({
      page: String(s.usersPage),
      page_size: String(USERS_PAGE_SIZE),
    });
    if (s.usersQuery.trim()) params.set("q", s.usersQuery.trim());
    if (s.usersFilter && s.usersFilter !== "all") params.set("filter", s.usersFilter);
    if (s.usersPanelStatus && s.usersPanelStatus !== "all")
      params.set("panel_status", s.usersPanelStatus);
    if (s.usersPremiumTraffic && s.usersPremiumTraffic !== "all") {
      params.set("premium_traffic", s.usersPremiumTraffic);
    }
    if (s.usersSort) params.set("sort", s.usersSort);
    return params;
  }

  function usersListQueryKey(s: AdminStoreState): AdminQueryKey {
    return [
      USERS_QUERY_KEY[0],
      USERS_QUERY_KEY[1],
      {
        filter: s.usersFilter,
        page: s.usersPage,
        panelStatus: s.usersPanelStatus,
        premiumTraffic: s.usersPremiumTraffic,
        query: s.usersQuery.trim(),
        sort: s.usersSort,
      },
    ];
  }

  async function requestUsers(s: AdminStoreState): Promise<AdminUsersListResponse> {
    const data = (await api(buildAdminUsersPath(usersListParams(s)))) as
      AdminUsersListResponse | AdminErrorResponse;
    if (!data?.ok) {
      throw new AdminUsersError(adminErrorMessage(data, at, "load_failed"), data);
    }
    return data;
  }

  async function queryUsers(s: AdminStoreState, refresh: boolean): Promise<AdminUsersListResponse> {
    return fetchAdminQuery({
      queryClient,
      queryKey: usersListQueryKey(s),
      queryFn: () => requestUsers(s),
      refresh,
    });
  }

  function userDetailQueryKey(userId: number): AdminQueryKey {
    return [USER_DETAIL_QUERY_KEY[0], USER_DETAIL_QUERY_KEY[1], USER_DETAIL_QUERY_KEY[2], userId];
  }

  async function requestUserDetail(userId: number): Promise<AdminUserDetailResponse> {
    const res = (await api(buildAdminUserPath(userId))) as
      AdminUserDetailResponse | AdminErrorResponse;
    if (!res?.ok) {
      throw new AdminUsersError(adminErrorMessage(res, at, "load_failed"), res);
    }
    return res;
  }

  function queryUserDetail(userId: number, refresh = false): Promise<AdminUserDetailResponse> {
    return fetchAdminQuery({
      queryClient,
      queryKey: userDetailQueryKey(userId),
      queryFn: () => requestUserDetail(userId),
      refresh,
    });
  }

  function userLogsQueryKey(userId: number | string, page: number): AdminQueryKey {
    return [USER_LOGS_QUERY_KEY[0], USER_LOGS_QUERY_KEY[1], USER_LOGS_QUERY_KEY[2], userId, page];
  }

  async function requestUserLogs(
    userId: number | string,
    page: number
  ): Promise<AdminLogsResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(USER_LOGS_PAGE_SIZE),
      user_id: String(userId),
    });
    const data = (await api(buildAdminUserLogsPath(params))) as
      AdminLogsResponse | AdminErrorResponse;
    if (!data?.ok) {
      throw new AdminUsersError(adminErrorMessage(data, at, "load_failed"), data);
    }
    return data;
  }

  function queryUserLogs(userId: number | string, page: number): Promise<AdminLogsResponse> {
    return fetchAdminQuery({
      queryClient,
      queryKey: userLogsQueryKey(userId, page),
      queryFn: () => requestUserLogs(userId, page),
    });
  }

  function userReferralsQueryKey(
    userId: number | string,
    page: number,
    pageSize: number
  ): AdminQueryKey {
    return [
      USER_REFERRALS_QUERY_KEY[0],
      USER_REFERRALS_QUERY_KEY[1],
      USER_REFERRALS_QUERY_KEY[2],
      userId,
      page,
      pageSize,
    ];
  }

  async function requestUserReferrals(
    userId: number | string,
    page: number,
    pageSize: number
  ): Promise<AdminUserReferralsResponse> {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    const data = (await api(buildAdminUserReferralsPath(userId, params))) as
      AdminUserReferralsResponse | AdminErrorResponse;
    if (!data?.ok) {
      throw new AdminUsersError(adminErrorMessage(data, at, "load_failed"), data);
    }
    return data;
  }

  function queryUserReferrals(
    userId: number | string,
    page: number,
    pageSize: number
  ): Promise<AdminUserReferralsResponse> {
    return fetchAdminQuery({
      queryClient,
      queryKey: userReferralsQueryKey(userId, page, pageSize),
      queryFn: () => requestUserReferrals(userId, page, pageSize),
    });
  }

  function invalidateUsersQueries(userId?: number | string): void {
    invalidateAdminQuery(queryClient, USERS_QUERY_KEY);
    if (userId === undefined || userId === null) return;
    const normalizedUserId = Number(userId);
    if (Number.isFinite(normalizedUserId)) {
      invalidateAdminQuery(queryClient, userDetailQueryKey(normalizedUserId));
    }
    invalidateAdminQuery(queryClient, [
      USER_LOGS_QUERY_KEY[0],
      USER_LOGS_QUERY_KEY[1],
      USER_LOGS_QUERY_KEY[2],
      userId,
    ]);
    invalidateAdminQuery(queryClient, [
      USER_REFERRALS_QUERY_KEY[0],
      USER_REFERRALS_QUERY_KEY[1],
      USER_REFERRALS_QUERY_KEY[2],
      userId,
    ]);
  }

  function loadUserErrorMessage(error: unknown): string {
    if (error instanceof AdminUsersError) {
      return adminErrorMessage(error.payload, at, "load_failed");
    }
    if (error instanceof Error) return error.message;
    return String(error || "load_failed");
  }

  return {
    invalidateUsersQueries,
    loadUserErrorMessage,
    queryUserDetail,
    queryUserLogs,
    queryUserReferrals,
    queryUsers,
  };
}
