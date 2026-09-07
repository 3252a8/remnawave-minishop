import type { PendingPaymentView, WebappRecord } from "./types.js";
import { isQaPaymentUrl } from "./qaPayment.js";

export type BillingPaymentResponse = WebappRecord & {
  action?: string;
  ok: boolean;
  payment_id?: string | number;
  payment_url?: string | null;
};

type PaymentSuccessContext = WebappRecord & {
  initialSubscriptionPayment?: boolean;
  paymentId?: string | number;
  renewalSubscriptionPayment?: boolean;
};

export function createPaymentResponseHandler({
  afterOpened,
  notifyOpened,
  openExternalLink,
  openQaPaymentLink,
  openTelegramInvoice,
  startPaymentStatusPolling,
}: {
  afterOpened?: () => Promise<unknown> | unknown;
  notifyOpened: (resumed: boolean) => void;
  openExternalLink: (url: string) => void;
  openQaPaymentLink: (url: string) => void;
  openTelegramInvoice: (url: string, context: PaymentSuccessContext) => Promise<boolean>;
  startPaymentStatusPolling: (
    paymentId: string | number | undefined,
    context: PaymentSuccessContext
  ) => void;
}) {
  function refreshSnapshot(): void {
    if (!afterOpened) return;
    void Promise.resolve(afterOpened()).catch((_error) => {
      void _error;
    });
  }

  return async function handlePaymentResponse(
    response: BillingPaymentResponse,
    successContext: PaymentSuccessContext = {},
    closeModal: () => void = () => {},
    resumed = false
  ): Promise<boolean> {
    if (!response.ok) throw response;
    notifyOpened(resumed);
    if (response.action === "open_invoice") {
      if (!response.payment_url) throw response;
      const opened = await openTelegramInvoice(response.payment_url, successContext);
      if (!opened) return false;
    } else if (response.action === "invoice_sent" || response.action === "completed") {
      startPaymentStatusPolling(response.payment_id, successContext);
      closeModal();
      refreshSnapshot();
      return true;
    } else {
      if (!response.payment_url) throw response;
      if (isQaPaymentUrl(response.payment_url)) openQaPaymentLink(response.payment_url);
      else openExternalLink(response.payment_url);
    }
    startPaymentStatusPolling(response.payment_id, successContext);
    closeModal();
    refreshSnapshot();
    return true;
  };
}

export function createPendingPaymentResume({
  closeModal,
  getPaymentStartedWithActiveSubscription,
  handlePaymentResponse,
  isBusy,
  onError,
  rememberPending,
  setBusy,
}: {
  closeModal: () => void;
  getPaymentStartedWithActiveSubscription: () => boolean;
  handlePaymentResponse: ReturnType<typeof createPaymentResponseHandler>;
  isBusy: () => boolean;
  onError: (error: unknown) => void;
  rememberPending: (context: PaymentSuccessContext) => void;
  setBusy: (busy: boolean) => void;
}) {
  return async function resumePendingPayment(payment: PendingPaymentView): Promise<void> {
    const paymentUrl = String(payment.payment_url || "").trim();
    const paymentId = payment.payment_id;
    if (!paymentUrl || !paymentId || isBusy()) return;

    setBusy(true);
    const activeSubscription = getPaymentStartedWithActiveSubscription();
    const subscriptionPayment =
      (String(payment.sale_mode || "").split("@", 1)[0] || "subscription") === "subscription";
    const successContext = {
      paymentId,
      initialSubscriptionPayment:
        !activeSubscription &&
        subscriptionPayment &&
        !String(payment.sale_mode || "")
          .split("|")
          .includes("gift"),
      renewalSubscriptionPayment: activeSubscription && subscriptionPayment,
    };
    try {
      rememberPending(successContext);
      await handlePaymentResponse(
        {
          ok: true,
          action: String(payment.provider || "")
            .toLowerCase()
            .includes("stars")
            ? "open_invoice"
            : "open_url",
          payment_id: paymentId,
          payment_url: paymentUrl,
        },
        successContext,
        closeModal,
        true
      );
    } catch (error: unknown) {
      onError(error);
    } finally {
      setBusy(false);
    }
  };
}

export function createPendingPaymentCancellation({
  afterCanceled,
  cancelPayment,
  isBusy,
  notifyCanceled,
  onError,
  setBusy,
}: {
  afterCanceled: (payment: PendingPaymentView) => Promise<void>;
  cancelPayment: (paymentId: string | number) => Promise<BillingPaymentResponse>;
  isBusy: () => boolean;
  notifyCanceled: () => void;
  onError: (error: unknown) => void;
  setBusy: (busy: boolean) => void;
}) {
  return async function cancelPendingPayment(payment: PendingPaymentView): Promise<void> {
    const paymentId = payment.payment_id;
    const promoCode = String(payment.promo_code || "").trim();
    if (!paymentId || !promoCode || isBusy()) return;

    setBusy(true);
    try {
      const response = await cancelPayment(paymentId);
      if (!response.ok) throw response;
      await afterCanceled(payment);
      notifyCanceled();
    } catch (error: unknown) {
      onError(error);
    } finally {
      setBusy(false);
    }
  };
}
