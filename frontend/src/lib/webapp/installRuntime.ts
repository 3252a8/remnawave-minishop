import { createPublicInstallActions } from "./publicInstallActions.js";

type WebappRecord = Record<string, unknown>;

type PublicInstallActionDeps = Parameters<typeof createPublicInstallActions>[0];
type PublicInstallGuidesStore = PublicInstallActionDeps["installGuidesStore"];

type InstallRuntimeDeps = {
  canUseInstallGuides: () => boolean;
  getOrigin: () => string;
  getPreloadHost: () => Record<string, unknown> | null;
  goInstall: () => void;
  installGuidesStore: PublicInstallGuidesStore;
  openConnectLink: () => void;
  openTrialConnectLink: () => void;
  setActiveTab: (tab: string) => void;
  setMode: (mode: string) => void;
  setPublicInstallSubscription: (subscription: WebappRecord | null) => void;
  setPublicInstallToken: (token: string) => void;
  setScreen: (screen: string) => void;
};

export function createInstallRuntime({
  canUseInstallGuides,
  getOrigin,
  getPreloadHost,
  goInstall,
  installGuidesStore,
  openConnectLink,
  openTrialConnectLink,
  setActiveTab,
  setMode,
  setPublicInstallSubscription,
  setPublicInstallToken,
  setScreen,
}: InstallRuntimeDeps) {
  const publicInstallActions = createPublicInstallActions({
    getOrigin,
    getPreloadHost: getPreloadHost as PublicInstallActionDeps["getPreloadHost"],
    installGuidesStore,
    setActiveTab,
    setMode,
    setPublicInstallSubscription,
    setPublicInstallToken,
    setScreen,
  });

  function openInstallOrConnect() {
    if (canUseInstallGuides()) {
      goInstall();
      return;
    }
    openConnectLink();
  }

  function openTrialInstallOrConnect() {
    if (canUseInstallGuides()) {
      goInstall();
      return;
    }
    openTrialConnectLink();
  }

  return {
    ...publicInstallActions,
    openInstallOrConnect,
    openTrialInstallOrConnect,
  };
}
