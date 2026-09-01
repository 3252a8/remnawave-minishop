import {
  buildDeviceTopupOptionsPath,
  buildPaymentCancelPath,
  buildPaymentStatusPath,
  buildPaymentsPath,
  buildPlansViewedPath,
  buildSubscriptionPromoQuotePath,
  buildSubscriptionQuotePath,
  buildSubscriptionAutoRenewPath,
  buildSubscriptionReissuePath,
  buildTariffChangeOptionsPath,
  buildTariffChangePath,
  buildTariffChangePaymentPath,
  buildTariffTopupOptionsPath,
} from "./publicApi";
import type {
  WebappBillingAction,
  WebappBillingPlan,
  WebappBillingTarget,
  WebappRecord,
} from "./domainTypes";
import type {
  ApiClient,
  DeviceTopupOptionsResponse,
  PaymentCreateResponse,
  PaymentCancelResponse,
  PaymentStatusResponse,
  PlansViewedResponse,
  PostPayload,
  PromoQuoteResponse,
  SubscriptionAutoRenewResponse,
  SubscriptionReissueResponse,
  SubscriptionQuoteResponse,
  TariffChangeOptionsResponse,
  TariffChangePaymentResponse,
  TariffChangeResponse,
  TariffTopupOptionsResponse,
} from "./publicApi";
import type { CheckoutAddonSelection } from "./tariffs";

type BillingApi = ApiClient["api"];
type BillingPlan = WebappBillingPlan;
type BillingAction = WebappBillingAction;
type BillingTarget = WebappBillingTarget;
export type PartnerBalancePaymentOptions = {
  balanceSource?: "user" | "partner" | null;
  usePartnerBalance?: boolean;
  checkoutAddons?: CheckoutAddonSelection;
};

export type BillingActions = {
  fetchTopupOptions(kind: string): Promise<TariffTopupOptionsResponse>;
  fetchDeviceTopupOptions(): Promise<DeviceTopupOptionsResponse>;
  fetchTariffChangeOptions(): Promise<TariffChangeOptionsResponse>;
  notifyPlansViewed(body: PostPayload<"/api/plans/viewed">): Promise<PlansViewedResponse>;
  postPayment(body: PostPayload<"/api/payments">): Promise<PaymentCreateResponse>;
  cancelPayment(paymentId: string | number): Promise<PaymentCancelResponse>;
  fetchPaymentStatus(paymentId: string | number): Promise<PaymentStatusResponse>;
  quotePromo(body: PostPayload<"/api/subscription/quote-promo">): Promise<PromoQuoteResponse>;
  quoteSubscription(
    body: PostPayload<"/api/subscription/quote">
  ): Promise<SubscriptionQuoteResponse>;
  postTariffChange(body: PostPayload<"/api/tariffs/change">): Promise<TariffChangeResponse>;
  postTariffChangePayment(
    body: PostPayload<"/api/tariffs/change-payment">
  ): Promise<TariffChangePaymentResponse>;
  postAutoRenew(enabled: boolean): Promise<SubscriptionAutoRenewResponse>;
  postSubscriptionReissue(): Promise<SubscriptionReissueResponse>;
  planPaymentBody(
    plan: BillingPlan,
    method: string,
    options?: {
      renewHwidDevices?: boolean;
      promoCode?: string | null;
      balanceSource?: "user" | "partner" | null;
      usePartnerBalance?: boolean;
      checkoutAddons?: CheckoutAddonSelection;
    }
  ): PostPayload<"/api/payments">;
  topupPaymentBody(
    plan: BillingPlan,
    method: string,
    fallbackTariffKey?: string | null,
    promoCode?: string | null,
    usePartnerBalance?: boolean,
    balanceSource?: "user" | "partner" | null
  ): PostPayload<"/api/payments">;
  deviceTopupPaymentBody(
    plan: BillingPlan,
    method: string,
    fallbackTariffKey?: string | null,
    promoCode?: string | null,
    usePartnerBalance?: boolean,
    balanceSource?: "user" | "partner" | null
  ): PostPayload<"/api/payments">;
  changePaymentBody(
    action: BillingAction,
    target: BillingTarget,
    method: string,
    usePartnerBalance?: boolean,
    balanceSource?: "user" | "partner" | null
  ): PostPayload<"/api/tariffs/change-payment">;
};

export function createBillingActions({ api }: { api: BillingApi }): BillingActions {
  async function fetchTopupOptions(kind: string): Promise<TariffTopupOptionsResponse> {
    return api(buildTariffTopupOptionsPath(kind));
  }

  async function fetchDeviceTopupOptions(): Promise<DeviceTopupOptionsResponse> {
    return api(buildDeviceTopupOptionsPath());
  }

  async function fetchTariffChangeOptions(): Promise<TariffChangeOptionsResponse> {
    return api(buildTariffChangeOptionsPath());
  }

  async function notifyPlansViewed(
    body: PostPayload<"/api/plans/viewed">
  ): Promise<PlansViewedResponse> {
    return api(buildPlansViewedPath(), { method: "POST", body: JSON.stringify(body) });
  }

  async function postPayment(body: PostPayload<"/api/payments">): Promise<PaymentCreateResponse> {
    return api(buildPaymentsPath(), { method: "POST", body: JSON.stringify(body) });
  }

  async function cancelPayment(paymentId: string | number): Promise<PaymentCancelResponse> {
    return api(buildPaymentCancelPath(paymentId), { method: "POST" });
  }

  async function fetchPaymentStatus(paymentId: string | number): Promise<PaymentStatusResponse> {
    return api(buildPaymentStatusPath(paymentId));
  }

  async function quotePromo(
    body: PostPayload<"/api/subscription/quote-promo">
  ): Promise<PromoQuoteResponse> {
    return api(buildSubscriptionPromoQuotePath(), { method: "POST", body: JSON.stringify(body) });
  }

  async function quoteSubscription(
    body: PostPayload<"/api/subscription/quote">
  ): Promise<SubscriptionQuoteResponse> {
    return api(buildSubscriptionQuotePath(), { method: "POST", body: JSON.stringify(body) });
  }

  async function postTariffChange(
    body: PostPayload<"/api/tariffs/change">
  ): Promise<TariffChangeResponse> {
    return api(buildTariffChangePath(), { method: "POST", body: JSON.stringify(body) });
  }

  async function postTariffChangePayment(
    body: PostPayload<"/api/tariffs/change-payment">
  ): Promise<TariffChangePaymentResponse> {
    return api(buildTariffChangePaymentPath(), { method: "POST", body: JSON.stringify(body) });
  }

  async function postAutoRenew(enabled: boolean): Promise<SubscriptionAutoRenewResponse> {
    return api(buildSubscriptionAutoRenewPath(), {
      method: "POST",
      body: JSON.stringify({ enabled: Boolean(enabled) }),
    });
  }

  async function postSubscriptionReissue(): Promise<SubscriptionReissueResponse> {
    return api(buildSubscriptionReissuePath(), {
      method: "POST",
      body: JSON.stringify({}),
    });
  }

  function setOptionalString(body: WebappRecord, key: string, value: unknown) {
    if (value !== null && typeof value !== "undefined" && String(value)) {
      body[key] = String(value);
    }
  }

  function planPaymentBody(
    plan: BillingPlan,
    method: string,
    options: {
      renewHwidDevices?: boolean;
      promoCode?: string | null;
      balanceSource?: "user" | "partner" | null;
      usePartnerBalance?: boolean;
      checkoutAddons?: CheckoutAddonSelection;
    } = {}
  ): PostPayload<"/api/payments"> {
    const hasDeviceCheckoutAddon = Number(options.checkoutAddons?.device_count || 0) > 0;
    const body: WebappRecord = {
      months: plan.months,
      traffic_gb: plan.traffic_gb,
      device_count: plan.device_count,
      renew_hwid_devices: Boolean(options.renewHwidDevices) && !hasDeviceCheckoutAddon,
      balance_source: options.balanceSource || (options.usePartnerBalance ? "partner" : null),
      use_partner_balance: Boolean(options.usePartnerBalance),
      method,
    };
    setOptionalString(body, "tariff_key", plan.tariff_key);
    setOptionalString(body, "sale_mode", plan.sale_mode);
    setOptionalString(body, "promo_code", options.promoCode);
    if (options.checkoutAddons) {
      body.checkout_addons = options.checkoutAddons;
    }
    return body as PostPayload<"/api/payments">;
  }

  function topupPaymentBody(
    plan: BillingPlan,
    method: string,
    fallbackTariffKey?: string | null,
    promoCode?: string | null,
    usePartnerBalance?: boolean,
    balanceSource?: "user" | "partner" | null
  ): PostPayload<"/api/payments"> {
    const body: WebappRecord = {
      months: plan.months,
      traffic_gb: plan.traffic_gb,
      sale_mode: String(plan.sale_mode || "topup"),
      balance_source: balanceSource || (usePartnerBalance ? "partner" : null),
      use_partner_balance: Boolean(usePartnerBalance),
      method,
    };
    setOptionalString(body, "tariff_key", plan.tariff_key || fallbackTariffKey);
    setOptionalString(body, "promo_code", promoCode);
    return body as PostPayload<"/api/payments">;
  }

  function deviceTopupPaymentBody(
    plan: BillingPlan,
    method: string,
    fallbackTariffKey?: string | null,
    promoCode?: string | null,
    usePartnerBalance?: boolean,
    balanceSource?: "user" | "partner" | null
  ): PostPayload<"/api/payments"> {
    const body: WebappRecord = {
      months: plan.device_count || plan.months,
      device_count: plan.device_count || plan.months,
      sale_mode: String(plan.sale_mode || "hwid_devices"),
      balance_source: balanceSource || (usePartnerBalance ? "partner" : null),
      use_partner_balance: Boolean(usePartnerBalance),
      method,
    };
    setOptionalString(body, "tariff_key", plan.tariff_key || fallbackTariffKey);
    setOptionalString(body, "promo_code", promoCode);
    return body as PostPayload<"/api/payments">;
  }

  function changePaymentBody(
    action: BillingAction,
    target: BillingTarget,
    method: string,
    usePartnerBalance?: boolean,
    balanceSource?: "user" | "partner" | null
  ): PostPayload<"/api/tariffs/change-payment"> {
    const withTarget = (body: WebappRecord): PostPayload<"/api/tariffs/change-payment"> => {
      setOptionalString(body, "tariff_key", target.tariff_key);
      return body as PostPayload<"/api/tariffs/change-payment">;
    };

    if (action.mode === "buy_package") {
      return withTarget({
        traffic_gb: action.traffic_gb,
        months: action.traffic_gb,
        sale_mode: "topup",
        balance_source: balanceSource || (usePartnerBalance ? "partner" : null),
        use_partner_balance: Boolean(usePartnerBalance),
        method,
      });
    }
    if (action.mode === "buy_period") {
      return withTarget({
        months: action.months,
        balance_source: balanceSource || (usePartnerBalance ? "partner" : null),
        use_partner_balance: Boolean(usePartnerBalance),
        method,
      });
    }
    return withTarget({
      method,
      balance_source: balanceSource || (usePartnerBalance ? "partner" : null),
      use_partner_balance: Boolean(usePartnerBalance),
    });
  }

  return {
    fetchTopupOptions,
    fetchDeviceTopupOptions,
    fetchTariffChangeOptions,
    notifyPlansViewed,
    postPayment,
    cancelPayment,
    quotePromo,
    quoteSubscription,
    fetchPaymentStatus,
    postTariffChange,
    postTariffChangePayment,
    postAutoRenew,
    postSubscriptionReissue,
    planPaymentBody,
    topupPaymentBody,
    deviceTopupPaymentBody,
    changePaymentBody,
  };
}
