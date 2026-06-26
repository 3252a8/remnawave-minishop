import { readCookie } from "./session.js";
import type { paths } from "../api/openapi.generated";

type HttpMethod = "get" | "put" | "post" | "delete" | "patch";
type RawApiPath = Extract<keyof paths, string>;
export type ApiPath = RawApiPath;

type ExpandPathPath<Path extends string> = Path extends `${infer Prefix}/{${string}}${infer Suffix}`
  ? `${Prefix}/${string}${ExpandPathPath<Suffix>}`
  : Path;

type ApiPathExpanded = {
  [P in RawApiPath]: ExpandPathPath<P>;
}[RawApiPath];

type ApiPathFor<Path extends string> = Path extends `/api${string}` ? Path : `/api${Path}`;

type StripQuery<Path extends string> = Path extends `${infer PathWithoutQuery}?${string}`
  ? PathWithoutQuery
  : Path;

type MatchApiTemplatePath<Path extends string> = {
  [P in RawApiPath]: Path extends ExpandPathPath<P> ? P : never;
}[RawApiPath];

type ResolvedApiPath<Path extends string> = Path extends string
  ? MatchApiTemplatePath<StripQuery<ApiPathFor<Path>>>
  : never;

type KnownApiPath<Path extends string> = Path extends ApiPathInput ? ResolvedApiPath<Path> : never;

type ApiPathInputWithApiPrefix = ApiPath | ApiPathExpanded;
type ApiPathInputWithoutPrefix = ApiPathInputWithApiPrefix extends `/api${infer Rest}` ? Rest : never;
type ApiPathInput = ApiPathInputWithApiPrefix | `${ApiPathInputWithApiPrefix}?${string}` | ApiPathInputWithoutPrefix | `${ApiPathInputWithoutPrefix}?${string}`;

type OperationFor<Path extends string, Method extends HttpMethod> =
  KnownApiPath<Path> extends never ? never : NonNullable<paths[KnownApiPath<Path>][Method]>;
type JsonRequestBody<Operation> = Operation extends {
  requestBody: { content: { "application/json": infer Body } };
}
  ? Body
  : Record<string, unknown>;
type JsonResponse<Operation> = Operation extends {
  responses: { 200: { content: { "application/json": infer Body } } };
}
  ? Body
  : Record<string, unknown>;
export type ApiResponse<Path extends string> =
  | JsonResponse<OperationFor<Path, "get">>
  | JsonResponse<OperationFor<Path, "post">>
  | JsonResponse<OperationFor<Path, "put">>
  | JsonResponse<OperationFor<Path, "patch">>
  | JsonResponse<OperationFor<Path, "delete">>;
export type GetResponse<Path extends string> = JsonResponse<OperationFor<Path, "get">>;
export type PostPayload<Path extends string> = JsonRequestBody<OperationFor<Path, "post">>;
export type PostResponse<Path extends string> = JsonResponse<OperationFor<Path, "post">>;

export type BootstrapResponse = GetResponse<"/api/bootstrap">;
export type MeResponse = GetResponse<"/api/me">;
export type AccountEmailRequestResponse = PostResponse<"/api/account/email/request">;
export type AccountEmailVerifyResponse = PostResponse<"/api/account/email/verify">;
export type AccountLanguageResponse = PostResponse<"/api/account/language">;
export type AccountPasswordRequestResponse = PostResponse<"/api/account/password/request">;
export type AccountPasswordConfirmResponse = PostResponse<"/api/account/password/confirm">;
export type AccountTelegramLinkResponse = PostResponse<"/api/account/telegram/link">;
export type AuthEmailMagicResponse = PostResponse<"/api/auth/email/magic">;
export type AuthEmailPasswordResponse = PostResponse<"/api/auth/email/password">;
export type AuthEmailRequestResponse = PostResponse<"/api/auth/email/request">;
export type AuthEmailVerifyResponse = PostResponse<"/api/auth/email/verify">;
export type AuthLogoutResponse = PostResponse<"/api/auth/logout">;
export type AuthTokenResponse = PostResponse<"/api/auth/token">;
export type DevicesResponse = GetResponse<"/api/devices">;
export type DevicesDisconnectResponse = PostResponse<"/api/devices/disconnect">;
export type DeviceTopupOptionsResponse = GetResponse<"/api/devices/topup-options">;
export type PaymentCreateResponse = PostResponse<"/api/payments">;
export type PaymentStatusResponse = GetResponse<"/api/payments/{payment_id}">;
export type PromoApplyResponse = PostResponse<"/api/promo/apply">;
export type ReferralWelcomeBonusResponse = PostResponse<"/api/referral/welcome-bonus/claim">;
export type SubscriptionGuidesResponse = GetResponse<"/api/subscription-guides">;
export type PublicSubscriptionGuidesResponse =
  GetResponse<"/api/subscription-guides/public/{share_token}">;
export type SubscriptionAutoRenewResponse = PostResponse<"/api/subscription/auto-renew">;
export type SupportTicketsResponse = GetResponse<"/api/support/tickets">;
export type SupportTicketCreateResponse = PostResponse<"/api/support/tickets">;
export type SupportTicketDetailResponse = GetResponse<"/api/support/tickets/{id}">;
export type SupportTicketReplyResponse = PostResponse<"/api/support/tickets/{id}/messages">;
export type SupportTicketReadResponse = PostResponse<"/api/support/tickets/{id}/read">;
export type SupportUnreadResponse = GetResponse<"/api/support/unread">;
export type TariffChangeResponse = PostResponse<"/api/tariffs/change">;
export type TariffChangeOptionsResponse = GetResponse<"/api/tariffs/change-options">;
export type TariffChangePaymentResponse = PostResponse<"/api/tariffs/change-payment">;
export type TariffTopupOptionsResponse = GetResponse<"/api/tariffs/topup-options">;
export type TrialActivateResponse = PostResponse<"/api/trial/activate">;

type MockContext = Record<string, unknown>;
export type MockApi = (
  path: string,
  options: RequestInit,
  context: MockContext
) => unknown | Promise<unknown>;

type ApiClientOptions = {
  apiBase?: string;
  csrfCookieName?: string;
  getCsrfToken?: () => string;
  onUnauthorized?: () => void;
  mockApi?: MockApi | null;
  getMockContext?: () => MockContext;
};

export type ApiClient = {
  api<Path extends ApiPathInput>(path: Path, options?: RequestInit): Promise<ApiResponse<Path>>;
  apiUnchecked(path: string, options?: RequestInit): Promise<Record<string, unknown>>;
  publicApi<Path extends ApiPathInput>(
    path: Path,
    payload?: PostPayload<Path>,
    options?: Pick<RequestInit, "signal">
  ): Promise<PostResponse<Path>>;
  publicApiUnchecked(
    path: string,
    payload?: Record<string, unknown>,
    options?: Pick<RequestInit, "signal">
  ): Promise<Record<string, unknown>>;
};

export type MePath = "/me" | "/me?fresh=1";
export function buildMePath(fresh: boolean = false): MePath {
  return fresh ? "/me?fresh=1" : "/me";
}

export type AdminHealthPath = "/admin/health" | "/admin/health?refresh=1";
export function buildAdminHealthPath(refresh: boolean = false): AdminHealthPath {
  return refresh ? "/admin/health?refresh=1" : "/admin/health";
}

export type TariffTopupOptionsPath = `/tariffs/topup-options?kind=${string}`;
export function buildTariffTopupOptionsPath(kind: string): TariffTopupOptionsPath {
  return `/tariffs/topup-options?kind=${encodeURIComponent(String(kind))}`;
}

export type PaymentStatusPath = `/payments/${string}`;
export function buildPaymentStatusPath(paymentId: string | number): PaymentStatusPath {
  return `/payments/${encodeURIComponent(String(paymentId))}` as PaymentStatusPath;
}

export type SupportTicketPath = "/support/tickets/{id}";
export function buildSupportTicketPath(ticketId: string | number): SupportTicketPath {
  return `/support/tickets/${encodeURIComponent(String(ticketId))}` as SupportTicketPath;
}

export type SupportTicketMessagesPath = "/support/tickets/{id}/messages";
export function buildSupportTicketMessagesPath(ticketId: string | number): SupportTicketMessagesPath {
  return `/support/tickets/${encodeURIComponent(String(ticketId))}/messages` as SupportTicketMessagesPath;
}

export type SupportTicketReadPath = "/support/tickets/{id}/read";
export function buildSupportTicketReadPath(ticketId: string | number): SupportTicketReadPath {
  return `/support/tickets/${encodeURIComponent(String(ticketId))}/read` as SupportTicketReadPath;
}

export type AdminSettingsPath = "/admin/settings";
export function buildAdminSettingsPath(): AdminSettingsPath {
  return "/admin/settings";
}

export type AdminTariffsPath = "/admin/tariffs";
export function buildAdminTariffsPath(): AdminTariffsPath {
  return "/admin/tariffs";
}

export type AdminPanelInternalSquadsPath = "/admin/panel/internal-squads";
export function buildAdminPanelInternalSquadsPath(): AdminPanelInternalSquadsPath {
  return "/admin/panel/internal-squads";
}

export type AdminUsersPath = "/admin/users" | `/admin/users?${string}`;
export function buildAdminUsersPath(params?: URLSearchParams): AdminUsersPath {
  const query = params?.toString();
  return (query ? `/admin/users?${query}` : "/admin/users") as AdminUsersPath;
}

export type AdminUserPath = "/admin/users/{user_id}";
export function buildAdminUserPath(userId: string | number): AdminUserPath {
  return `/admin/users/${encodeURIComponent(String(userId))}` as AdminUserPath;
}

export type AdminUsersLogsPath = "/admin/logs" | `/admin/logs?${string}`;
export function buildAdminUserLogsPath(params?: URLSearchParams): AdminUsersLogsPath {
  const query = params?.toString();
  return (query ? `/admin/logs?${query}` : "/admin/logs") as AdminUsersLogsPath;
}

export type AdminUserReferralsPath =
  | "/admin/users/{user_id}/referrals"
  | `/admin/users/{user_id}/referrals?${string}`;
export function buildAdminUserReferralsPath(
  userId: string | number,
  params?: URLSearchParams
): AdminUserReferralsPath {
  const base = `/admin/users/${encodeURIComponent(String(userId))}/referrals`;
  const query = params?.toString();
  return (query ? `${base}?${query}` : base) as AdminUserReferralsPath;
}

export type AdminUserAction =
  | "ban"
  | "message"
  | "message/preview"
  | "telegram-profile-link"
  | "extend"
  | "tariff"
  | "reset-trial"
  | "premium-override"
  | "regular-traffic-override"
  | "hwid-device-limit"
  | "traffic-grant";
export type AdminUserActionPath = `/admin/users/{user_id}/${AdminUserAction}`;
export function buildAdminUserActionPath(
  userId: string | number,
  action: AdminUserAction
): AdminUserActionPath {
  return `/admin/users/${encodeURIComponent(String(userId))}/${action}` as AdminUserActionPath;
}

export type AdminSupportTicketsPath = "/admin/support/tickets" | `/admin/support/tickets?${string}`;
export function buildAdminSupportTicketsPath(params: URLSearchParams): AdminSupportTicketsPath {
  return `/admin/support/tickets?${params.toString()}` as AdminSupportTicketsPath;
}

export type AdminSupportTicketPath = "/admin/support/tickets/{id}";
export function buildAdminSupportTicketPath(ticketId: string | number): AdminSupportTicketPath {
  return `/admin/support/tickets/${encodeURIComponent(String(ticketId))}` as AdminSupportTicketPath;
}

export type AdminSupportTicketMessagesPath = "/admin/support/tickets/{id}/messages";
export function buildAdminSupportTicketMessagesPath(
  ticketId: string | number
): AdminSupportTicketMessagesPath {
  return `/admin/support/tickets/${encodeURIComponent(String(ticketId))}/messages` as AdminSupportTicketMessagesPath;
}

export type AdminSupportTicketReadPath = "/admin/support/tickets/{id}/read";
export function buildAdminSupportTicketReadPath(ticketId: string | number): AdminSupportTicketReadPath {
  return `/admin/support/tickets/${encodeURIComponent(String(ticketId))}/read` as AdminSupportTicketReadPath;
}

export type AdminSupportPath = "/admin/support" | "/admin/support/{id}";
export function buildAdminSupportPath(ticketId?: string | number | null): AdminSupportPath {
  return ticketId
    ? (`/admin/support/${encodeURIComponent(String(ticketId))}` as AdminSupportPath)
    : "/admin/support";
}

export type AdminBroadcastPath = "/admin/broadcast";
export function buildAdminBroadcastPath(): AdminBroadcastPath {
  return "/admin/broadcast";
}

export type AdminBroadcastAudienceCountsPath = "/admin/broadcast/audience-counts";
export function buildAdminBroadcastAudienceCountsPath(): AdminBroadcastAudienceCountsPath {
  return "/admin/broadcast/audience-counts";
}

export type AdminLogsPath = "/admin/logs" | `/admin/logs?${string}`;
export function buildAdminLogsPath(params?: URLSearchParams): AdminLogsPath {
  const query = params?.toString();
  return (query ? `/admin/logs?${query}` : "/admin/logs") as AdminLogsPath;
}

export type AdminStatsPath = "/admin/stats";
export function buildAdminStatsPath(): AdminStatsPath {
  return "/admin/stats";
}

export type AdminSyncPath = "/admin/sync";
export function buildAdminSyncPath(): AdminSyncPath {
  return "/admin/sync";
}

export type AdminThemesPath = "/admin/themes";
export function buildAdminThemesPath(): AdminThemesPath {
  return "/admin/themes";
}

export type AdminAppearanceLogoPath = "/admin/appearance/logo";
export function buildAdminAppearanceLogoPath(): AdminAppearanceLogoPath {
  return "/admin/appearance/logo";
}

export type AdminAppearanceFaviconPath = "/admin/appearance/favicon";
export function buildAdminAppearanceFaviconPath(): AdminAppearanceFaviconPath {
  return "/admin/appearance/favicon";
}

export type AdminTranslationsPath = "/admin/translations";
export function buildAdminTranslationsPath(): AdminTranslationsPath {
  return "/admin/translations";
}

export type AdminBackupsPath = "/admin/backups";
export function buildAdminBackupsPath(): AdminBackupsPath {
  return "/admin/backups";
}

export type AdminBackupsCreatePath = "/admin/backups/create";
export function buildAdminBackupsCreatePath(): AdminBackupsCreatePath {
  return "/admin/backups/create";
}

export type AdminBackupsUploadPath = "/admin/backups/upload";
export function buildAdminBackupsUploadPath(): AdminBackupsUploadPath {
  return "/admin/backups/upload";
}

export type AdminBackupsRestorePath = "/admin/backups/restore";
export function buildAdminBackupsRestorePath(): AdminBackupsRestorePath {
  return "/admin/backups/restore";
}

export type AdminPromosPath = "/admin/promos" | `/admin/promos?${string}`;
export function buildAdminPromosPath(params?: URLSearchParams): AdminPromosPath {
  const query = params?.toString();
  return (query ? `/admin/promos?${query}` : "/admin/promos") as AdminPromosPath;
}

export type AdminPromoPath = "/admin/promos/{promo_id}";
export function buildAdminPromoPath(promoId: string | number): AdminPromoPath {
  return `/admin/promos/${encodeURIComponent(String(promoId))}` as AdminPromoPath;
}

export type AdminAdsPath = "/admin/ads";
export function buildAdminAdsPath(): AdminAdsPath {
  return "/admin/ads";
}

export type AdminAdPath = "/admin/ads/{campaign_id}";
export function buildAdminAdPath(campaignId: string | number): AdminAdPath {
  return `/admin/ads/${encodeURIComponent(String(campaignId))}` as AdminAdPath;
}

export type AdminAdTogglePath = "/admin/ads/{campaign_id}/toggle";
export function buildAdminAdTogglePath(campaignId: string | number): AdminAdTogglePath {
  return `/admin/ads/${encodeURIComponent(String(campaignId))}/toggle` as AdminAdTogglePath;
}

export type AdminSupportStatsPath = "/admin/support/stats";
export function buildAdminSupportStatsPath(): AdminSupportStatsPath {
  return "/admin/support/stats";
}

export type AdminPaymentsPath = "/admin/payments" | `/admin/payments?${string}`;
export function buildAdminPaymentsPath(params?: URLSearchParams): AdminPaymentsPath {
  const query = params?.toString();
  return (query ? `/admin/payments?${query}` : "/admin/payments") as AdminPaymentsPath;
}

export type AdminPaymentUsersPath = "/admin/payments/users" | "/admin/payments/users/{user_id}";
export function buildAdminPaymentsUserPath(userId?: string | number | null): AdminPaymentUsersPath {
  return userId
    ? (`/admin/payments/users/${encodeURIComponent(String(userId))}` as AdminPaymentUsersPath)
    : "/admin/payments/users";
}

export type AdminPaymentPath = "/admin/payments/{payment_id}";
export function buildAdminPaymentPath(paymentId: string | number): AdminPaymentPath {
  return `/admin/payments/${encodeURIComponent(String(paymentId))}` as AdminPaymentPath;
}

export type AdminPaymentsExportPath = "/api/admin/payments/export.csv";
export function buildAdminPaymentsExportPath(): AdminPaymentsExportPath {
  return "/api/admin/payments/export.csv";
}

export function unwrap<T extends { ok: boolean }>(response: T): Extract<T, { ok: true }> {
  if (!response.ok) throw response;
  return response as Extract<T, { ok: true }>;
}

export function createApiClient({
  apiBase = "",
  csrfCookieName = "rw_webapp_csrf",
  getCsrfToken = () => "",
  onUnauthorized = () => {},
  mockApi = null,
  getMockContext = () => ({}),
}: ApiClientOptions = {}): ApiClient {
  const isFormDataBody = (body: BodyInit | null | undefined) =>
    typeof FormData !== "undefined" && body instanceof FormData;

  async function requestJson(path: string, options: RequestInit = {}): Promise<Record<string, unknown>> {
    if (mockApi) return (await mockApi(path, options, getMockContext())) as Record<string, unknown>;

    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers);

    const csrf = getCsrfToken() || readCookie(csrfCookieName) || "";
    if (csrf && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      headers.set("X-CSRF-Token", csrf);
    }
    if (options.body && !headers.has("Content-Type") && !isFormDataBody(options.body)) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
    });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) onUnauthorized();
    return payload as Record<string, unknown>;
  }

  async function api<Path extends ApiPathInput>(
    path: Path,
    options: RequestInit = {}
  ): Promise<ApiResponse<Path>> {
    return (await requestJson(path, options)) as ApiResponse<Path>;
  }

  async function apiUnchecked(path: string, options: RequestInit = {}): Promise<Record<string, unknown>> {
    return requestJson(path, options);
  }

  async function publicApiUnchecked(
    path: string,
    payload: Record<string, unknown> = {},
    options: Pick<RequestInit, "signal"> = {}
  ): Promise<Record<string, unknown>> {
    if (mockApi) {
      return (await mockApi(
        path,
        { method: "POST", body: JSON.stringify(payload) },
        getMockContext()
      )) as Record<string, unknown>;
    }
    const response = await fetch(`${apiBase}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: options.signal,
      credentials: "same-origin",
    });
    return (await response.json()) as Record<string, unknown>;
  }

  async function publicApi<Path extends ApiPathInput>(
    path: Path,
    payload: PostPayload<Path> = {} as PostPayload<Path>,
    options: Pick<RequestInit, "signal"> = {}
  ): Promise<PostResponse<Path>> {
    return (await publicApiUnchecked(path, payload, options)) as PostResponse<Path>;
  }

  return { api, apiUnchecked, publicApi, publicApiUnchecked };
}
