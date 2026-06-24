import { adminSectionFromPath, normalizeAdminSection } from "./routes.js";

type SyncAppSectionPath = (
  section: string,
  replace?: boolean,
  adminSection?: string | null,
  adminUserId?: string | number | null
) => void;

type AdminPanelActionDeps = {
  cancelAdminAssetsPrefetch: () => void;
  clearLanguageClickGuard: () => void;
  closePaymentModal: () => void;
  ensureAdminBundle: () => Promise<unknown>;
  ensureI18nScope: (scope: string) => Promise<unknown> | unknown;
  getAdminActiveSection: () => string;
  getRoutePathname: () => string;
  getScreen: () => string;
  isAdmin: () => boolean;
  isFileProtocol: () => boolean;
  routePrefix?: string;
  setActiveTab: (tab: string) => void;
  setAdminActiveSection: (section: string) => void;
  setScreen: (screen: string) => void;
  showToast: (message: unknown) => void;
  syncAppSectionPath: SyncAppSectionPath;
  t: (key: string) => unknown;
};

export function createAdminPanelActions({
  cancelAdminAssetsPrefetch,
  clearLanguageClickGuard,
  closePaymentModal,
  ensureAdminBundle,
  ensureI18nScope,
  getAdminActiveSection,
  getRoutePathname,
  getScreen,
  isAdmin,
  isFileProtocol,
  routePrefix = "",
  setActiveTab,
  setAdminActiveSection,
  setScreen,
  showToast,
  syncAppSectionPath,
  t,
}: AdminPanelActionDeps) {
  async function openAdminPanel() {
    if (!isAdmin()) return;
    clearLanguageClickGuard();
    closePaymentModal();
    const nextAdminSection = normalizeAdminSection(
      getAdminActiveSection() || adminSectionFromPath(getRoutePathname(), routePrefix)
    );
    cancelAdminAssetsPrefetch();
    setActiveTab("settings");
    setScreen("admin");
    setAdminActiveSection(nextAdminSection);
    syncAppSectionPath("admin", false, nextAdminSection);
    try {
      await ensureI18nScope("admin");
      await ensureAdminBundle();
    } catch (_error) {
      void _error;
      if (getScreen() === "admin") {
        setScreen("settings");
        setActiveTab("settings");
        syncAppSectionPath("settings");
      }
      showToast(t("wa_unavailable"));
    }
  }

  function closeAdminPanel() {
    setScreen("settings");
    setActiveTab("settings");
    syncAppSectionPath("settings");
  }

  function handleAdminSectionChange(
    adminSection: string,
    adminUserId: string | number | null = null
  ) {
    if (getScreen() !== "admin") return;
    const nextAdminSection = normalizeAdminSection(adminSection);
    setAdminActiveSection(nextAdminSection);
    if (isFileProtocol()) return;
    syncAppSectionPath("admin", false, nextAdminSection, adminUserId);
  }

  return {
    closeAdminPanel,
    handleAdminSectionChange,
    openAdminPanel,
  };
}
