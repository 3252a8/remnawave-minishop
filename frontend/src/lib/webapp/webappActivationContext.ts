import { tick } from "svelte";

import { createActivationHandoff } from "./activationHandoff.js";
import { createActivationRuntime } from "./activationRuntime.js";
import { createActivationWatcher } from "./activationWatcher";

const ACTIVATION_HANDOFF_STORAGE_KEY = "rw_webapp_activation_handoff_v1";
const ACTIVATION_HANDOFF_TTL_MS = 48 * 60 * 60 * 1000;

type WatcherDeps = Parameters<typeof createActivationWatcher>[0];

type ActivationContextDeps = {
  billing: WatcherDeps["billing"];
  loadData: WatcherDeps["loadData"];
  getData: () => Record<string, any> | null;
  getSubscription: () => Record<string, unknown>;
  getMode: () => string;
  getScreen: () => string;
  getActivationSuccessDialogOpen: () => boolean;
  getActivationSuccessUseInstallGuides: () => boolean;
  getPaymentModalOpen: () => boolean;
  getTopupModalOpen: () => boolean;
  getDeviceTopupModalOpen: () => boolean;
  getChangeModalOpen: () => boolean;
  getChangeConfirmOpen: () => boolean;
  setActivationSuccessDialogOpen: (open: boolean) => void;
  setActivationSuccessUseInstallGuides: (useInstallGuides: boolean) => void;
  setActiveTab: (tab: string) => void;
  setScreen: (screen: string) => void;
  canUseInstallGuides: () => boolean;
  closePaymentModal: () => void;
  loadInstallGuides: (force?: boolean) => unknown;
  openActivationConnectLink: () => void;
  syncAppSectionPath: (section: string, replace?: boolean) => void;
};

/**
 * Builds the subscription-activation slice of the webapp shell: the handoff
 * store, the activation runtime (success dialog / pending bookkeeping), and the
 * pending-payment watcher. The handoff store and watcher are internal wiring;
 * only the runtime's public actions are returned. Behaviour is identical to the
 * former inline construction in App.svelte — the shell passes its mutable state
 * through getters/setters exactly as before.
 */
export function createWebappActivationContext(deps: ActivationContextDeps) {
  const activationHandoff = createActivationHandoff({
    storageKey: ACTIVATION_HANDOFF_STORAGE_KEY,
    ttlMs: ACTIVATION_HANDOFF_TTL_MS,
  } as any) as any;
  let activationWatcher: ReturnType<typeof createActivationWatcher>;
  const activationRuntime = createActivationRuntime({
    activationHandoff,
    closePaymentModal: deps.closePaymentModal,
    getActivationSuccessDialogOpen: deps.getActivationSuccessDialogOpen,
    getActivationSuccessUseInstallGuides: deps.getActivationSuccessUseInstallGuides,
    getData: deps.getData,
    getSubscription: deps.getSubscription,
    canUseInstallGuides: deps.canUseInstallGuides,
    loadInstallGuides: deps.loadInstallGuides,
    openActivationConnectLink: deps.openActivationConnectLink,
    refreshPendingActivationOnResume: () => activationWatcher.refreshOnResume(),
    setActivationSuccessDialogOpen: deps.setActivationSuccessDialogOpen,
    setActivationSuccessUseInstallGuides: deps.setActivationSuccessUseInstallGuides,
    setActiveTab: deps.setActiveTab,
    setScreen: deps.setScreen,
    startPendingActivationWatch: () => activationWatcher.start(),
    stopPendingActivationWatch: () => activationWatcher.stop(),
    syncAppSectionPath: deps.syncAppSectionPath,
    tick,
  });
  const {
    closeActivationSuccessDialog,
    handleSubscriptionActivated,
    hasPendingActivationHandoff,
    maybeShowActivationSuccessDialog,
    refreshPendingActivationOnResume,
    rememberActivationPending,
    startPendingActivationWatch,
    stopPendingActivationWatch,
  } = activationRuntime;
  activationWatcher = createActivationWatcher({
    activationHandoff,
    billing: deps.billing,
    getData: deps.getData,
    loadData: deps.loadData,
    maybeShowActivationSuccessDialog,
    shouldWatch: () =>
      deps.getMode() === "app" &&
      activationHandoff.hasPending(deps.getData() || {}) &&
      !deps.getActivationSuccessDialogOpen() &&
      deps.getScreen() !== "admin",
    canRefreshOnResume: () =>
      deps.getMode() === "app" &&
      deps.getScreen() !== "admin" &&
      !deps.getActivationSuccessDialogOpen() &&
      !deps.getPaymentModalOpen() &&
      !deps.getTopupModalOpen() &&
      !deps.getDeviceTopupModalOpen() &&
      !deps.getChangeModalOpen() &&
      !deps.getChangeConfirmOpen() &&
      activationHandoff.hasPending(deps.getData() || {}),
  });

  return {
    closeActivationSuccessDialog,
    handleSubscriptionActivated,
    hasPendingActivationHandoff,
    maybeShowActivationSuccessDialog,
    refreshPendingActivationOnResume,
    rememberActivationPending,
    startPendingActivationWatch,
    stopPendingActivationWatch,
  };
}
