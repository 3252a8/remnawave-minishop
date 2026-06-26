import { buildPaymentStatusPath, buildTariffTopupOptionsPath } from "./publicApi";
import type {
  ApiClient,
  DeviceTopupOptionsResponse,
  PaymentCreateResponse,
  PaymentStatusResponse,
  PostPayload,
  SubscriptionAutoRenewResponse,
  TariffChangeOptionsResponse,
  TariffChangePaymentResponse,
  TariffChangeResponse,
  TariffTopupOptionsResponse,
} from "./publicApi";

type BillingApi = ApiClient["api"];
type BillingPlan = Record<string, unknown>;
type BillingAction = Record<string, unknown> & { mode?: string };
type BillingTarget = Record<string, unknown> & { tariff_key?: string };

export type BillingActions = {
  fetchTopupOptions(kind: string): Promise<TariffTopupOptionsResponse>;
  fetchDeviceTopupOptions(): Promise<DeviceTopupOptionsResponse>;
  fetchTariffChangeOptions(): Promise<TariffChangeOptionsResponse>;
  postPayment(body: PostPayload<"/api/payments">): Promise<PaymentCreateResponse>;
  fetchPaymentStatus(paymentId: string | number): Promise<PaymentStatusResponse>;
  postTariffChange(body: PostPayload<"/api/tariffs/change">): Promise<TariffChangeResponse>;
  postTariffChangePayment(
    body: PostPayload<"/api/tariffs/change-payment">
  ): Promise<TariffChangePaymentResponse>;
  postAutoRenew(enabled: boolean): Promise<SubscriptionAutoRenewResponse>;
  planPaymentBody(
    plan: BillingPlan,
    method: string,
    options?: { renewHwidDevices?: boolean }
  ): PostPayload<"/api/payments">;
  topupPaymentBody(
    plan: BillingPlan,
    method: string,
    fallbackTariffKey?: string | null
  ): PostPayload<"/api/payments">;
  deviceTopupPaymentBody(
    plan: BillingPlan,
    method: string,
    fallbackTariffKey?: string | null
  ): PostPayload<"/api/payments">;
  changePaymentBody(
    action: BillingAction,
    target: BillingTarget,
    method: string
  ): PostPayload<"/api/tariffs/change-payment">;
};

export function createBillingActions({ api }: { api: BillingApi }): BillingActions {
  async function fetchTopupOptions(kind: string): Promise<TariffTopupOptionsResponse> {
    return api(buildTariffTopupOptionsPath(kind));
  }

  async function fetchDeviceTopupOptions(): Promise<DeviceTopupOptionsResponse> {
    return api("/devices/topup-options");
  }

  async function fetchTariffChangeOptions(): Promise<TariffChangeOptionsResponse> {
    return api("/tariffs/change-options");
  }

  async function postPayment(body: PostPayload<"/api/payments">): Promise<PaymentCreateResponse> {
    return api("/payments", { method: "POST", body: JSON.stringify(body) });
  }

  async function fetchPaymentStatus(paymentId: string | number): Promise<PaymentStatusResponse> {
    return api(buildPaymentStatusPath(paymentId));
  }

  async function postTariffChange(
    body: PostPayload<"/api/tariffs/change">
  ): Promise<TariffChangeResponse> {
    return api("/tariffs/change", { method: "POST", body: JSON.stringify(body) });
  }

  async function postTariffChangePayment(
    body: PostPayload<"/api/tariffs/change-payment">
  ): Promise<TariffChangePaymentResponse> {
    return api("/tariffs/change-payment", { method: "POST", body: JSON.stringify(body) });
  }

  async function postAutoRenew(enabled: boolean): Promise<SubscriptionAutoRenewResponse> {
    return api("/subscription/auto-renew", {
      method: "POST",
      body: JSON.stringify({ enabled: Boolean(enabled) }),
    });
  }

  function setOptionalString(body: Record<string, unknown>, key: string, value: unknown) {
    if (value !== null && typeof value !== "undefined" && String(value)) {
      body[key] = String(value);
    }
  }

  function planPaymentBody(
    plan: BillingPlan,
    method: string,
    options: { renewHwidDevices?: boolean } = {}
  ): PostPayload<"/api/payments"> {
    const body: Record<string, unknown> = {
      months: plan.months,
      traffic_gb: plan.traffic_gb,
      device_count: plan.device_count,
      renew_hwid_devices: Boolean(options.renewHwidDevices),
      method,
    };
    setOptionalString(body, "tariff_key", plan.tariff_key);
    setOptionalString(body, "sale_mode", plan.sale_mode);
    return body as PostPayload<"/api/payments">;
  }

  function topupPaymentBody(
    plan: BillingPlan,
    method: string,
    fallbackTariffKey?: string | null
  ): PostPayload<"/api/payments"> {
    const body: Record<string, unknown> = {
      months: plan.months,
      traffic_gb: plan.traffic_gb,
      sale_mode: String(plan.sale_mode || "topup"),
      method,
    };
    setOptionalString(body, "tariff_key", plan.tariff_key || fallbackTariffKey);
    return body as PostPayload<"/api/payments">;
  }

  function deviceTopupPaymentBody(
    plan: BillingPlan,
    method: string,
    fallbackTariffKey?: string | null
  ): PostPayload<"/api/payments"> {
    const body: Record<string, unknown> = {
      months: plan.device_count || plan.months,
      device_count: plan.device_count || plan.months,
      sale_mode: String(plan.sale_mode || "hwid_devices"),
      method,
    };
    setOptionalString(body, "tariff_key", plan.tariff_key || fallbackTariffKey);
    return body as PostPayload<"/api/payments">;
  }

  function changePaymentBody(
    action: BillingAction,
    target: BillingTarget,
    method: string
  ): PostPayload<"/api/tariffs/change-payment"> {
    const withTarget = (
      body: Record<string, unknown>
    ): PostPayload<"/api/tariffs/change-payment"> => {
      setOptionalString(body, "tariff_key", target.tariff_key);
      return body as PostPayload<"/api/tariffs/change-payment">;
    };

    if (action.mode === "buy_package") {
      return withTarget({
        traffic_gb: action.traffic_gb,
        months: action.traffic_gb,
        sale_mode: "topup",
        method,
      });
    }
    if (action.mode === "buy_period") {
      return withTarget({
        months: action.months,
        method,
      });
    }
    return withTarget({ method });
  }

  return {
    fetchTopupOptions,
    fetchDeviceTopupOptions,
    fetchTariffChangeOptions,
    postPayment,
    fetchPaymentStatus,
    postTariffChange,
    postTariffChangePayment,
    postAutoRenew,
    planPaymentBody,
    topupPaymentBody,
    deviceTopupPaymentBody,
    changePaymentBody,
  };
}
