import { unwrap } from "../publicApi";
import type { PartnerBalancePaymentOptions } from "../billingActions";
import type { CheckoutAddonPreset } from "../deeplinks.js";
import type {
  BillingOptionsResponse,
  DeviceTopupOptions,
  PendingPaymentView,
  PlanView,
  SubscriptionView,
  TariffChangeAction,
  TariffChangeOptions,
  TariffChangeTarget,
  TariffView,
  WebappRecord,
} from "../types";

export type BillingRecord = WebappRecord & {
  action?: string;
  actions?: BillingRecord[];
  available?: boolean;
  hwid_renewal?: BillingRecord;
  key?: string;
  message?: string;
  mode?: string;
  paid?: boolean;
  payment_id?: string | number;
  payment_url?: string | null;
  plans?: BillingRecord[];
  sale_mode?: string;
  status?: string;
  tariff_key?: string;
  targets?: BillingRecord[];
  topup_kind?: string;
};
export type BillingState = {
  paymentModalOpen: boolean;
  paymentStep: string;
  selectedTariffKey: string;
  selectedPlan: PlanView | null;
  selectedMethod: string;
  renewHwidDevices: boolean;
  paymentStartedWithActiveSubscription: boolean;
  topupModalOpen: boolean;
  topupKind: string;
  deviceTopupModalOpen: boolean;
  changeModalOpen: boolean;
  topupOptions: BillingOptionsResponse | null;
  deviceTopupOptions: DeviceTopupOptions | null;
  changeOptions: TariffChangeOptions | null;
  selectedTopupPlan: PlanView | null;
  selectedDeviceTopupPlan: PlanView | null;
  selectedChangeTarget: TariffChangeTarget | null;
  selectedChangeAction: TariffChangeAction | null;
  changeConfirmOpen: boolean;
  tariffActionBusy: boolean;
  payBusy: boolean;
  checkoutPromoInput: string;
  checkoutPromoAutoApply: boolean;
  checkoutPromoAppliedCode: string;
  checkoutPromoStatus: string;
  checkoutPromoIsError: boolean;
  checkoutPromoPriceText: string;
  checkoutPromoEffectiveAmount: number;
  checkoutPromoDiscountPercent: number;
  checkoutPromoAppliesTo: string;
  checkoutPromoMinSubscriptionMonths: number | null;
  checkoutPromoMinTrafficGb: number | null;
  checkoutAddonPreset: CheckoutAddonPreset | null;
};
export type BillingStore = BillingState & {
  update(updater: (snapshot: BillingState) => BillingState): void;
  openPaymentModal(
    tariffMode: boolean,
    singleTariffMode: boolean,
    tariffCatalog: TariffView[],
    subscription: SubscriptionView,
    plans: PlanView[],
    defaultMethod?: string,
    options?: WebappRecord
  ): void;
  closePaymentModal(): void;
  selectTariff(tariff: TariffView, plans?: PlanView[]): void;
  continueWithSelectedTariff(selectedTariffPlans?: PlanView[]): void;
  backToTariffList(subscription: SubscriptionView, tariffCatalog?: TariffView[]): void;
  createPayment(options?: PartnerBalancePaymentOptions): Promise<void>;
  resumePendingPayment(payment: PendingPaymentView): Promise<void>;
  cancelPendingPayment(payment: PendingPaymentView): Promise<void>;
  setCheckoutPromoInput(value: string): void;
  applyCheckoutPromo(): Promise<void>;
  clearCheckoutPromo(): void;
  openTopupModal(kind?: string, defaultMethod?: string): void;
  closeTopupModal(): void;
  loadTopupOptions(kind: string): Promise<void>;
  createTopupPayment(options?: PartnerBalancePaymentOptions): Promise<void>;
  openTariffChangeModal(defaultMethod?: string): void;
  closeTariffChangeModal(): void;
  openTariffChangeConfirm(): void;
  closeTariffChangeConfirm(): void;
  loadTariffChangeOptions(): Promise<void>;
  applyTariffChange(options?: PartnerBalancePaymentOptions): Promise<void>;
  createTariffChangePayment(options?: PartnerBalancePaymentOptions): Promise<void>;
  openDeviceTopupModal(defaultMethod?: string): void;
  closeDeviceTopupModal(): void;
  loadDeviceTopupOptions(): Promise<void>;
  createDeviceTopupPayment(options?: PartnerBalancePaymentOptions): Promise<void>;
};

export function asBillingRecord(value: unknown): BillingRecord {
  return value && typeof value === "object" ? (value as BillingRecord) : {};
}

export function billingRecordArray<T extends WebappRecord = BillingRecord>(value: unknown): T[] {
  return Array.isArray(value)
    ? (value.filter((item) => item && typeof item === "object") as T[])
    : [];
}

export function billingStringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function billingSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function unwrapBilling<T extends { ok: boolean }>(response: T): T & BillingRecord {
  return unwrap(response) as T & BillingRecord;
}
