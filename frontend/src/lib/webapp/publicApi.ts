import { readCookie } from "./session.js";
import type { paths } from "../api/openapi.generated";

type HttpMethod = "get" | "put" | "post" | "delete" | "patch";
type RawApiPath = Extract<keyof paths, string>;
export type ApiPath = RawApiPath;

type ExpandPathPath<Path extends string> = Path extends `${infer Prefix}/{${string}}${infer Suffix}`
  ? `${Prefix}/${string}${ExpandPathPath<Suffix>}`
  : Path;

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

declare const API_PATH_TEMPLATE: unique symbol;
export type BuiltApiPath<Template extends RawApiPath> = string & {
  readonly [API_PATH_TEMPLATE]: Template;
};

type ExcludeParameterized<Path extends string> = Path extends `${string}{${string}}${string}`
  ? never
  : Path;
type StaticApiPath = ExcludeParameterized<RawApiPath>;
type StaticApiPathWithoutPrefix = StaticApiPath extends `/api${infer Rest}` ? Rest : never;
type StaticApiPathInput =
  | StaticApiPath
  | `${StaticApiPath}?${string}`
  | StaticApiPathWithoutPrefix
  | `${StaticApiPathWithoutPrefix}?${string}`;
type ApiPathInput = StaticApiPathInput | BuiltApiPath<RawApiPath>;

type KnownApiPath<Path extends string> =
  Path extends BuiltApiPath<infer Template>
    ? Template
    : Path extends RawApiPath
      ? Path
      : Path extends StaticApiPathInput
        ? ResolvedApiPath<Path>
        : never;

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
type MethodForOptions<Options> = Options extends { method?: infer Method }
  ? Method extends string
    ? Lowercase<Method> extends HttpMethod
      ? Lowercase<Method>
      : HttpMethod
    : "get"
  : "get";
export type ApiResponseFor<Path extends string, Options = undefined> = JsonResponse<
  OperationFor<Path, MethodForOptions<Options>>
>;
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
export type PromoStatusResponse = PostResponse<"/api/promo/status">;
export type PromoQuoteResponse = PostResponse<"/api/subscription/quote-promo">;
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

export type AccountEmailRequestPath = "/account/email/request";
export type AccountEmailVerifyPath = "/account/email/verify";
export type AccountLanguagePath = "/account/language";
export type AccountPasswordRequestPath = "/account/password/request";
export type AccountPasswordConfirmPath = "/account/password/confirm";
export type AccountTelegramLinkPath = "/account/telegram/link";
export type AuthEmailMagicPath = "/auth/email/magic";
export type AuthEmailPasswordPath = "/auth/email/password";
export type AuthEmailRequestPath = "/auth/email/request";
export type AuthEmailVerifyPath = "/auth/email/verify";
export type AuthLogoutPath = "/auth/logout";
export type AuthTokenPath = "/auth/token";
export type DeviceTopupOptionsPath = "/devices/topup-options";
export type DevicesDisconnectPath = "/devices/disconnect";
export type TariffChangeOptionsPath = "/tariffs/change-options";
export type TariffChangePath = "/tariffs/change";
export type TariffChangePaymentPath = "/tariffs/change-payment";
export type SubscriptionAutoRenewPath = "/subscription/auto-renew";
export type SubscriptionPromoQuotePath = "/subscription/quote-promo";
export type ReferralWelcomeBonusClaimPath = "/referral/welcome-bonus/claim";
export type PromoApplyPath = "/promo/apply";
export type PromoStatusPath = "/promo/status";
export type TrialActivatePath = "/trial/activate";
export type SupportTicketsListPath = "/support/tickets" | `/support/tickets?${string}`;
export type SupportUnreadPath = "/support/unread";
export type SubscriptionGuidesPath = "/subscription-guides";
export type PublicSubscriptionGuidesPath =
  BuiltApiPath<"/api/subscription-guides/public/{share_token}">;
export type PaymentsPath = "/payments";

type MockContext = Record<string, unknown>;
export type MockApi = (
  path: string,
  options: RequestInit,
  context: MockContext
) => unknown | Promise<unknown>;

type ApiClientOptions = {
  apiBase?: string;
  csrfCookieName?: string;
  getAuthToken?: () => string;
  getCsrfToken?: () => string;
  onUnauthorized?: () => void;
  mockApi?: MockApi | null;
  getMockContext?: () => MockContext;
  requestTimeoutMs?: number;
};

const DEFAULT_API_REQUEST_TIMEOUT_MS = 15000;

function apiTimeoutError(): Error {
  const error = new Error("api_request_timeout");
  error.name = "TimeoutError";
  return error;
}

function requestSignal(
  existingSignal: AbortSignal | null | undefined,
  timeoutMs: number
): { signal: AbortSignal | undefined; cleanup: () => void } {
  const timeout = Math.max(0, Number(timeoutMs || 0));
  if (timeout <= 0 || typeof AbortController === "undefined") {
    return { signal: existingSignal || undefined, cleanup: () => {} };
  }

  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  const abortFromExisting = () => controller.abort(existingSignal?.reason);

  if (existingSignal?.aborted) {
    controller.abort(existingSignal.reason);
  } else {
    existingSignal?.addEventListener("abort", abortFromExisting, { once: true });
  }

  timeoutId = setTimeout(() => {
    if (!controller.signal.aborted) controller.abort(apiTimeoutError());
  }, timeout);

  return {
    signal: controller.signal,
    cleanup: () => {
      if (timeoutId) clearTimeout(timeoutId);
      existingSignal?.removeEventListener("abort", abortFromExisting);
    },
  };
}

export type ApiClient = {
  api<Path extends ApiPathInput, Options extends RequestInit | undefined = undefined>(
    path: Path,
    options?: Options
  ): Promise<ApiResponseFor<Path, Options>>;
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

function builtApiPath<Template extends RawApiPath>(path: string): BuiltApiPath<Template> {
  return path as BuiltApiPath<Template>;
}

export type MePath = "/me" | "/me?fresh=1";
export function buildMePath(fresh: boolean = false): MePath {
  return fresh ? "/me?fresh=1" : "/me";
}

export function buildAccountEmailRequestPath(): AccountEmailRequestPath {
  return "/account/email/request";
}

export function buildAccountEmailVerifyPath(): AccountEmailVerifyPath {
  return "/account/email/verify";
}

export function buildAccountLanguagePath(): AccountLanguagePath {
  return "/account/language";
}

export function buildAccountPasswordRequestPath(): AccountPasswordRequestPath {
  return "/account/password/request";
}

export function buildAccountPasswordConfirmPath(): AccountPasswordConfirmPath {
  return "/account/password/confirm";
}

export function buildAccountTelegramLinkPath(): AccountTelegramLinkPath {
  return "/account/telegram/link";
}

export function buildAuthEmailMagicPath(): AuthEmailMagicPath {
  return "/auth/email/magic";
}

export function buildAuthEmailPasswordPath(): AuthEmailPasswordPath {
  return "/auth/email/password";
}

export function buildAuthEmailRequestPath(): AuthEmailRequestPath {
  return "/auth/email/request";
}

export function buildAuthEmailVerifyPath(): AuthEmailVerifyPath {
  return "/auth/email/verify";
}

export function buildAuthLogoutPath(): AuthLogoutPath {
  return "/auth/logout";
}

export function buildAuthTokenPath(): AuthTokenPath {
  return "/auth/token";
}

export function buildDevicesPath(): "/devices" {
  return "/devices";
}

export function buildDevicesDisconnectPath(): DevicesDisconnectPath {
  return "/devices/disconnect";
}

export function buildDeviceTopupOptionsPath(): DeviceTopupOptionsPath {
  return "/devices/topup-options";
}

export type AdminHealthPath = "/admin/health" | "/admin/health?refresh=1";
export function buildAdminHealthPath(refresh: boolean = false): AdminHealthPath {
  return refresh ? "/admin/health?refresh=1" : "/admin/health";
}

export type TariffTopupOptionsPath = `/tariffs/topup-options?kind=${string}`;
export function buildTariffTopupOptionsPath(kind: string): TariffTopupOptionsPath {
  return `/tariffs/topup-options?kind=${encodeURIComponent(String(kind))}`;
}

export type PaymentStatusPath = BuiltApiPath<"/api/payments/{payment_id}">;
export function buildPaymentStatusPath(paymentId: string | number): PaymentStatusPath {
  return builtApiPath<"/api/payments/{payment_id}">(
    `/payments/${encodeURIComponent(String(paymentId))}`
  );
}

export type SupportTicketPath = BuiltApiPath<"/api/support/tickets/{id}">;
export function buildSupportTicketPath(ticketId: string | number): SupportTicketPath {
  return builtApiPath<"/api/support/tickets/{id}">(
    `/support/tickets/${encodeURIComponent(String(ticketId))}`
  );
}

export function buildSupportTicketsPath(params?: URLSearchParams): SupportTicketsListPath {
  const query = params?.toString();
  return (query ? `/support/tickets?${query}` : "/support/tickets") as SupportTicketsListPath;
}

export function buildSupportUnreadPath(): SupportUnreadPath {
  return "/support/unread";
}

export function buildPublicSubscriptionGuidesPath(
  token: string | number
): PublicSubscriptionGuidesPath {
  return builtApiPath<"/api/subscription-guides/public/{share_token}">(
    `/subscription-guides/public/${encodeURIComponent(String(token))}`
  );
}

export function buildTariffChangeOptionsPath(): TariffChangeOptionsPath {
  return "/tariffs/change-options";
}

export function buildTariffChangePath(): TariffChangePath {
  return "/tariffs/change";
}

export function buildTariffChangePaymentPath(): TariffChangePaymentPath {
  return "/tariffs/change-payment";
}

export function buildSubscriptionAutoRenewPath(): SubscriptionAutoRenewPath {
  return "/subscription/auto-renew";
}

export function buildSubscriptionPromoQuotePath(): SubscriptionPromoQuotePath {
  return "/subscription/quote-promo";
}

export function buildReferralWelcomeBonusClaimPath(): ReferralWelcomeBonusClaimPath {
  return "/referral/welcome-bonus/claim";
}

export function buildPromoApplyPath(): PromoApplyPath {
  return "/promo/apply";
}

export function buildPromoStatusPath(): PromoStatusPath {
  return "/promo/status";
}

export function buildTrialActivatePath(): TrialActivatePath {
  return "/trial/activate";
}

export function buildSubscriptionGuidesPath(): SubscriptionGuidesPath {
  return "/subscription-guides";
}

export function buildPaymentsPath(): PaymentsPath {
  return "/payments";
}

export type SupportTicketMessagesPath = BuiltApiPath<"/api/support/tickets/{id}/messages">;
export function buildSupportTicketMessagesPath(
  ticketId: string | number
): SupportTicketMessagesPath {
  return builtApiPath<"/api/support/tickets/{id}/messages">(
    `/support/tickets/${encodeURIComponent(String(ticketId))}/messages`
  );
}

export type SupportTicketReadPath = BuiltApiPath<"/api/support/tickets/{id}/read">;
export function buildSupportTicketReadPath(ticketId: string | number): SupportTicketReadPath {
  return builtApiPath<"/api/support/tickets/{id}/read">(
    `/support/tickets/${encodeURIComponent(String(ticketId))}/read`
  );
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

export type AdminUserPath = BuiltApiPath<"/api/admin/users/{user_id}">;
export function buildAdminUserPath(userId: string | number): AdminUserPath {
  return builtApiPath<"/api/admin/users/{user_id}">(
    `/admin/users/${encodeURIComponent(String(userId))}`
  );
}

export type AdminUsersLogsPath = "/admin/logs" | `/admin/logs?${string}`;
export function buildAdminUserLogsPath(params?: URLSearchParams): AdminUsersLogsPath {
  const query = params?.toString();
  return (query ? `/admin/logs?${query}` : "/admin/logs") as AdminUsersLogsPath;
}

export type AdminUserReferralsPath = BuiltApiPath<"/api/admin/users/{user_id}/referrals">;
export function buildAdminUserReferralsPath(
  userId: string | number,
  params?: URLSearchParams
): AdminUserReferralsPath {
  const base = `/admin/users/${encodeURIComponent(String(userId))}/referrals`;
  const query = params?.toString();
  return builtApiPath<"/api/admin/users/{user_id}/referrals">(query ? `${base}?${query}` : base);
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
  | "traffic-strategy"
  | "hwid-device-limit"
  | "traffic-grant";
type AdminUserActionTemplate =
  | "/api/admin/users/{user_id}/ban"
  | "/api/admin/users/{user_id}/message"
  | "/api/admin/users/{user_id}/message/preview"
  | "/api/admin/users/{user_id}/telegram-profile-link"
  | "/api/admin/users/{user_id}/extend"
  | "/api/admin/users/{user_id}/tariff"
  | "/api/admin/users/{user_id}/reset-trial"
  | "/api/admin/users/{user_id}/premium-override"
  | "/api/admin/users/{user_id}/regular-traffic-override"
  | "/api/admin/users/{user_id}/traffic-strategy"
  | "/api/admin/users/{user_id}/hwid-device-limit"
  | "/api/admin/users/{user_id}/traffic-grant";
export type AdminUserActionPath = BuiltApiPath<AdminUserActionTemplate>;
export function buildAdminUserActionPath(
  userId: string | number,
  action: AdminUserAction
): AdminUserActionPath {
  return builtApiPath<AdminUserActionTemplate>(
    `/admin/users/${encodeURIComponent(String(userId))}/${action}`
  );
}

export type AdminSupportTicketsPath = "/admin/support/tickets" | `/admin/support/tickets?${string}`;
export function buildAdminSupportTicketsPath(params: URLSearchParams): AdminSupportTicketsPath {
  return `/admin/support/tickets?${params.toString()}` as AdminSupportTicketsPath;
}

export type AdminSupportTicketPath = BuiltApiPath<"/api/admin/support/tickets/{id}">;
export function buildAdminSupportTicketPath(ticketId: string | number): AdminSupportTicketPath {
  return builtApiPath<"/api/admin/support/tickets/{id}">(
    `/admin/support/tickets/${encodeURIComponent(String(ticketId))}`
  );
}

export type AdminSupportTicketMessagesPath =
  BuiltApiPath<"/api/admin/support/tickets/{id}/messages">;
export function buildAdminSupportTicketMessagesPath(
  ticketId: string | number
): AdminSupportTicketMessagesPath {
  return builtApiPath<"/api/admin/support/tickets/{id}/messages">(
    `/admin/support/tickets/${encodeURIComponent(String(ticketId))}/messages`
  );
}

export type AdminSupportTicketReadPath = BuiltApiPath<"/api/admin/support/tickets/{id}/read">;
export function buildAdminSupportTicketReadPath(
  ticketId: string | number
): AdminSupportTicketReadPath {
  return builtApiPath<"/api/admin/support/tickets/{id}/read">(
    `/admin/support/tickets/${encodeURIComponent(String(ticketId))}/read`
  );
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

export type AdminPromoPath = BuiltApiPath<"/api/admin/promos/{promo_id}">;
export function buildAdminPromoPath(promoId: string | number): AdminPromoPath {
  return builtApiPath<"/api/admin/promos/{promo_id}">(
    `/admin/promos/${encodeURIComponent(String(promoId))}`
  );
}

export type AdminPromoActivationsPath = BuiltApiPath<"/api/admin/promos/{promo_id}/activations">;
export function buildAdminPromoActivationsPath(
  promoId: string | number,
  params?: URLSearchParams
): AdminPromoActivationsPath {
  const base = `/admin/promos/${encodeURIComponent(String(promoId))}/activations`;
  const query = params?.toString();
  return builtApiPath<"/api/admin/promos/{promo_id}/activations">(
    query ? `${base}?${query}` : base
  );
}

export type AdminAdsPath = "/admin/ads";
export function buildAdminAdsPath(): AdminAdsPath {
  return "/admin/ads";
}

export type AdminAdPath = BuiltApiPath<"/api/admin/ads/{campaign_id}">;
export function buildAdminAdPath(campaignId: string | number): AdminAdPath {
  return builtApiPath<"/api/admin/ads/{campaign_id}">(
    `/admin/ads/${encodeURIComponent(String(campaignId))}`
  );
}

export type AdminAdTogglePath = BuiltApiPath<"/api/admin/ads/{campaign_id}/toggle">;
export function buildAdminAdTogglePath(campaignId: string | number): AdminAdTogglePath {
  return builtApiPath<"/api/admin/ads/{campaign_id}/toggle">(
    `/admin/ads/${encodeURIComponent(String(campaignId))}/toggle`
  );
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

export type AdminPaymentPath = BuiltApiPath<"/api/admin/payments/{payment_id}">;
export function buildAdminPaymentPath(paymentId: string | number): AdminPaymentPath {
  return builtApiPath<"/api/admin/payments/{payment_id}">(
    `/admin/payments/${encodeURIComponent(String(paymentId))}`
  );
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
  getAuthToken = () => "",
  getCsrfToken = () => "",
  onUnauthorized = () => {},
  mockApi = null,
  getMockContext = () => ({}),
  requestTimeoutMs = DEFAULT_API_REQUEST_TIMEOUT_MS,
}: ApiClientOptions = {}): ApiClient {
  const isFormDataBody = (body: BodyInit | null | undefined) =>
    typeof FormData !== "undefined" && body instanceof FormData;

  async function requestJson(
    path: string,
    options: RequestInit = {}
  ): Promise<Record<string, unknown>> {
    if (mockApi) return (await mockApi(path, options, getMockContext())) as Record<string, unknown>;

    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers);

    const csrf = getCsrfToken() || readCookie(csrfCookieName) || "";
    const authToken = getAuthToken();
    if (authToken && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${authToken}`);
    }
    if (csrf && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      headers.set("X-CSRF-Token", csrf);
    }
    if (options.body && !headers.has("Content-Type") && !isFormDataBody(options.body)) {
      headers.set("Content-Type", "application/json");
    }

    const { signal, cleanup } = requestSignal(options.signal, requestTimeoutMs);
    try {
      const response = await fetch(`${apiBase}${path}`, {
        ...options,
        headers,
        credentials: "same-origin",
        signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (response.status === 401) onUnauthorized();
      return payload as Record<string, unknown>;
    } finally {
      cleanup();
    }
  }

  async function api<
    Path extends ApiPathInput,
    Options extends RequestInit | undefined = undefined,
  >(path: Path, options: Options = {} as Options): Promise<ApiResponseFor<Path, Options>> {
    return (await requestJson(path, options)) as ApiResponseFor<Path, Options>;
  }

  async function apiUnchecked(
    path: string,
    options: RequestInit = {}
  ): Promise<Record<string, unknown>> {
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
    const { signal, cleanup } = requestSignal(options.signal, requestTimeoutMs);
    try {
      const response = await fetch(`${apiBase}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal,
        credentials: "same-origin",
      });
      return (await response.json()) as Record<string, unknown>;
    } finally {
      cleanup();
    }
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
