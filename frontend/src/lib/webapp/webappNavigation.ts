type NavigationDeps = {
  canUseInstallGuides: () => boolean;
  closePaymentModal: () => void;
  devicesEnabled: () => boolean;
  loadDevices: () => void;
  loadInstallGuides: () => void;
  loadSupport: () => void;
  openConnectLink: () => void;
  setActiveTab: (tab: string) => void;
  setScreen: (screen: string) => void;
  supportEnabled: () => boolean;
  syncSectionPath: (section: string) => void;
};

export function createWebappNavigation({
  canUseInstallGuides,
  closePaymentModal,
  devicesEnabled,
  loadDevices,
  loadInstallGuides,
  loadSupport,
  openConnectLink,
  setActiveTab,
  setScreen,
  supportEnabled,
  syncSectionPath,
}: NavigationDeps) {
  function showSection(section: string, tab = section) {
    closePaymentModal();
    setActiveTab(tab);
    setScreen(section);
    syncSectionPath(section);
  }

  function goHome() {
    showSection("home");
  }

  function goInstall() {
    if (!canUseInstallGuides()) {
      openConnectLink();
      return false;
    }
    showSection("install", "home");
    loadInstallGuides();
    return true;
  }

  function goInvite() {
    showSection("invite");
  }

  function goDevices() {
    if (!devicesEnabled()) return false;
    showSection("devices");
    loadDevices();
    return true;
  }

  function goSupport() {
    if (!supportEnabled()) return false;
    showSection("support");
    loadSupport();
    return true;
  }

  function goSettings() {
    showSection("settings");
  }

  return {
    goDevices,
    goHome,
    goInstall,
    goInvite,
    goSettings,
    goSupport,
  };
}
