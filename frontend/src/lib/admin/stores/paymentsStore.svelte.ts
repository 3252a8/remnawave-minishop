import { withRoutePrefix } from "../../webapp/routes.js";
import {
  buildAdminPaymentPath,
  buildAdminPaymentsPath,
  unwrap,
  type ApiClient,
  type GetResponse,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { adminErrorMessage } from "../errors.js";
import { createAdminPerfSpan } from "../adminPerfMarks";
import { defineRawStateProperty } from "./rawStateProperty";
import { fetchAdminQuery, type AdminQueryClient, type AdminQueryKey } from "./adminQueryCache";

const PAYMENTS_PAGE_SIZE = 25;
const PAYMENTS_QUERY_KEY = ["admin", "payments"] as const;
const PAYMENT_DETAIL_QUERY_KEY = ["admin", "payments", "detail"] as const;

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = ApiClient["api"];
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
  queryClient?: AdminQueryClient | null;
};
export type PaymentsStore = PaymentsState & {
  setActive: (section: string) => void;
  loadPayments: (options?: { refresh?: boolean }) => Promise<void>;
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

class AdminPaymentsError extends Error {
  payload: unknown;

  constructor(message: string, payload: unknown) {
    super(message);
    this.payload = payload;
  }
}

export function createPaymentsStore({
  api,
  onToast = () => {},
  at = (key, _params, fallback) => fallback || key,
  routePrefix = "",
  queryClient = null,
}: PaymentsStoreOptions): PaymentsStore {
  let payments = $state.raw<PaymentOut[]>([]);
  const state = $state<Omit<PaymentsState, "payments">>({
    paymentsTotal: 0,
    paymentsPage: 0,
    paymentsLoading: false,
    openedPaymentId: null,
    openedPayment: null,
    paymentDetailLoading: false,
  });
  const store = Object.create(state) as PaymentsStore;
  defineRawStateProperty(store, "payments", {
    get: () => payments,
    set: (value) => {
      payments = value;
    },
  });

  let active = "stats";

  function setActive(section: string): void {
    active = section;
  }

  function pushPaymentPath(paymentId: number | null): void {
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    if (active !== "payments") return;
    const target = withRoutePrefix(
      paymentId ? buildAdminPaymentPath(paymentId) : buildAdminPaymentsPath(),
      routePrefix
    );
    if (window.location.pathname === target) return;
    window.history.pushState(null, "", `${target}${window.location.search}${window.location.hash}`);
  }

  function paymentsListQueryKey(page: number): AdminQueryKey {
    return [
      PAYMENTS_QUERY_KEY[0],
      PAYMENTS_QUERY_KEY[1],
      {
        page,
      },
    ];
  }

  async function requestPayments(page: number): Promise<PaymentsListResponse> {
    const data = await api(
      buildAdminPaymentsPath(
        new URLSearchParams({
          page: String(page),
          page_size: String(PAYMENTS_PAGE_SIZE),
        })
      )
    );
    if (!isOkResponse(data)) {
      throw new AdminPaymentsError(adminErrorMessage(data, at, "load_failed"), data);
    }
    return data;
  }

  function paymentDetailQueryKey(paymentId: number): AdminQueryKey {
    return [
      PAYMENT_DETAIL_QUERY_KEY[0],
      PAYMENT_DETAIL_QUERY_KEY[1],
      PAYMENT_DETAIL_QUERY_KEY[2],
      paymentId,
    ];
  }

  async function requestPaymentDetail(paymentId: number): Promise<PaymentDetailResponse> {
    const res = await api(buildAdminPaymentPath(paymentId));
    if (!isOkResponse(res)) {
      throw new AdminPaymentsError(
        adminErrorMessage(res, at, at("payment_load_failed", {}, "Failed to load payment")),
        res
      );
    }
    return res;
  }

  async function loadPayments({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
    state.paymentsLoading = true;
    const currentPage = state.paymentsPage;
    const perf = createAdminPerfSpan("payments");

    try {
      const data = await fetchAdminQuery({
        queryClient,
        queryKey: paymentsListQueryKey(currentPage),
        queryFn: () => requestPayments(currentPage),
        refresh,
      });
      perf.apiResponse();
      const result = unwrap(data);
      payments = result.payments || [];
      state.paymentsTotal = result.total || 0;
      perf.stateAssign();
      void perf.renderSettled();
    } catch (error) {
      if (error instanceof AdminPaymentsError) {
        onToast(adminErrorMessage(error.payload, at, "load_failed"));
      } else {
        onToast(error instanceof Error ? error.message : String(error || "load_failed"));
      }
    } finally {
      state.paymentsLoading = false;
    }
  }

  function setPage(page: number): void {
    state.paymentsPage = page;
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

    state.openedPaymentId = paymentId;
    state.openedPayment = hasPaymentId(paymentOrId)
      ? { ...paymentOrId }
      : state.openedPayment?.payment_id === paymentId
        ? state.openedPayment
        : null;
    state.paymentDetailLoading = true;
    if (!opts.skipPush) pushPaymentPath(paymentId);

    try {
      const res = await fetchAdminQuery({
        queryClient,
        queryKey: paymentDetailQueryKey(paymentId),
        queryFn: () => requestPaymentDetail(paymentId),
      });
      if (isOkResponse(res)) {
        const result = unwrap(res);
        state.openedPayment = result.payment || state.openedPayment;
      } else {
        onToast(
          adminErrorMessage(res, at, at("payment_load_failed", {}, "Failed to load payment"))
        );
        state.openedPaymentId = null;
        state.openedPayment = null;
        if (!opts.skipPush) pushPaymentPath(null);
      }
    } catch (error) {
      if (error instanceof AdminPaymentsError) {
        onToast(adminErrorMessage(error.payload, at, "load_failed"));
      } else {
        onToast(error instanceof Error ? error.message : String(error || "load_failed"));
      }
      state.openedPaymentId = null;
      state.openedPayment = null;
      if (!opts.skipPush) pushPaymentPath(null);
    } finally {
      state.paymentDetailLoading = false;
    }
  }

  function closePayment(opts: PaymentOpenOptions = {}): void {
    const wasOpen = Boolean(state.openedPaymentId);
    state.openedPaymentId = null;
    state.openedPayment = null;
    state.paymentDetailLoading = false;
    if (wasOpen && !opts.skipPush) pushPaymentPath(null);
  }

  function copyToClipboard(text: unknown, successMessage = at("copied", {}, "Copied")): void {
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

  return Object.assign(store, {
    setActive,
    loadPayments,
    setPage,
    openPayment,
    closePayment,
    copyToClipboard,
  });
}
