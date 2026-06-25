import { tick } from "svelte";

import { createActivationHandoff } from "./activationHandoff.js";
import { createActivationRuntime } from "./activationRuntime.js";
import { createActivationWatcher } from "./activationWatcher";
import { shellState } from "./shellState.svelte";

const ACTIVATION_HANDOFF_STORAGE_KEY = "rw_webapp_activation_handoff_v1";
const ACTIVATION_HANDOFF_TTL_MS = 48 * 60 * 60 * 1000;

type WatcherDeps = Parameters<typeof createActivationWatcher>[0];

type ActivationContextDeps = {
  billing: WatcherDeps["billing"];
  loadData: WatcherDeps["loadData"];
  getPaymentModalOpen: () => boolean;
  getTopupModalOpen: () => boolean;
  getDeviceTopupModalOpen: () => boolean;
  getChangeModalOpen: () => boolean;
  getChangeConfirmOpen: () => boolean;
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
 * only the runtime's public actions are returned. Mutable shell fields are read
 * and updated through the shared shell state store.
 */
export function createWebappActivationContext(deps: ActivationContextDeps) {
  function getShellData(): Record<string, any> | null {
    return shellState.data && typeof shellState.data === "object"
      ? (shellState.data as Record<string, any>)
      : null;
  }

  function getShellSubscription(): Record<string, unknown> | null {
    const subscription = getShellData()?.subscription;
    return subscription && typeof subscription === "object"
      ? (subscription as Record<string, unknown>)
      : null;
  }

  const activationHandoff = createActivationHandoff({
    storageKey: ACTIVATION_HANDOFF_STORAGE_KEY,
    ttlMs: ACTIVATION_HANDOFF_TTL_MS,
  } as any) as any;
  let activationWatcher: ReturnType<typeof createActivationWatcher>;
  const activationRuntime = createActivationRuntime({
    activationHandoff,
    closePaymentModal: deps.closePaymentModal,
    getActivationSuccessDialogOpen: () => shellState.activationSuccessDialogOpen,
    getActivationSuccessUseInstallGuides: () => shellState.activationSuccessUseInstallGuides,
    getData: getShellData,
    getSubscription: getShellSubscription,
    canUseInstallGuides: deps.canUseInstallGuides,
    loadInstallGuides: deps.loadInstallGuides,
    openActivationConnectLink: deps.openActivationConnectLink,
    refreshPendingActivationOnResume: () => activationWatcher.refreshOnResume(),
    setActivationSuccessDialogOpen: (open) => {
      shellState.activationSuccessDialogOpen = open;
    },
    setActivationSuccessUseInstallGuides: (useInstallGuides) => {
      shellState.activationSuccessUseInstallGuides = useInstallGuides;
    },
    setActiveTab: (tab) => {
      shellState.activeTab = tab;
    },
    setScreen: (screen) => {
      shellState.screen = screen;
    },
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
    getData: getShellData,
    loadData: deps.loadData,
    maybeShowActivationSuccessDialog,
    shouldWatch: () =>
      shellState.mode === "app" &&
      activationHandoff.hasPending(getShellData() || {}) &&
      !shellState.activationSuccessDialogOpen &&
      shellState.screen !== "admin",
    canRefreshOnResume: () =>
      shellState.mode === "app" &&
      shellState.screen !== "admin" &&
      !shellState.activationSuccessDialogOpen &&
      !deps.getPaymentModalOpen() &&
      !deps.getTopupModalOpen() &&
      !deps.getDeviceTopupModalOpen() &&
      !deps.getChangeModalOpen() &&
      !deps.getChangeConfirmOpen() &&
      activationHandoff.hasPending(getShellData() || {}),
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
