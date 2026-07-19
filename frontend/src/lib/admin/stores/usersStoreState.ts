import type { components, operations } from "../../api/openapi.generated";
import type { ApiClient, ApiResponse } from "../../webapp/publicApi";

export const USERS_PAGE_SIZE = 25;
export const USER_LOGS_PAGE_SIZE = 20;

export type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
export type AdminApi = <Path extends Parameters<ApiClient["api"]>[0]>(
  path: Path,
  options?: Parameters<ApiClient["api"]>[1]
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
export type AdminUsersListResponse = NonNullable<
  operations["get_admin_users_list_route"]["responses"][200]["content"]["application/json"]
>;
export type AdminUserDetailResponse = NonNullable<
  operations["get_admin_user_detail_route"]["responses"][200]["content"]["application/json"]
>;
export type AdminUserReferralsResponse = NonNullable<
  operations["get_admin_user_referrals_route"]["responses"][200]["content"]["application/json"]
>;
export type AdminLogsResponse = NonNullable<
  operations["get_admin_logs_route"]["responses"][200]["content"]["application/json"]
>;
type AdminListUser = NonNullable<AdminUsersListResponse["users"]>[number];
export type AdminSubscription = components["schemas"]["AdminSubscriptionOut"];
export type AdminPanelSquadOverrides = components["schemas"]["AdminPanelSquadOverridesOut"];
export type AdminUserDetail = AdminUserDetailResponse & {
  active_subscription: AdminSubscription | null;
  subscriptions: AdminSubscription[];
  user: AdminUser;
  panel_squad_overrides?: AdminPanelSquadOverrides | null;
};
export type UserLogRow = NonNullable<AdminLogsResponse["logs"]>[number];
export type DraftNumber = number | string;
export type AdminStoreState = {
  users: AdminUser[];
  usersTotal: number;
  usersPage: number;
  usersQuery: string;
  usersFilter: string;
  usersPanelStatus: string;
  usersPremiumTraffic: string;
  usersSort: string;
  usersLoading: boolean;
  openedUser: AdminUser | null;
  openedUserDetail: AdminUserDetail | null;
  userDetailLoading: boolean;
  userMessageDraft: string;
  userExtendDays: DraftNumber;
  userExtendHwidDevices: boolean;
  userExtendTariffKey: string;
  userTariffActionKey: string;
  userTariffActionBaselineKey: string;
  userApplyTariffHwidLimit: boolean;
  userTariffHwidConfirmOpen: boolean;
  trafficStrategyDraft: string;
  trafficStrategyBaseline: string;
  userActionBusy: boolean;
  userDeleteOpen: boolean;
  userSubscriptionReissueOpen: boolean;
  userBanConfirmOpen: boolean;
  userMessageConfirmOpen: boolean;
  userReferralsOpen: boolean;
  userReferralsLoading: boolean;
  userReferrals: AdminUser[];
  userReferralsTotal: number;
  userReferralsPage: number;
  userReferralsPageSize: number;
  userReferralsInviter: AdminUser | null;
  userDetailTab: string;
  premiumUnlimitedDraft: boolean;
  premiumUnlimitedBaseline: boolean;
  premiumBonusGbDraft: DraftNumber;
  premiumBonusGbBaseline: DraftNumber;
  regularUnlimitedDraft: boolean;
  regularUnlimitedBaseline: boolean;
  regularBonusGbDraft: DraftNumber;
  regularBonusGbBaseline: DraftNumber;
  hwidUnlimitedDraft: boolean;
  hwidUnlimitedBaseline: boolean;
  hwidDeviceLimitDraft: DraftNumber;
  hwidDeviceLimitBaseline: DraftNumber;
  grantTrafficGbDraft: DraftNumber;
  grantTrafficKindDraft: "regular" | "premium";
  userSquadOverrideDraft: string;
  userExternalSquadModeDraft: "inherit" | "set" | "cleared";
  userExternalSquadUuidDraft: string;
  userLogs: UserLogRow[];
  userLogsTotal: number;
  userLogsPage: number;
  userLogsLoading: boolean;
  userLogsLoaded: boolean;
  userLogsUserId: number | string | null;
  userLogsPageSize: number;
};
export type AdminUser = Partial<
  components["schemas"]["AdminUserOut"] &
    components["schemas"]["AdminUserWithAvatarOut"] &
    AdminListUser
> & { user_id: number | string };
export type ToastFn = (message: string) => void;
export type TranslateFn = (
  key: string,
  params?: Record<string, unknown>,
  fallback?: string
) => string;
export type PathContext = "users" | "payments" | null;
export type OpenUserOptions = { pathContext?: PathContext; skipPush?: boolean };
export type SnapshotOptions = {
  resetExtendTariff?: boolean;
  resetTariffAction?: boolean;
  resetTrafficStrategy?: boolean;
  resetPremium?: boolean;
  resetRegular?: boolean;
  resetHwid?: boolean;
  resetGrant?: boolean;
  resetSquadOverrides?: boolean;
};

export type UsersStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  routePrefix?: string;
  queryClient?: import("./adminQueryCache").AdminQueryClient | null;
};

export function createInitialUsersState(): AdminStoreState {
  return {
    users: [],
    usersTotal: 0,
    usersPage: 0,
    usersQuery: "",
    usersFilter: "all",
    usersPanelStatus: "all",
    usersPremiumTraffic: "all",
    usersSort: "",
    usersLoading: false,

    openedUser: null,
    openedUserDetail: null,
    userDetailLoading: false,
    userMessageDraft: "",
    userExtendDays: 30,
    userExtendHwidDevices: true,
    userExtendTariffKey: "",
    userTariffActionKey: "",
    userTariffActionBaselineKey: "",
    userApplyTariffHwidLimit: false,
    userTariffHwidConfirmOpen: false,
    trafficStrategyDraft: "",
    trafficStrategyBaseline: "",
    userActionBusy: false,
    userDeleteOpen: false,
    userSubscriptionReissueOpen: false,
    userBanConfirmOpen: false,
    userMessageConfirmOpen: false,
    userReferralsOpen: false,
    userReferralsLoading: false,
    userReferrals: [],
    userReferralsTotal: 0,
    userReferralsPage: 0,
    userReferralsPageSize: USERS_PAGE_SIZE,
    userReferralsInviter: null,
    userDetailTab: "profile",
    premiumUnlimitedDraft: false,
    premiumUnlimitedBaseline: false,
    premiumBonusGbDraft: "",
    premiumBonusGbBaseline: "",
    regularUnlimitedDraft: false,
    regularUnlimitedBaseline: false,
    regularBonusGbDraft: "",
    regularBonusGbBaseline: "",
    hwidUnlimitedDraft: false,
    hwidUnlimitedBaseline: false,
    hwidDeviceLimitDraft: "",
    hwidDeviceLimitBaseline: "",
    grantTrafficGbDraft: "",
    grantTrafficKindDraft: "regular",
    userSquadOverrideDraft: "",
    userExternalSquadModeDraft: "inherit",
    userExternalSquadUuidDraft: "",

    userLogs: [],
    userLogsTotal: 0,
    userLogsPage: 0,
    userLogsLoading: false,
    userLogsLoaded: false,
    userLogsUserId: null,
    userLogsPageSize: USER_LOGS_PAGE_SIZE,
  };
}

export function closedUserModalState(): Partial<AdminStoreState> {
  return {
    openedUser: null,
    openedUserDetail: null,
    userDetailLoading: false,
    userMessageDraft: "",
    userExtendDays: 30,
    userExtendHwidDevices: true,
    userExtendTariffKey: "",
    userTariffActionKey: "",
    userTariffActionBaselineKey: "",
    userApplyTariffHwidLimit: false,
    userTariffHwidConfirmOpen: false,
    trafficStrategyDraft: "",
    trafficStrategyBaseline: "",
    userDeleteOpen: false,
    userSubscriptionReissueOpen: false,
    userBanConfirmOpen: false,
    userMessageConfirmOpen: false,
    userReferralsOpen: false,
    userReferralsLoading: false,
    userReferrals: [],
    userReferralsTotal: 0,
    userReferralsPage: 0,
    userReferralsInviter: null,
    userDetailTab: "profile",
    premiumUnlimitedDraft: false,
    premiumUnlimitedBaseline: false,
    premiumBonusGbDraft: "",
    premiumBonusGbBaseline: "",
    regularUnlimitedDraft: false,
    regularUnlimitedBaseline: false,
    regularBonusGbDraft: "",
    regularBonusGbBaseline: "",
    hwidUnlimitedDraft: false,
    hwidUnlimitedBaseline: false,
    hwidDeviceLimitDraft: "",
    hwidDeviceLimitBaseline: "",
    grantTrafficGbDraft: "",
    grantTrafficKindDraft: "regular",
    userSquadOverrideDraft: "",
    userExternalSquadModeDraft: "inherit",
    userExternalSquadUuidDraft: "",
    userLogs: [],
    userLogsTotal: 0,
    userLogsPage: 0,
    userLogsLoading: false,
    userLogsLoaded: false,
    userLogsUserId: null,
  };
}
