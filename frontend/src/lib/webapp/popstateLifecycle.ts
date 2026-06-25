import { resolvePopstateRoute, type PopstateRouteDecision } from "./appRouteLifecycle.js";
import { sectionFromPath } from "./routes.js";

type MaybePromise<T = void> = T | Promise<T>;

type AdminRuntime = {
  cancelAdminAssetsPrefetch: () => void;
  ensureAdminBundle: () => Promise<unknown>;
  ensureI18nScope: (scope: string) => Promise<unknown>;
};

type PopstateLifecycleDeps = {
  adminRuntime: AdminRuntime;
  boot: () => MaybePromise;
  canUseInstallGuides: () => boolean;
  currentSearchParams: () => URLSearchParams;
  getDevicesEnabled: () => boolean;
  getFallbackAdminSection: () => string;
  getIsAdmin: () => boolean;
  getMode: () => string;
  getScreen: () => string;
  getSupportEnabled: () => boolean;
  getWindowPathname?: () => string;
  isDocsDemo: boolean;
  loadDevices: () => void;
  loadInstallGuides: () => void;
  loadPublicInstall: (shareToken: string) => MaybePromise;
  loadSupport: () => void;
  routePathnameFromLocation: () => string;
  routePrefix: string;
  setActiveTab: (tab: string) => void;
  setAdminActiveSection: (section: string) => void;
  setPasswordLoginMode: (enabled: boolean, replace?: boolean) => void;
  setScreen: (screen: string) => void;
  showAdminUnavailable: () => void;
  startSupportPolling: () => void;
  syncAppSectionPath: (section: string, replace?: boolean) => void;
};

export function createPopstateLifecycle({
  adminRuntime,
  boot,
  canUseInstallGuides,
  currentSearchParams,
  getDevicesEnabled,
  getFallbackAdminSection,
  getIsAdmin,
  getMode,
  getScreen,
  getSupportEnabled,
  getWindowPathname = () => (typeof window === "undefined" ? "" : window.location.pathname),
  isDocsDemo,
  loadDevices,
  loadInstallGuides,
  loadPublicInstall,
  loadSupport,
  routePathnameFromLocation,
  routePrefix,
  setActiveTab,
  setAdminActiveSection,
  setPasswordLoginMode,
  setScreen,
  showAdminUnavailable,
  startSupportPolling,
  syncAppSectionPath,
}: PopstateLifecycleDeps) {
  function handleAdminDecision(decision: Extract<PopstateRouteDecision, { kind: "admin" }>): void {
    setAdminActiveSection(decision.adminSection);
    adminRuntime.cancelAdminAssetsPrefetch();
    setActiveTab(decision.activeTab);
    setScreen(decision.section);
    const pathAtStart = getWindowPathname();
    void Promise.all([
      adminRuntime.ensureI18nScope("admin"),
      adminRuntime.ensureAdminBundle(),
    ]).catch(() => {
      if (sectionFromPath(routePathnameFromLocation(), routePrefix) !== "admin") return;
      if (getWindowPathname() !== pathAtStart) return;
      if (getScreen() === "admin") {
        setActiveTab("settings");
        setScreen("settings");
        syncAppSectionPath("settings", true);
      }
      showAdminUnavailable();
    });
  }

  function handleSectionDecision(
    decision: Extract<PopstateRouteDecision, { kind: "section" }>
  ): void {
    setActiveTab(decision.activeTab);
    setScreen(decision.section);
    if (decision.loadDevices) loadDevices();
    if (decision.loadSupport) {
      loadSupport();
      startSupportPolling();
    }
    if (decision.loadInstallGuides) loadInstallGuides();
  }

  function handlePopstate(): PopstateRouteDecision {
    const currentQuery = currentSearchParams();
    const decision = resolvePopstateRoute({
      canUseInstallGuides: canUseInstallGuides(),
      devicesEnabled: getDevicesEnabled(),
      fallbackAdminSection: getFallbackAdminSection(),
      isAdmin: getIsAdmin(),
      isDocsDemo,
      mode: getMode(),
      pathname: routePathnameFromLocation(),
      routePrefix,
      screenQuery: currentQuery.get("screen"),
      supportEnabled: getSupportEnabled(),
    });

    if (decision.kind === "publicInstall") {
      void loadPublicInstall(decision.shareToken);
      return decision;
    }
    if (decision.kind === "boot") {
      void boot();
      return decision;
    }
    if (decision.kind === "login") {
      setPasswordLoginMode(decision.passwordLoginEnabled, true);
      setScreen("login");
      return decision;
    }
    if (decision.kind === "admin") {
      handleAdminDecision(decision);
      return decision;
    }
    if (decision.kind === "section") {
      handleSectionDecision(decision);
    }
    return decision;
  }

  return {
    handlePopstate,
  };
}
