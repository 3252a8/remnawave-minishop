import type { LoadDataOptions } from "./dataClient";
import { activationPaymentFailed } from "./activationHandoff.js";

const ACTIVATION_PENDING_WATCH_INTERVAL_MS = 2000;
const ACTIVATION_PENDING_WATCH_MAX_ATTEMPTS = 45;
const ACTIVATION_RESUME_CHECK_COOLDOWN_MS = 1500;

type PendingActivation = {
  paymentId?: string | number | null;
};
type ActivationState = {
  pending?: PendingActivation | null;
};
type ActivationHandoff = {
  clearPending(): void;
  hasPending(payload?: unknown): boolean;
  read(): ActivationState;
};
type PaymentStatus = Record<string, unknown> & {
  paid?: boolean;
  status?: string;
};
type BillingWithStatus = {
  fetchPaymentStatus?: (paymentId: string | number) => Promise<PaymentStatus | null | undefined>;
};
type ActivationWatcherDeps = {
  activationHandoff: ActivationHandoff;
  billing: BillingWithStatus;
  canRefreshOnResume: () => boolean;
  getData: () => unknown;
  loadData: (options?: LoadDataOptions & Record<string, unknown>) => Promise<unknown>;
  maybeShowActivationSuccessDialog: (context?: Record<string, unknown>) => Promise<boolean>;
  shouldWatch: () => boolean;
  intervalMs?: number;
  maxAttempts?: number;
  resumeCooldownMs?: number;
};

export function createActivationWatcher({
  activationHandoff,
  billing,
  canRefreshOnResume,
  getData,
  loadData,
  maybeShowActivationSuccessDialog,
  shouldWatch,
  intervalMs = ACTIVATION_PENDING_WATCH_INTERVAL_MS,
  maxAttempts = ACTIVATION_PENDING_WATCH_MAX_ATTEMPTS,
  resumeCooldownMs = ACTIVATION_RESUME_CHECK_COOLDOWN_MS,
}: ActivationWatcherDeps) {
  let watchTimer: number | null = null;
  let watchAttempts = 0;
  let watchBusy = false;
  let resumeRefreshBusy = false;
  let resumeLastCheckAt = 0;

  function hasPending() {
    return activationHandoff.hasPending(getData());
  }

  function stop() {
    if (watchTimer) {
      window.clearTimeout(watchTimer);
      watchTimer = null;
    }
    watchAttempts = 0;
    watchBusy = false;
  }

  function schedule() {
    if (watchTimer || !hasPending()) return;
    watchTimer = window.setTimeout(() => {
      watchTimer = null;
      void checkNow();
    }, intervalMs);
  }

  function start() {
    if (!shouldWatch() || !hasPending()) {
      stop();
      return;
    }
    if (watchTimer || watchBusy) return;
    schedule();
  }

  async function checkNow() {
    if (watchBusy) return;
    if (!shouldWatch() || !hasPending()) {
      stop();
      return;
    }
    if (watchAttempts >= maxAttempts) {
      stop();
      return;
    }

    const state = activationHandoff.read();
    const pending = state.pending;
    watchAttempts += 1;
    watchBusy = true;
    try {
      let shouldRefreshProfile = !pending?.paymentId;
      if (pending?.paymentId && billing.fetchPaymentStatus) {
        const paymentStatus = await billing.fetchPaymentStatus(pending.paymentId);
        if (paymentStatus?.paid || paymentStatus?.status === "succeeded") {
          shouldRefreshProfile = true;
        } else if (activationPaymentFailed(paymentStatus)) {
          activationHandoff.clearPending();
          stop();
          return;
        }
      }
      if (shouldRefreshProfile) {
        await loadData({ fresh: true });
        const shown = await maybeShowActivationSuccessDialog({
          source: "watch",
          paymentId: pending?.paymentId,
        });
        if (shown || !hasPending()) {
          stop();
          return;
        }
      }
    } catch (_error) {
      void _error;
    } finally {
      watchBusy = false;
    }
    schedule();
  }

  async function refreshOnResume() {
    if (!canRefreshOnResume() || !hasPending()) return;
    const now = Date.now();
    if (resumeRefreshBusy || now - resumeLastCheckAt < resumeCooldownMs) {
      return;
    }
    resumeLastCheckAt = now;
    resumeRefreshBusy = true;
    try {
      await loadData({ fresh: true });
      const shown = await maybeShowActivationSuccessDialog({ source: "resume" });
      if (!shown) start();
    } catch (_error) {
      void _error;
    } finally {
      resumeRefreshBusy = false;
    }
  }

  return {
    checkNow,
    refreshOnResume,
    start,
    stop,
  };
}
