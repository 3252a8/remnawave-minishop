type ActivationPayload = Record<string, unknown>;
type ActivationContext = {
  force?: boolean;
  source?: string;
  payload?: ActivationPayload;
  paymentId?: string;
  initialSubscriptionPayment?: boolean;
};

type ActivationState = {
  pending?: ActivationPayload | null;
  acknowledged?: ActivationPayload | null;
};

type ActivationHandoff = {
  acknowledge(
    subscriptionKey: string,
    context?: ActivationPayload,
    payload?: ActivationPayload,
    state?: ActivationState
  ): void;
  hasPending(payload?: ActivationPayload): boolean;
  isAcknowledged(subscriptionKey: string, state?: ActivationState): boolean;
  isPendingFresh(pending?: ActivationPayload | null): boolean;
  pendingMatchesUser(pending?: ActivationPayload | null, payload?: ActivationPayload): boolean;
  read(): ActivationState;
  rememberPending(context?: ActivationPayload, payload?: ActivationPayload): void;
  subscriptionKey(payload?: ActivationPayload): string;
  write(state: ActivationState): void;
};

type ActivationRuntimeDeps = {
  activationHandoff: ActivationHandoff;
  closePaymentModal: () => void;
  getActivationSuccessDialogOpen: () => boolean;
  getActivationSuccessUseInstallGuides: () => boolean;
  getData: () => ActivationPayload | null;
  getSubscription: () => ActivationPayload | null;
  canUseInstallGuides: () => boolean;
  loadInstallGuides: (force?: boolean) => unknown;
  openActivationConnectLink: () => unknown;
  refreshPendingActivationOnResume: () => Promise<void>;
  setActivationSuccessDialogOpen: (open: boolean) => void;
  setActivationSuccessUseInstallGuides: (useInstallGuides: boolean) => void;
  setActiveTab: (tab: string) => void;
  setScreen: (screen: string) => void;
  startPendingActivationWatch: () => void;
  stopPendingActivationWatch: () => void;
  syncAppSectionPath: (section: string, replace?: boolean) => void;
  tick: () => Promise<void>;
};

export function createActivationRuntime({
  activationHandoff,
  closePaymentModal,
  getActivationSuccessDialogOpen,
  getActivationSuccessUseInstallGuides,
  getData,
  getSubscription,
  canUseInstallGuides,
  loadInstallGuides,
  openActivationConnectLink,
  refreshPendingActivationOnResume,
  setActivationSuccessDialogOpen,
  setActivationSuccessUseInstallGuides,
  setActiveTab,
  setScreen,
  startPendingActivationWatch,
  stopPendingActivationWatch,
  syncAppSectionPath,
  tick,
}: ActivationRuntimeDeps) {
  function hasPendingActivationHandoff(payload: ActivationPayload | null = getData()) {
    return activationHandoff.hasPending(payload || {});
  }

  function rememberActivationPending(context: ActivationContext = {}) {
    activationHandoff.rememberPending(context, getData() || {});
  }

  async function maybeShowActivationSuccessDialog(context: ActivationContext = {}) {
    if (getActivationSuccessDialogOpen()) return false;
    await tick();
    const payload: ActivationPayload = context.payload ?? getData() ?? {};
    const subscriptionKey = activationHandoff.subscriptionKey(payload);
    if (!subscriptionKey) return false;
    const state = activationHandoff.read();
    const pending = state.pending;
    if (!context.force && activationHandoff.isAcknowledged(subscriptionKey, state)) {
      if (pending && activationHandoff.pendingMatchesUser(pending, payload)) {
        activationHandoff.write({ ...state, pending: null });
      }
      return false;
    }
    if (
      !context.force &&
      (!pending ||
        !activationHandoff.isPendingFresh(pending) ||
        !activationHandoff.pendingMatchesUser(pending, payload))
    ) {
      return false;
    }
    activationHandoff.acknowledge(subscriptionKey, context, payload, state);
    stopPendingActivationWatch();
    const useInstallGuides = canUseInstallGuides();
    setActivationSuccessUseInstallGuides(useInstallGuides);
    closePaymentModal();
    setActiveTab("home");
    if (!useInstallGuides) {
      setScreen("home");
      syncAppSectionPath("home", true);
    }
    setActivationSuccessDialogOpen(true);
    return true;
  }

  function navigateToActivationTarget({ replace = true }: { replace?: boolean } = {}) {
    const useInstallGuides = canUseInstallGuides();
    setActivationSuccessUseInstallGuides(useInstallGuides);
    closePaymentModal();
    setActiveTab("home");
    if (useInstallGuides) {
      setScreen("install");
      syncAppSectionPath("install", replace);
      loadInstallGuides(true);
      return;
    }
    setScreen("home");
    syncAppSectionPath("home", replace);
  }

  async function handleSubscriptionActivated(context: ActivationContext = {}) {
    await tick();
    if (!getSubscription()?.active) return;
    await maybeShowActivationSuccessDialog({ ...context, force: true, source: "payment" });
  }

  function closeActivationSuccessDialog() {
    const shouldOpenConnect = !getActivationSuccessUseInstallGuides();
    setActivationSuccessDialogOpen(false);
    if (getActivationSuccessUseInstallGuides()) {
      navigateToActivationTarget({ replace: true });
      return;
    }
    if (shouldOpenConnect) openActivationConnectLink();
  }

  return {
    closeActivationSuccessDialog,
    handleSubscriptionActivated,
    hasPendingActivationHandoff,
    maybeShowActivationSuccessDialog,
    navigateToActivationTarget,
    refreshPendingActivationOnResume,
    rememberActivationPending,
    startPendingActivationWatch,
    stopPendingActivationWatch,
  };
}
