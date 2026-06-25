import { activeTabForWebappSection } from "./sectionAvailability.js";
import {
  resolveInitialLoadRoute,
  resolveLoadedWebappRoute,
  resolveSupportLoadRoute,
} from "./appLoadFlow.js";
import type { ApplyPostLoadBillingDeeplinksInput } from "./billingDeeplinkEffects.js";
import type { LoadSectionDataInput } from "./sectionDataLoader.js";

type WebappRecord = Record<string, unknown>;

export type AppLoadDataOptions = {
  adminSection?: string | null;
  fresh?: boolean;
  preserveView?: boolean;
  section?: string | null;
};

type RouteState = {
  activeTab: string;
  adminActiveSection: string;
  screen: string;
};

type RouteStatePatch = {
  activeTab?: string;
  adminActiveSection?: string;
  mode?: string;
  screen?: string;
};

type AdminRuntime = {
  cancelAdminAssetsPrefetch: () => void;
  ensureAdminBundle: () => Promise<unknown>;
  ensureI18nScope: (scope: string) => Promise<unknown>;
  scheduleAdminAssetsPrefetch: (adminAllowed?: boolean) => void;
};

type ModalState = {
  changeModalOpen: boolean;
  deviceTopupModalOpen: boolean;
  topupKind: string;
  topupModalOpen: boolean;
};

type AppLoadExecutorDeps = {
  adminRuntime: AdminRuntime;
  applyPostLoadBillingDeeplinks: (input: ApplyPostLoadBillingDeeplinksInput) => void;
  currentSearchParams: () => URLSearchParams;
  dataClientLoadData: (options: { fresh: boolean }) => Promise<WebappRecord>;
  getModalState: () => ModalState;
  getRouteState: () => RouteState;
  getWindowSearch: () => string;
  hydrateSupportUnread: (input: { supportEnabled: boolean; unreadCount: unknown }) => void;
  initialAdminSectionFromLocation: () => string;
  isDocsDemo: () => boolean;
  isMock: () => boolean;
  loadDeviceTopupOptions: () => Promise<unknown>;
  loadInstallGuides: () => unknown;
  loadSectionData: (input: LoadSectionDataInput) => Promise<void>;
  loadTariffChangeOptions: () => Promise<unknown>;
  loadTopupOptions: (kind: string) => Promise<unknown>;
  resetBillingSelection: (defaultMethod: string) => void;
  routePathnameFromLocation: () => string;
  routePrefix: string;
  setData: (payload: WebappRecord) => void;
  setDocsDemoParentRouteConsumed: () => void;
  setRouteState: (patch: RouteStatePatch) => void;
  showAdminUnavailable: () => void;
  syncLoadedRoute: (input: {
    initialAdminSection: string | null;
    initialSupportTicketId: number | null;
    section: string;
    supportTargetPath: string | null;
  }) => void;
};

function recordField(value: unknown): WebappRecord {
  return value && typeof value === "object" ? (value as WebappRecord) : {};
}

function arrayField(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function defaultPaymentMethodId(payload: WebappRecord): string {
  const firstMethod = recordField(arrayField(payload.payment_methods)[0]);
  return String(firstMethod.id || "");
}

export function createAppLoadExecutor({
  adminRuntime,
  applyPostLoadBillingDeeplinks,
  currentSearchParams,
  dataClientLoadData,
  getModalState,
  getRouteState,
  getWindowSearch,
  hydrateSupportUnread,
  initialAdminSectionFromLocation,
  isDocsDemo,
  isMock,
  loadDeviceTopupOptions,
  loadInstallGuides,
  loadSectionData,
  loadTariffChangeOptions,
  loadTopupOptions,
  resetBillingSelection,
  routePathnameFromLocation,
  routePrefix,
  setData,
  setDocsDemoParentRouteConsumed,
  setRouteState,
  showAdminUnavailable,
  syncLoadedRoute,
}: AppLoadExecutorDeps) {
  async function loadData(options: AppLoadDataOptions = {}): Promise<WebappRecord> {
    const currentQuery = currentSearchParams();
    const routeState = getRouteState();
    const initialRoute = resolveInitialLoadRoute({
      activeTab: routeState.activeTab,
      adminActiveSection: routeState.adminActiveSection,
      adminSection: options.adminSection,
      fallbackAdminSection: initialAdminSectionFromLocation(),
      mock: isMock(),
      pathname: routePathnameFromLocation(),
      preserveView: options.preserveView === true,
      routePrefix,
      screen: routeState.screen,
      screenQuery: currentQuery.get("screen"),
      section: options.section,
    });
    const installGuidesPromise = initialRoute.shouldPreloadInstallGuides
      ? loadInstallGuides()
      : null;
    const payload = await dataClientLoadData({ fresh: options.fresh === true });
    if (!payload.ok) throw new Error(String(payload.error || "load_failed"));
    setData(payload);
    resetBillingSelection(defaultPaymentMethodId(payload));

    const loadedRoute = resolveLoadedWebappRoute({
      fallbackAdminSection: initialAdminSectionFromLocation(),
      payload,
      preservedAdminSection: initialRoute.preservedAdminSection,
      routeSection: initialRoute.routeSection,
    });
    let section = loadedRoute.section;
    const initialAdminSection = loadedRoute.initialAdminSection;
    if (section === "admin" && recordField(payload.user).is_admin) {
      adminRuntime.cancelAdminAssetsPrefetch();
      setRouteState({
        activeTab: "settings",
        adminActiveSection: initialAdminSection || "stats",
        mode: "app",
        screen: "admin",
      });
      try {
        await adminRuntime.ensureI18nScope("admin");
        await adminRuntime.ensureAdminBundle();
      } catch (_error) {
        void _error;
        section = "settings";
        setRouteState({
          activeTab: "settings",
          screen: "settings",
        });
        showAdminUnavailable();
      }
    }

    const supportRoute = resolveSupportLoadRoute({
      pathname: routePathnameFromLocation(),
      routePrefix,
      section,
    });
    const initialSupportTicketId = supportRoute.initialSupportTicketId;
    if (isDocsDemo()) setDocsDemoParentRouteConsumed();
    setRouteState({
      activeTab:
        section === loadedRoute.section
          ? loadedRoute.activeTab
          : activeTabForWebappSection(section),
      mode: "app",
      screen: section,
    });
    if (loadedRoute.shouldPrefetchAdminAssets) {
      adminRuntime.scheduleAdminAssetsPrefetch(true);
    }
    hydrateSupportUnread({
      supportEnabled: loadedRoute.supportEnabled,
      unreadCount: payload.support_unread_count,
    });
    syncLoadedRoute({
      initialAdminSection,
      initialSupportTicketId,
      section,
      supportTargetPath: supportRoute.targetPath,
    });
    await loadSectionData({
      initialSupportTicketId,
      installGuidesPromise,
      payload,
      section,
    });

    const modalState = getModalState();
    if (modalState.topupModalOpen) await loadTopupOptions(modalState.topupKind);
    if (modalState.deviceTopupModalOpen) await loadDeviceTopupOptions();
    if (modalState.changeModalOpen) await loadTariffChangeOptions();

    applyPostLoadBillingDeeplinks({
      defaultMethod: defaultPaymentMethodId(payload),
      plans: arrayField(payload.plans) as ApplyPostLoadBillingDeeplinksInput["plans"],
      search: getWindowSearch(),
      subscription: recordField(payload.subscription),
    });
    return payload;
  }

  return {
    loadData,
  };
}
