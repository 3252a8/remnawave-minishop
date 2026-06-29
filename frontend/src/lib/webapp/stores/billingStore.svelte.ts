import type { LoadDataOptions } from "../dataClient";
import type { BillingActions } from "../billingActions";
import { unwrap } from "../publicApi";

type TelegramWebApp = Record<string, unknown> & {
  openInvoice?: (url: string, callback: (status: string) => void) => void;
};
type BillingRecord = Record<string, unknown> & {
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
  selectedPlan: BillingRecord | null;
  selectedMethod: string;
  renewHwidDevices: boolean;
  paymentStartedWithActiveSubscription: boolean;
  topupModalOpen: boolean;
  topupKind: string;
  deviceTopupModalOpen: boolean;
  changeModalOpen: boolean;
  topupOptions: BillingRecord | null;
  deviceTopupOptions: BillingRecord | null;
  changeOptions: BillingRecord | null;
  selectedTopupPlan: BillingRecord | null;
  selectedDeviceTopupPlan: BillingRecord | null;
  selectedChangeTarget: BillingRecord | null;
  selectedChangeAction: BillingRecord | null;
  changeConfirmOpen: boolean;
  tariffActionBusy: boolean;
  payBusy: boolean;
  checkoutPromoInput: string;
  checkoutPromoAppliedCode: string;
  checkoutPromoStatus: string;
  checkoutPromoIsError: boolean;
  checkoutPromoPriceText: string;
};
export type BillingStore = BillingState & {
  update(updater: (snapshot: BillingState) => BillingState): void;
  openPaymentModal(
    tariffMode: boolean,
    singleTariffMode: boolean,
    tariffCatalog: BillingRecord[],
    subscription: BillingRecord,
    plans: BillingRecord[],
    defaultMethod?: string,
    options?: BillingRecord
  ): void;
  closePaymentModal(): void;
  selectTariff(tariff: BillingRecord, plans?: BillingRecord[]): void;
  continueWithSelectedTariff(selectedTariffPlans?: BillingRecord[]): void;
  backToTariffList(subscription: BillingRecord, tariffCatalog?: BillingRecord[]): void;
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
    refresh?: () => TelegramWebApp | null;
    ensureForAction?: () => Promise<TelegramWebApp | null>;
  } | null;
}) {
  function asRecord(value: unknown): BillingRecord {
    return value && typeof value === "object" ? (value as BillingRecord) : {};
  }

  function arrayRecords(value: unknown): BillingRecord[] {
    return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
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

  function checkoutPlanKey(plan: BillingRecord | null): string {
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
    const stars = payload.effective_stars;
    if (typeof stars === "number" && stars > 0) return `${stars} stars`;
    const amount = Number(payload.effective_amount || 0);
    const currency = stringField(payload.currency);
    return amount > 0 ? `${amount.toFixed(2)}${currency ? ` ${currency}` : ""}` : "";
  }

  async function applyCheckoutPromo(): Promise<void> {
    const body = checkoutQuoteBody();
    if (!body) {
      updateState((s) => ({
        ...s,
        checkoutPromoIsError: true,
        checkoutPromoStatus: t("wa_promo_select_plan_first", {}, "Choose a plan first"),
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
        }));
        return;
      }
      updateState((s) => ({
        ...s,
        checkoutPromoInput: "",
        checkoutPromoAppliedCode: stringField(payload.code || body.promo_code),
        checkoutPromoIsError: false,
        checkoutPromoStatus: stringField(payload.effect_summary),
        checkoutPromoPriceText: promoPriceText(payload),
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
    }));
  }

  function sleep(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function isSubscriptionSale(plan: BillingRecord | null) {
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

  function openPaymentModal(
    tariffMode: boolean,
    singleTariffMode: boolean,
    tariffCatalog: BillingRecord[],
    subscription: BillingRecord,
    plans: BillingRecord[],
    defaultMethod = "",
    options: BillingRecord = {}
  ) {
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

  function selectTariff(tariff: BillingRecord, plans: BillingRecord[] = []) {
    const key = String(tariff?.key || "").trim();
    if (!key) return;
    updateState((s) => ({
      ...s,
      selectedTariffKey: key,
      selectedPlan: plans.find((plan) => plan?.tariff_key === key) || null,
      renewHwidDevices: true,
    }));
  }

  function continueWithSelectedTariff(selectedTariffPlans: BillingRecord[] = []) {
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

  function backToTariffList(subscription: BillingRecord, tariffCatalog: BillingRecord[] = []) {
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

  function resolveTelegramWebApp() {
    if (typeof getTg === "function") {
      const currentTg = getTg();
      if (currentTg) return currentTg;
    }
    if (tg) return tg;
    if (telegramSdk?.refresh) return telegramSdk.refresh();
    return null;
  }

  async function resolveInvoiceTelegramWebApp(): Promise<TelegramWebApp | null> {
    const currentTg = resolveTelegramWebApp();
    if (currentTg?.openInvoice) return currentTg;
    if (telegramSdk?.ensureForAction) {
      const loadedTg = await telegramSdk.ensureForAction();
      if (loadedTg?.openInvoice) return loadedTg;
    }
    return resolveTelegramWebApp();
  }

  async function openTelegramInvoice(url: string, successContext: BillingRecord = {}) {
    if (!url) return false;
    const invoiceTg = await resolveInvoiceTelegramWebApp();
    if (invoiceTg?.openInvoice) {
      invoiceTg.openInvoice(url, async (status) => {
        if (status === "paid") {
          await handlePaymentSuccess(successContext);
        } else if (status === "failed") {
          showToast(t("wa_payment_create_failed"));
        }
      });
      return true;
    }
    showToast(
      t("wa_payment_stars_telegram_required", {}, "Open this payment in Telegram to pay with Stars")
    );
    return false;
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
        selectedTopupPlan: arrayRecords(payload.plans)[0] || null,
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
      const targets = arrayRecords(payload.targets);
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
        selectedDeviceTopupPlan: arrayRecords(payload.plans)[0] || null,
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
