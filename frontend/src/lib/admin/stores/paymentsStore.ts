import { writable, type Writable } from "svelte/store";
import { withRoutePrefix } from "../../webapp/routes.js";
import { unwrap, type ApiResponse, type GetResponse } from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { adminErrorMessage } from "../errors.js";

const PAYMENTS_PAGE_SIZE = 25;

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends string>(
  path: Path,
  options?: RequestInit
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type PaymentsListResponse = GetResponse<"/api/admin/payments">;
type PaymentDetailResponse = GetResponse<"/api/admin/payments/{payment_id}">;
export type PaymentOut = components["schemas"]["PaymentOut"];
export type PaymentDetailOut = components["schemas"]["PaymentDetailOut"];
export type AdminPayment = Partial<PaymentOut> &
  Partial<PaymentDetailOut> & {
    payment_id: number;
  };
type PaymentsState = {
  payments: PaymentOut[];
  paymentsTotal: number;
  paymentsPage: number;
  paymentsLoading: boolean;
  openedPaymentId: number | null;
  openedPayment: AdminPayment | null;
  paymentDetailLoading: boolean;
};
type PaymentOpenOptions = { skipPush?: boolean };
type PaymentsStoreOptions = {
  api: AdminApi;
  onToast?: ToastFn;
  at?: TranslateFn;
  routePrefix?: string;
};
export type PaymentsStore = Writable<PaymentsState> & {
  setActive: (section: string) => void;
  loadPayments: () => Promise<void>;
  setPage: (page: number) => void;
  openPayment: (
    paymentOrId: AdminPayment | PaymentOut | number | string,
    opts?: PaymentOpenOptions
  ) => Promise<void>;
  closePayment: (opts?: PaymentOpenOptions) => void;
  copyToClipboard: (text: unknown, successMessage?: string) => void;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

function hasPaymentId(value: unknown): value is AdminPayment | PaymentOut {
  return Boolean(value && typeof value === "object" && "payment_id" in value);
}

export function createPaymentsStore({
  api,
  onToast = () => {},
  at = (key, _params, fallback) => fallback || key,
  routePrefix = "",
}: PaymentsStoreOptions): PaymentsStore {
  const state: Writable<PaymentsState> = writable({
    payments: [],
    paymentsTotal: 0,
    paymentsPage: 0,
    paymentsLoading: false,
    openedPaymentId: null,
    openedPayment: null,
    paymentDetailLoading: false,
  });

  let active = "stats";

  function setActive(section: string): void {
    active = section;
  }

  function pushPaymentPath(paymentId: number | null): void {
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    if (active !== "payments") return;
    const target = withRoutePrefix(
      paymentId ? `/admin/payments/${paymentId}` : "/admin/payments",
      routePrefix
    );
    if (window.location.pathname === target) return;
    window.history.pushState(null, "", `${target}${window.location.search}${window.location.hash}`);
  }

  async function loadPayments(): Promise<void> {
    state.update((s) => ({ ...s, paymentsLoading: true }));
    let currentPage = 0;
    state.update((s) => {
      currentPage = s.paymentsPage;
      return s;
    });

    try {
      const data = (await api(
        `/admin/payments?page=${currentPage}&page_size=${PAYMENTS_PAGE_SIZE}`
      )) as PaymentsListResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const result = unwrap(data);
        state.update((s) => ({
          ...s,
          payments: result.payments || [],
          paymentsTotal: result.total || 0,
        }));
      }
    } finally {
      state.update((s) => ({ ...s, paymentsLoading: false }));
    }
  }

  function setPage(page: number): void {
    state.update((s) => ({ ...s, paymentsPage: page }));
    void loadPayments();
  }

  async function openPayment(
    paymentOrId: AdminPayment | PaymentOut | number | string,
    opts: PaymentOpenOptions = {}
  ): Promise<void> {
    const paymentId = hasPaymentId(paymentOrId)
      ? Number(paymentOrId.payment_id)
      : Number(paymentOrId);
    if (!Number.isFinite(paymentId) || paymentId <= 0) return;

    state.update((s) => ({
      ...s,
      openedPaymentId: paymentId,
      openedPayment: hasPaymentId(paymentOrId)
        ? { ...paymentOrId }
        : s.openedPayment?.payment_id === paymentId
          ? s.openedPayment
          : null,
      paymentDetailLoading: true,
    }));
    if (!opts.skipPush) pushPaymentPath(paymentId);

    try {
      const path = `/admin/payments/${paymentId}` as "/api/admin/payments/{payment_id}";
      const res = (await api(path)) as PaymentDetailResponse | AdminErrorResponse;
      if (isOkResponse(res)) {
        const result = unwrap(res);
        state.update((s) => ({
          ...s,
          openedPayment: result.payment || s.openedPayment,
        }));
      } else {
        onToast(
          adminErrorMessage(res, at, at("payment_load_failed", {}, "Не удалось загрузить платеж"))
        );
        state.update((s) => ({ ...s, openedPaymentId: null, openedPayment: null }));
        if (!opts.skipPush) pushPaymentPath(null);
      }
    } finally {
      state.update((s) => ({ ...s, paymentDetailLoading: false }));
    }
  }

  function closePayment(opts: PaymentOpenOptions = {}): void {
    let wasOpen = false;
    state.update((s) => {
      wasOpen = Boolean(s.openedPaymentId);
      return {
        ...s,
        openedPaymentId: null,
        openedPayment: null,
        paymentDetailLoading: false,
      };
    });
    if (wasOpen && !opts.skipPush) pushPaymentPath(null);
  }

  function copyToClipboard(text: unknown, successMessage = at("copied", {}, "Скопировано")): void {
    if (!text) return;
    if (typeof navigator !== "undefined" && navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(String(text)).then(
        () => onToast(successMessage),
        () => onToast(String(text))
      );
    } else {
      onToast(String(text));
    }
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    setActive,
    loadPayments,
    setPage,
    openPayment,
    closePayment,
    copyToClipboard,
  };
}
