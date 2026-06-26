import { withRoutePrefix } from "../../webapp/routes.js";
import {
  buildAdminPaymentPath,
  buildAdminPaymentsPath,
  unwrap,
  type ApiResponse,
  type GetResponse,
} from "../../webapp/publicApi";
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
export type PaymentsStore = PaymentsState & {
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
  const state = $state<PaymentsState>({
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
      paymentId ? buildAdminPaymentPath(paymentId) : buildAdminPaymentsPath(),
      routePrefix
    );
    if (window.location.pathname === target) return;
    window.history.pushState(null, "", `${target}${window.location.search}${window.location.hash}`);
  }

  async function loadPayments(): Promise<void> {
    state.paymentsLoading = true;
    const currentPage = state.paymentsPage;

    try {
      const data = (await api(
        buildAdminPaymentsPath(
          new URLSearchParams({
            page: String(currentPage),
            page_size: String(PAYMENTS_PAGE_SIZE),
          })
        )
      )) as PaymentsListResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const result = unwrap(data);
        state.payments = result.payments || [];
        state.paymentsTotal = result.total || 0;
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
      const path = buildAdminPaymentPath(paymentId);
      const res = (await api(path)) as PaymentDetailResponse | AdminErrorResponse;
      if (isOkResponse(res)) {
        const result = unwrap(res);
        state.openedPayment = result.payment || state.openedPayment;
      } else {
        onToast(
          adminErrorMessage(res, at, at("payment_load_failed", {}, "Не удалось загрузить платёж"))
        );
        state.openedPaymentId = null;
        state.openedPayment = null;
        if (!opts.skipPush) pushPaymentPath(null);
      }
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

  return Object.assign(state, {
    setActive,
    loadPayments,
    setPage,
    openPayment,
    closePayment,
    copyToClipboard,
  });
}
