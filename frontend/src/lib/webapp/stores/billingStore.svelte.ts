import type { LoadDataOptions } from "../dataClient";
import type { BillingActions } from "../billingActions";
import { unwrap } from "../publicApi";
import { priceLabel } from "../tariffs";
import {
  openTelegramInvoice as openTelegramInvoiceUrl,
  type TelegramWebApp,
} from "../telegramInvoice";
import type {
  BillingOptionsResponse,
  DeviceTopupOptions,
  PlanView,
  SubscriptionView,
  TariffChangeAction,
  TariffChangeOptions,
  TariffChangeTarget,
  TariffView,
  WebappRecord,
} from "../types";

type BillingRecord = WebappRecord & {
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
type BillingOkRecord = BillingRecord & { ok: boolean };
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
  checkoutPromoAppliedCode: string;
  checkoutPromoStatus: string;
  checkoutPromoIsError: boolean;
  checkoutPromoPriceText: string;
  checkoutPromoDiscountPercent: number;
  checkoutPromoAppliesTo: string;
  checkoutPromoMinSubscriptionMonths: number | null;
  checkoutPromoMinTrafficGb: number | null;
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
  createPayment(): Promise<void>;
  setCheckoutPromoInput(value: string): void;
  applyCheckoutPromo(): Promise<void>;
  clearCheckoutPromo(): void;
  openTopupModal(kind?: string, defaultMethod?: string): void;
  closeTopupModal(): void;
  loadTopupOptions(kind: string): Promise<void>;
  createTopupPayment(): Promise<void>;
  openTariffChangeModal(defaultMethod?: string): void;
  closeTariffChangeModal(): void;
  openTariffChangeConfirm(): void;
  closeTariffChangeConfirm(): void;
  loadTariffChangeOptions(): Promise<void>;
  applyTariffChange(): Promise<void>;
  createTariffChangePayment(): Promise<void>;
  openDeviceTopupModal(defaultMethod?: string): void;
  closeDeviceTopupModal(): void;
  loadDeviceTopupOptions(): Promise<void>;
  createDeviceTopupPayment(): Promise<void>;
};

export function createBillingStore({
  billing,
  loadData,
  t,
  showToast,
  openExternalLink,
  onSubscriptionActivationPending = null,
  onSubscriptionActivated = null,
  tg,
  getTg = null,
  telegramSdk = null,
}: {
  billing: BillingActions;
  loadData: (options?: LoadDataOptions & Record<string, unknown>) => Promise<unknown>;
  t: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  showToast: (message: string) => void;
  openExternalLink: (url: string) => void;
  onSubscriptionActivationPending?: ((context: Record<string, unknown>) => void) | null;
  onSubscriptionActivated?: ((context: Record<string, unknown>) => Promise<void> | void) | null;
  tg?: TelegramWebApp | null;
  getTg?: (() => TelegramWebApp | null) | null;
  telegramSdk?: {
    hasLaunchParams?: () => boolean;
    refresh?: () => TelegramWebApp | null;
    ensureForAction?: () => Promise<TelegramWebApp | null>;
  } | null;
}) {
  function asRecord(value: unknown): BillingRecord {
    return value && typeof value === "object" ? (value as BillingRecord) : {};
  }

  function arrayRecords<T extends WebappRecord = BillingRecord>(value: unknown): T[] {
    return Array.isArray(value)
      ? (value.filter((item) => item && typeof item === "object") as T[])
      : [];
  }

  function stringField(value: unknown): string {
    return typeof value === "string" ? value : "";
  }

  function unwrapBilling<T extends { ok: boolean }>(response: T): T & BillingRecord {
    return unwrap(response) as T & BillingRecord;
  }

  const state = $state<BillingStore>({
    paymentModalOpen: false,
    paymentStep: "tariff",
    selectedTariffKey: "",
    selectedPlan: null,
    selectedMethod: "",
    renewHwidDevices: true,
    paymentStartedWithActiveSubscription: false,
    topupModalOpen: false,
    topupKind: "regular",
    deviceTopupModalOpen: false,
    changeModalOpen: false,
    topupOptions: null,
    deviceTopupOptions: null,
    changeOptions: null,
    selectedTopupPlan: null,
    selectedDeviceTopupPlan: null,
    selectedChangeTarget: null,
    selectedChangeAction: null,
    changeConfirmOpen: false,
    tariffActionBusy: false,
    payBusy: false,
    checkoutPromoInput: "",
    checkoutPromoAppliedCode: "",
    checkoutPromoStatus: "",
    checkoutPromoIsError: false,
    checkoutPromoPriceText: "",
    checkoutPromoDiscountPercent: 0,
    checkoutPromoAppliesTo: "all",
    checkoutPromoMinSubscriptionMonths: null,
    checkoutPromoMinTrafficGb: null,
    update: updateState,
    openPaymentModal,
    closePaymentModal,
    selectTariff,
    continueWithSelectedTariff,
    backToTariffList,
    createPayment,
    setCheckoutPromoInput,
    applyCheckoutPromo,
    clearCheckoutPromo,
    openTopupModal,
    closeTopupModal,
    loadTopupOptions,
    createTopupPayment,
    openTariffChangeModal,
    closeTariffChangeModal,
    openTariffChangeConfirm,
    closeTariffChangeConfirm,
    loadTariffChangeOptions,
    applyTariffChange,
    createTariffChangePayment,
    openDeviceTopupModal,
    closeDeviceTopupModal,
    loadDeviceTopupOptions,
    createDeviceTopupPayment,
  });

  function updateState(updater: (snapshot: BillingState) => BillingState): void {
    const next = updater(state);
    if (next === state) return;
    Object.assign(state, next);
  }

  let topupOptionsRequestId = 0;
  let paymentPollToken = 0;
  let lastCheckoutQuoteKey = "";
  const successfulPaymentIds = new Set<string>();

  function setCheckoutPromoInput(value: string): void {
    state.checkoutPromoInput = value;
    state.checkoutPromoStatus = "";
    state.checkoutPromoIsError = false;
    if (String(value || "").trim() !== String(state.checkoutPromoAppliedCode || "").trim()) {
      state.checkoutPromoAppliedCode = "";
      state.checkoutPromoPriceText = "";
      Object.assign(state, resetCheckoutPromoQuote());
    }
  }

  function optionalNumber(value: unknown): number | null {
    if (value == null || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function resetCheckoutPromoQuote(): Pick<
    BillingState,
    | "checkoutPromoDiscountPercent"
    | "checkoutPromoAppliesTo"
    | "checkoutPromoMinSubscriptionMonths"
    | "checkoutPromoMinTrafficGb"
  > {
    return {
      checkoutPromoDiscountPercent: 0,
      checkoutPromoAppliesTo: "all",
      checkoutPromoMinSubscriptionMonths: null,
      checkoutPromoMinTrafficGb: null,
    };
  }

  function checkoutPromoCode(): string | null {
    const code = String(state.checkoutPromoAppliedCode || "").trim();
    return code || null;
  }

  function checkoutQuoteBody() {
    const s = state;
    const code = String(s.checkoutPromoInput || s.checkoutPromoAppliedCode || "").trim();
    if (!code || !s.selectedMethod) return null;
    if (s.paymentModalOpen && s.selectedPlan) {
      return {
        ...billing.planPaymentBody(s.selectedPlan, s.selectedMethod, {
          renewHwidDevices: s.renewHwidDevices && Boolean(s.selectedPlan?.hwid_renewal?.available),
        }),
        promo_code: code,
      };
    }
    if (s.topupModalOpen && s.selectedTopupPlan) {
      return {
        ...billing.topupPaymentBody(
          s.selectedTopupPlan,
          s.selectedMethod,
          stringField(s.topupOptions?.tariff_key)
        ),
        promo_code: code,
      };
    }
    if (s.deviceTopupModalOpen && s.selectedDeviceTopupPlan) {
      return {
        ...billing.deviceTopupPaymentBody(
          s.selectedDeviceTopupPlan,
          s.selectedMethod,
          stringField(s.deviceTopupOptions?.tariff_key)
        ),
        promo_code: code,
      };
    }
    return null;
  }

  function checkoutPlanKey(plan: PlanView | null): string {
    if (!plan) return "";
    return String(
      plan.id ||
        `${plan.tariff_key || ""}:${plan.sale_mode || ""}:${plan.months || ""}:${plan.traffic_gb || ""}`
    );
  }

  function checkoutQuoteKey(): string {
    const code = String(
      state.checkoutPromoAppliedCode || (state.checkoutPromoIsError ? state.checkoutPromoInput : "")
    ).trim();
    if (!code || !state.selectedMethod) return "";
    if (state.paymentModalOpen && state.selectedPlan) {
      return [
        "payment",
        code,
        state.selectedMethod,
        checkoutPlanKey(state.selectedPlan),
        state.renewHwidDevices ? "hwid" : "no-hwid",
      ].join(":");
    }
    if (state.topupModalOpen && state.selectedTopupPlan) {
      return [
        "topup",
        code,
        state.selectedMethod,
        checkoutPlanKey(state.selectedTopupPlan),
        state.topupKind,
      ].join(":");
    }
    if (state.deviceTopupModalOpen && state.selectedDeviceTopupPlan) {
      return [
        "device",
        code,
        state.selectedMethod,
        checkoutPlanKey(state.selectedDeviceTopupPlan),
      ].join(":");
    }
    return "";
  }

  $effect(() => {
    const key = checkoutQuoteKey();
    if (!key) {
      lastCheckoutQuoteKey = "";
      return;
    }
    if (key === lastCheckoutQuoteKey) return;
    const shouldRefresh = lastCheckoutQuoteKey !== "";
    lastCheckoutQuoteKey = key;
    if (shouldRefresh) void applyCheckoutPromo();
  });

  function promoPriceText(payload: BillingRecord): string {
    const amount = Number(payload.effective_amount || 0);
    const stars = Number(payload.effective_stars || 0);
    if (amount <= 0 && stars <= 0) return "";
    const currency = stringField(payload.currency);
    return priceLabel(
      {
        price: amount,
        stars_price: stars,
        currency: currency || undefined,
      },
      state.selectedMethod
    );
  }

  async function applyCheckoutPromo(): Promise<void> {
    const body = checkoutQuoteBody();
    if (!body) {
      updateState((s) => ({
        ...s,
        checkoutPromoIsError: true,
        checkoutPromoStatus: t("wa_promo_select_plan_first", {}, "Choose a plan first"),
        checkoutPromoPriceText: "",
        ...resetCheckoutPromoQuote(),
      }));
      return;
    }
    const attemptedCode = stringField(body.promo_code);
    try {
      const response = await billing.quotePromo(body);
      const payload = unwrapBilling(response);
      if (!payload.valid) {
        updateState((s) => ({
          ...s,
          checkoutPromoInput: attemptedCode,
          checkoutPromoAppliedCode: "",
          checkoutPromoIsError: true,
          checkoutPromoStatus:
            stringField(payload.reason) ||
            t("wa_promo_activation_failed", {}, "Code does not apply here"),
          checkoutPromoPriceText: "",
          ...resetCheckoutPromoQuote(),
        }));
        return;
      }
      const appliedCode = stringField(payload.code || body.promo_code);
      updateState((s) => ({
        ...s,
        checkoutPromoInput: appliedCode,
        checkoutPromoAppliedCode: appliedCode,
        checkoutPromoIsError: false,
        checkoutPromoStatus: stringField(payload.effect_summary),
        checkoutPromoPriceText: promoPriceText(payload),
        checkoutPromoDiscountPercent: Math.max(0, Number(payload.discount_percent || 0)),
        checkoutPromoAppliesTo: stringField(payload.applies_to) || "all",
        checkoutPromoMinSubscriptionMonths: optionalNumber(payload.min_subscription_months),
        checkoutPromoMinTrafficGb: optionalNumber(payload.min_traffic_gb),
      }));
    } catch (error: unknown) {
      updateState((s) => ({
        ...s,
        checkoutPromoInput: attemptedCode,
        checkoutPromoAppliedCode: "",
        checkoutPromoIsError: true,
        checkoutPromoStatus:
          stringField(asRecord(error).message) || t("wa_promo_activation_failed"),
        checkoutPromoPriceText: "",
        ...resetCheckoutPromoQuote(),
      }));
    }
  }

  function clearCheckoutPromo(): void {
    updateState((s) => ({
      ...s,
      checkoutPromoInput: "",
      checkoutPromoAppliedCode: "",
      checkoutPromoStatus: "",
      checkoutPromoIsError: false,
      checkoutPromoPriceText: "",
      ...resetCheckoutPromoQuote(),
    }));
  }

  function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function isSubscriptionSale(plan: PlanView | null) {
    const saleMode = String(plan?.sale_mode || "subscription").toLowerCase();
    return ![
      "traffic",
      "traffic_package",
      "topup",
      "premium_topup",
      "hwid_devices",
      "hwid_devices_renewal",
    ].includes(saleMode);
  }

  function paymentSuccessContext(s: BillingState, response: BillingRecord = {}) {
    return {
      paymentId: response.payment_id || "",
      initialSubscriptionPayment:
        !s.paymentStartedWithActiveSubscription && isSubscriptionSale(s.selectedPlan),
      renewalSubscriptionPayment:
        s.paymentStartedWithActiveSubscription && isSubscriptionSale(s.selectedPlan),
    };
  }

  async function handlePaymentSuccess(successContext: BillingRecord = {}) {
    const paymentId = String(successContext.paymentId || "");
    if (paymentId && successfulPaymentIds.has(paymentId)) return;
    if (paymentId) {
      successfulPaymentIds.add(paymentId);
      paymentPollToken += 1;
    }
    showToast(t("wa_payment_success", {}, "Payment successful"));
    await loadData({ fresh: true });
    if (
      successContext.initialSubscriptionPayment &&
      typeof onSubscriptionActivated === "function"
    ) {
      await onSubscriptionActivated({ source: "payment", ...successContext });
    }
  }

  function rememberSubscriptionActivationPending(successContext: BillingRecord = {}) {
    if (
      !successContext.initialSubscriptionPayment ||
      typeof onSubscriptionActivationPending !== "function"
    ) {
      return;
    }
    try {
      onSubscriptionActivationPending({ source: "payment", ...successContext });
    } catch (_error) {
      void _error;
    }
  }

  function notifyPaymentPlansViewed(
    tariffMode: boolean,
    singleTariffMode: boolean,
    tariffCatalog: TariffView[],
    subscription: SubscriptionView,
    plans: PlanView[],
    options: WebappRecord = {}
  ): void {
    const catalog = tariffCatalog || [];
    const planList = plans || [];
    const preferredTariffKey = String(options?.preferredTariffKey || "").trim();
    const preferredTariff = preferredTariffKey
      ? catalog.find((tariff) => tariff.key === preferredTariffKey)
      : null;
    const fallbackTariff =
      catalog.find((tariff) => tariff.is_default) ||
      catalog.find((tariff) => tariff.key === "standard") ||
      catalog[0] ||
      null;
    let tariffKey = "";

    if (tariffMode) {
      if (preferredTariff?.key) {
        tariffKey = String(preferredTariff.key);
      } else if (options?.selectDefaultTariff && fallbackTariff?.key) {
        tariffKey = String(fallbackTariff.key);
      } else if (singleTariffMode && catalog[0]?.key) {
        tariffKey = String(catalog[0].key);
      } else if (
        subscription?.active &&
        subscription?.tariff_key &&
        catalog.some((tariff) => tariff.key === subscription.tariff_key)
      ) {
        tariffKey = String(subscription.tariff_key);
      }
    }

    const plansCount = tariffKey
      ? planList.filter((plan) => plan?.tariff_key === tariffKey).length || 1
      : tariffMode
        ? catalog.length || planList.length
        : planList.length;

    void billing
      .notifyPlansViewed({
        plans_count: Math.max(0, plansCount),
        tariff_key: tariffKey || null,
      })
      .catch((_error) => {
        void _error;
      });
  }

  function openPaymentModal(
    tariffMode: boolean,
    singleTariffMode: boolean,
    tariffCatalog: TariffView[],
    subscription: SubscriptionView,
    plans: PlanView[],
    defaultMethod = "",
    options: WebappRecord = {}
  ) {
    notifyPaymentPlansViewed(
      tariffMode,
      singleTariffMode,
      tariffCatalog,
      subscription,
      plans,
      options
    );
    updateState((s) => {
      let step: string;
      let plan = s.selectedPlan;
      let tariffKey = s.selectedTariffKey;
      const catalog = tariffCatalog || [];
      const planList = plans || [];
      const preferredTariffKey = String(options?.preferredTariffKey || "").trim();
      const preferredTariff = preferredTariffKey
        ? catalog.find((tariff) => tariff.key === preferredTariffKey)
        : null;
      const fallbackTariff =
        catalog.find((tariff) => tariff.is_default) ||
        catalog.find((tariff) => tariff.key === "standard") ||
        catalog[0] ||
        null;
      const deeplinkTariff =
        preferredTariff || (options?.selectDefaultTariff ? fallbackTariff : null);

      if (tariffMode) {
        if (deeplinkTariff?.key) {
          tariffKey = String(deeplinkTariff.key);
          plan = planList.find((p) => p?.tariff_key === tariffKey) || null;
          step = options?.preferCheckout && plan ? "checkout" : "tariff";
        } else if (singleTariffMode && catalog[0]?.key) {
          tariffKey = String(catalog[0].key);
          plan = planList.find((p) => p?.tariff_key === tariffKey) || null;
          step = "checkout";
        } else if (
          subscription?.active &&
          subscription?.tariff_key &&
          catalog.some((t) => t.key === subscription.tariff_key)
        ) {
          tariffKey = String(subscription.tariff_key);
          plan = planList.find((p) => p?.tariff_key === tariffKey) || null;
          step = "checkout";
        } else {
          step = "tariff";
          tariffKey = "";
          plan = null;
        }
      } else {
        step = "checkout";
      }
      return {
        ...s,
        paymentModalOpen: true,
        paymentStep: step,
        selectedTariffKey: tariffKey,
        selectedPlan: plan,
        selectedMethod: s.selectedMethod || defaultMethod,
        renewHwidDevices: true,
        paymentStartedWithActiveSubscription: Boolean(subscription?.active),
      };
    });
  }

  function closePaymentModal() {
    updateState((s) => ({ ...s, paymentModalOpen: false }));
  }

  function selectTariff(tariff: TariffView, plans: PlanView[] = []) {
    const key = String(tariff?.key || "").trim();
    if (!key) return;
    updateState((s) => ({
      ...s,
      selectedTariffKey: key,
      selectedPlan: plans.find((plan) => plan?.tariff_key === key) || null,
      renewHwidDevices: true,
    }));
  }

  function continueWithSelectedTariff(selectedTariffPlans: PlanView[] = []) {
    updateState((s) => {
      if (!s.selectedTariffKey) return s;
      return {
        ...s,
        selectedPlan: s.selectedPlan || selectedTariffPlans[0] || null,
        paymentStep: "checkout",
        renewHwidDevices: true,
      };
    });
  }

  function backToTariffList(subscription: SubscriptionView, tariffCatalog: TariffView[] = []) {
    if (
      subscription?.active &&
      subscription?.tariff_key &&
      tariffCatalog.some((t) => t.key === subscription.tariff_key)
    ) {
      return;
    }
    updateState((s) => ({ ...s, paymentStep: "tariff" }));
  }

  function openTopupModal(kind = "regular", defaultMethod = "") {
    const normalizedKind = kind === "premium" ? "premium" : "regular";
    updateState((s) => ({
      ...s,
      topupKind: normalizedKind,
      topupModalOpen: true,
      topupOptions: s.topupOptions?.topup_kind === normalizedKind ? s.topupOptions : null,
      selectedTopupPlan: s.topupOptions?.topup_kind === normalizedKind ? s.selectedTopupPlan : null,
      selectedMethod: s.selectedMethod || defaultMethod,
    }));
    loadTopupOptions(normalizedKind);
  }

  function closeTopupModal() {
    updateState((s) => ({ ...s, topupModalOpen: false }));
  }

  function openDeviceTopupModal(defaultMethod = "") {
    updateState((s) => ({
      ...s,
      deviceTopupModalOpen: true,
      deviceTopupOptions: null,
      selectedDeviceTopupPlan: null,
      selectedMethod: s.selectedMethod || defaultMethod,
    }));
    loadDeviceTopupOptions();
  }

  function closeDeviceTopupModal() {
    updateState((s) => ({ ...s, deviceTopupModalOpen: false }));
  }

  function openTariffChangeModal(defaultMethod = "") {
    updateState((s) => ({
      ...s,
      changeModalOpen: true,
      selectedMethod: s.selectedMethod || defaultMethod,
    }));
    loadTariffChangeOptions();
  }

  function closeTariffChangeModal() {
    updateState((s) => ({ ...s, changeModalOpen: false }));
  }

  function openTariffChangeConfirm() {
    const s = state;
    if (!s.selectedChangeTarget || !s.selectedChangeAction) return;
    updateState((s) => ({ ...s, changeConfirmOpen: true }));
  }

  function closeTariffChangeConfirm() {
    updateState((s) => ({ ...s, changeConfirmOpen: false }));
  }

  async function openTelegramInvoice(url: string, successContext: BillingRecord = {}) {
    return openTelegramInvoiceUrl({
      getTg,
      onFailed: () => showToast(t("wa_payment_create_failed")),
      onPaid: () => handlePaymentSuccess(successContext),
      onUnavailable: () =>
        showToast(
          t(
            "wa_payment_stars_telegram_required",
            {},
            "Open Minishop from the bot in Telegram to pay with Stars"
          )
        ),
      telegramSdk,
      tg,
      url,
    });
  }

  async function handlePaymentResponse(
    response: BillingOkRecord,
    successContext: BillingRecord = {},
    closeModal: () => void = () => {}
  ) {
    if (!response.ok) throw response;
    const payload = unwrapBilling(response);
    showToast(t("wa_payment_created"));
    if (payload.action === "open_invoice") {
      if (!payload.payment_url) throw response;
      const opened = await openTelegramInvoice(payload.payment_url, successContext);
      if (!opened) return false;
    } else if (payload.action === "invoice_sent") {
      startPaymentStatusPolling(payload.payment_id, successContext);
      closeModal();
      return true;
    } else {
      if (!payload.payment_url) throw response;
      openExternalLink(payload.payment_url);
    }
    startPaymentStatusPolling(payload.payment_id, successContext);
    closeModal();
    return true;
  }

  function startPaymentStatusPolling(
    paymentId: string | number | undefined,
    successContext: BillingRecord = {}
  ) {
    if (!paymentId || !billing.fetchPaymentStatus) return;
    const token = ++paymentPollToken;
    void (async () => {
      for (let attempt = 0; attempt < 45 && token === paymentPollToken; attempt += 1) {
        await sleep(attempt === 0 ? 1500 : 2000);
        if (token !== paymentPollToken) return;
        try {
          const status = await billing.fetchPaymentStatus(paymentId);
          if (!status?.ok) continue;
          const payload = unwrapBilling(status);
          if (payload.paid || payload.status === "succeeded") {
            await handlePaymentSuccess({ ...successContext, paymentId });
            return;
          }
          const normalized = String(payload.status || "").toLowerCase();
          if (
            normalized === "failed" ||
            normalized === "canceled" ||
            normalized === "cancelled" ||
            normalized.startsWith("failed_")
          ) {
            showToast(t("wa_payment_create_failed"));
            return;
          }
        } catch (_error) {
          void _error;
        }
      }
    })();
  }

  async function createPayment() {
    const s = state;
    if (!s.selectedPlan || !s.selectedMethod || s.payBusy) return;
    updateState((s) => ({ ...s, payBusy: true }));
    try {
      const response = await billing.postPayment(
        billing.planPaymentBody(s.selectedPlan, s.selectedMethod, {
          renewHwidDevices: s.renewHwidDevices && Boolean(s.selectedPlan?.hwid_renewal?.available),
          promoCode: checkoutPromoCode(),
        })
      );
      const successContext = paymentSuccessContext(s, response);
      rememberSubscriptionActivationPending(successContext);
      await handlePaymentResponse(response, successContext, () => {
        updateState((s) => ({ ...s, paymentModalOpen: false }));
      });
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_payment_create_failed"));
    } finally {
      updateState((s) => ({ ...s, payBusy: false }));
    }
  }

  async function loadTopupOptions(kind: string) {
    const s = state;
    if (s.topupOptions?.topup_kind === kind) return;
    const requestId = ++topupOptionsRequestId;
    updateState((s) => ({
      ...s,
      tariffActionBusy: true,
      topupOptions: null,
      selectedTopupPlan: null,
    }));
    try {
      const response = await billing.fetchTopupOptions(kind);
      if (requestId !== topupOptionsRequestId || kind !== state.topupKind) return;
      if (!response?.ok) throw response;
      const payload = unwrapBilling(response);
      updateState((s) => ({
        ...s,
        topupOptions: payload,
        selectedTopupPlan: arrayRecords<PlanView>(payload.plans)[0] || null,
      }));
    } catch (error: unknown) {
      if (requestId !== topupOptionsRequestId || kind !== state.topupKind) return;
      showToast(stringField(asRecord(error).message) || t("wa_tariff_options_failed"));
      updateState((s) => ({ ...s, topupModalOpen: false }));
    } finally {
      if (requestId === topupOptionsRequestId) {
        updateState((s) => ({ ...s, tariffActionBusy: false }));
      }
    }
  }

  async function createTopupPayment() {
    const s = state;
    if (!s.selectedTopupPlan || !s.selectedMethod || s.payBusy) return;
    updateState((s) => ({ ...s, payBusy: true }));
    try {
      const response = await billing.postPayment(
        billing.topupPaymentBody(
          s.selectedTopupPlan,
          s.selectedMethod,
          stringField(s.topupOptions?.tariff_key),
          checkoutPromoCode()
        )
      );
      await handlePaymentResponse(response, {}, () => {
        updateState((s) => ({ ...s, topupModalOpen: false }));
      });
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_payment_create_failed"));
    } finally {
      updateState((s) => ({ ...s, payBusy: false }));
    }
  }

  async function loadTariffChangeOptions() {
    const s = state;
    if (s.changeOptions || s.tariffActionBusy) return;
    updateState((s) => ({ ...s, tariffActionBusy: true }));
    try {
      const response = await billing.fetchTariffChangeOptions();
      if (!response?.ok) throw response;
      const payload = unwrapBilling(response);
      const targets = arrayRecords<TariffChangeTarget>(payload.targets);
      const firstTarget = targets[0] || null;
      updateState((s) => ({
        ...s,
        changeOptions: payload,
        selectedChangeTarget: firstTarget,
        selectedChangeAction: firstTarget?.actions?.[0] || null,
      }));
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_tariff_options_failed"));
      updateState((s) => ({ ...s, changeModalOpen: false }));
    } finally {
      updateState((s) => ({ ...s, tariffActionBusy: false }));
    }
  }

  async function applyTariffChange() {
    const s = state;
    if (!s.selectedChangeTarget || !s.selectedChangeAction || s.tariffActionBusy) return;
    if (s.selectedChangeAction.kind === "payment") {
      await createTariffChangePayment();
      return;
    }
    updateState((s) => ({ ...s, tariffActionBusy: true }));
    try {
      const response = await billing.postTariffChange({
        tariff_key: stringField(s.selectedChangeTarget.tariff_key),
        mode: stringField(s.selectedChangeAction.mode),
      });
      if (!response?.ok) throw response;
      unwrapBilling(response);
      showToast(t("wa_tariff_change_applied"));
      updateState((s) => ({
        ...s,
        changeConfirmOpen: false,
        changeModalOpen: false,
        changeOptions: null,
      }));
      await loadData();
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_tariff_change_failed"));
    } finally {
      updateState((s) => ({ ...s, tariffActionBusy: false }));
    }
  }

  async function createTariffChangePayment() {
    const s = state;
    if (!s.selectedChangeTarget || !s.selectedChangeAction || !s.selectedMethod || s.payBusy)
      return;
    updateState((s) => ({ ...s, payBusy: true }));
    try {
      const body = billing.changePaymentBody(
        s.selectedChangeAction,
        s.selectedChangeTarget,
        s.selectedMethod
      );
      const response =
        s.selectedChangeAction.mode === "buy_package" ||
        s.selectedChangeAction.mode === "buy_period"
          ? await billing.postPayment(body)
          : await billing.postTariffChangePayment(body);
      await handlePaymentResponse(response, {}, () => {
        updateState((s) => ({ ...s, changeConfirmOpen: false, changeModalOpen: false }));
      });
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_payment_create_failed"));
    } finally {
      updateState((s) => ({ ...s, payBusy: false }));
    }
  }

  async function loadDeviceTopupOptions() {
    const s = state;
    if (s.deviceTopupOptions || s.tariffActionBusy) return;
    updateState((s) => ({ ...s, tariffActionBusy: true }));
    try {
      const response = await billing.fetchDeviceTopupOptions();
      if (!response?.ok) throw response;
      const payload = unwrapBilling(response);
      updateState((s) => ({
        ...s,
        deviceTopupOptions: payload,
        selectedDeviceTopupPlan: arrayRecords<PlanView>(payload.plans)[0] || null,
      }));
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_device_topup_options_failed"));
      updateState((s) => ({ ...s, deviceTopupModalOpen: false }));
    } finally {
      updateState((s) => ({ ...s, tariffActionBusy: false }));
    }
  }

  async function createDeviceTopupPayment() {
    const s = state;
    if (!s.selectedDeviceTopupPlan || !s.selectedMethod || s.payBusy) return;
    updateState((s) => ({ ...s, payBusy: true }));
    try {
      const response = await billing.postPayment(
        billing.deviceTopupPaymentBody(
          s.selectedDeviceTopupPlan,
          s.selectedMethod,
          stringField(s.deviceTopupOptions?.tariff_key),
          checkoutPromoCode()
        )
      );
      await handlePaymentResponse(response, {}, () => {
        updateState((s) => ({ ...s, deviceTopupModalOpen: false }));
      });
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_payment_create_failed"));
    } finally {
      updateState((s) => ({ ...s, payBusy: false }));
    }
  }

  return state;
}
