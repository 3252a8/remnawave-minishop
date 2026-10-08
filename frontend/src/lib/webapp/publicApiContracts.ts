import type { paths } from "../api/openapi.generated";

type HttpMethod = "get" | "put" | "post" | "delete" | "patch";
export type RawApiPath = Extract<keyof paths, string>;
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
export type ApiPathInput = StaticApiPathInput | BuiltApiPath<RawApiPath>;

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
export type PatchPayload<Path extends string> = JsonRequestBody<OperationFor<Path, "patch">>;
export type PostResponse<Path extends string> = JsonResponse<OperationFor<Path, "post">>;

export type BootstrapResponse = GetResponse<"/api/bootstrap">;
export type MeResponse = GetResponse<"/api/me">;
export type BalanceResponse = GetResponse<"/api/balance">;
export type BalanceTopupResponse = PostResponse<"/api/balance/topup">;
export type ServerStatusResponse = GetResponse<"/api/status">;
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
export type AuthExternalPendingResponse = PostResponse<"/api/auth/external/pending">;
export type AuthExternalRequestResponse = PostResponse<"/api/auth/external/request">;
export type AuthExternalVerifyResponse = PostResponse<"/api/auth/external/verify">;
export type AuthLogoutResponse = PostResponse<"/api/auth/logout">;
export type AuthSessionResponse = GetResponse<"/api/auth/session">;
export type AuthTokenResponse = PostResponse<"/api/auth/token">;
export type DevicesResponse = GetResponse<"/api/devices">;
export type DevicesDisconnectResponse = PostResponse<"/api/devices/disconnect">;
export type DeviceTopupOptionsResponse = GetResponse<"/api/devices/topup-options">;
export type PaymentCreateResponse = PostResponse<"/api/payments">;
export type PaymentHistoryResponse = GetResponse<"/api/payments/history">;
export type PaymentStatusResponse = GetResponse<"/api/payments/{payment_id}">;
export type PaymentCancelResponse = PostResponse<"/api/payments/{payment_id}/cancel">;
export type QaPaymentCompleteResponse = PostResponse<"/api/payments/{payment_id}/qa/complete">;
export type PlansViewedResponse = PostResponse<"/api/plans/viewed">;
export type PromoApplyResponse = PostResponse<"/api/promo/apply">;
export type PromoStatusResponse = PostResponse<"/api/promo/status">;
export type PromoQuoteResponse = PostResponse<"/api/subscription/quote-promo">;
export type SubscriptionQuoteResponse = PostResponse<"/api/subscription/quote">;
export type ReferralWelcomeBonusResponse = PostResponse<"/api/referral/welcome-bonus/claim">;
export type SubscriptionGuidesResponse = GetResponse<"/api/subscription-guides">;
export type PublicSubscriptionGuidesResponse =
  GetResponse<"/api/subscription-guides/public/{share_token}">;
export type SubscriptionAutoRenewResponse = PostResponse<"/api/subscription/auto-renew">;
export type SubscriptionReissueResponse = PostResponse<"/api/subscription/reissue">;
export type SupportTicketsResponse = GetResponse<"/api/support/tickets">;
export type SupportTicketCreateResponse = PostResponse<"/api/support/tickets">;
export type SupportTicketDetailResponse = GetResponse<"/api/support/tickets/{id}">;
export type SupportTicketReplyResponse = PostResponse<"/api/support/tickets/{id}/messages">;
export type SupportTicketReadResponse = PostResponse<"/api/support/tickets/{id}/read">;
export type SupportTicketTypingResponse = PostResponse<"/api/support/tickets/{id}/typing">;
export type SupportUnreadResponse = GetResponse<"/api/support/unread">;
export type TariffChangeResponse = PostResponse<"/api/tariffs/change">;
export type TariffChangeOptionsResponse = GetResponse<"/api/tariffs/change-options">;
export type TariffChangePaymentResponse = PostResponse<"/api/tariffs/change-payment">;
export type TariffTopupOptionsResponse = GetResponse<"/api/tariffs/topup-options">;
export type TrialActivateResponse = PostResponse<"/api/trial/activate">;
export type PartnerOverviewResponse = GetResponse<"/api/partner/overview">;
export type PartnerApplicationCreateResponse = PostResponse<"/api/partner/applications">;
export type PartnerClientsResponse = GetResponse<"/api/partner/clients">;
export type PartnerCommissionsResponse = GetResponse<"/api/partner/commissions">;
export type PartnerWithdrawalsResponse = GetResponse<"/api/partner/withdrawals">;
export type PartnerWithdrawalCreateResponse = PostResponse<"/api/partner/withdrawals">;
export type PartnerWithdrawalCancelResponse = PostResponse<"/api/partner/withdrawals/{id}/cancel">;
export type PartnerBalanceRenewResponse = PostResponse<"/api/partner/balance/renew">;
