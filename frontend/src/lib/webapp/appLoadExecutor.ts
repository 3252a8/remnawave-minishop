import { activeTabForWebappSection } from "./sectionAvailability.js";
import {
  resolveInitialLoadRoute,
  resolveLoadedWebappRoute,
  resolveSupportLoadRoute,
} from "./appLoadFlow.js";
import type { ApplyPostLoadBillingDeeplinksInput } from "./billingDeeplinkEffects.js";
import type { LoadSectionDataInput } from "./sectionDataLoader.js";
import { shellState } from "./shellState.svelte";
import type { PlanView, SubscriptionView, WebappData, WebappRecord } from "./types";

export type AppLoadDataOptions = {
  adminSection?: string | null;
  fresh?: boolean;
  preserveView?: boolean;
  section?: string | null;
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
  dataClientLoadData: (options: { fresh: boolean }) => Promise<WebappData>;
  getModalState: () => ModalState;
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
  showAdminUnavailable,
  syncLoadedRoute,
}: AppLoadExecutorDeps) {
  async function loadData(options: AppLoadDataOptions = {}): Promise<WebappData> {
    const currentQuery = currentSearchParams();
    const initialRoute = resolveInitialLoadRoute({
      activeTab: shellState.activeTab,
      adminActiveSection: shellState.adminActiveSection,
      adminSection: options.adminSection,
      fallbackAdminSection: initialAdminSectionFromLocation(),
      mock: isMock(),
      pathname: routePathnameFromLocation(),
      preserveView: options.preserveView === true,
      routePrefix,
      screen: shellState.screen,
      screenQuery: currentQuery.get("screen"),
      section: options.section,
    });
    const installGuidesPromise = initialRoute.shouldPreloadInstallGuides
      ? loadInstallGuides()
      : null;
    const payload = await dataClientLoadData({ fresh: options.fresh === true });
    if (!payload.ok) throw new Error(String(payload.error || "load_failed"));
    shellState.data = payload;
    resetBillingSelection(defaultPaymentMethodId(payload));

    // A user can switch sections while the initial request is in flight. Resolve the
    // route again from the live URL and shell state so completing that request does
    // not restore the section that was active when it started.
    const currentRoute = resolveInitialLoadRoute({
      activeTab: shellState.activeTab,
      adminActiveSection: shellState.adminActiveSection,
      adminSection: options.adminSection,
      fallbackAdminSection: initialAdminSectionFromLocation(),
      mock: isMock(),
      pathname: routePathnameFromLocation(),
      preserveView: options.preserveView === true,
      routePrefix,
      screen: shellState.screen,
      screenQuery: currentSearchParams().get("screen"),
      section: options.section,
    });
    const loadedRoute = resolveLoadedWebappRoute({
      fallbackAdminSection: initialAdminSectionFromLocation(),
      partnerProgramPreview: currentSearchParams().has("partner_scenario"),
      payload,
      preservedAdminSection: currentRoute.preservedAdminSection,
      routeSection: currentRoute.routeSection,
    });
    let section = loadedRoute.section;
    const initialAdminSection = loadedRoute.initialAdminSection;
    if (section === "admin" && recordField(payload.user).is_admin) {
      adminRuntime.cancelAdminAssetsPrefetch();
      shellState.activeTab = "settings";
      shellState.adminActiveSection = initialAdminSection || "stats";
      shellState.mode = "app";
      shellState.screen = "admin";
      try {
        await Promise.all([
          adminRuntime.ensureI18nScope("admin"),
          adminRuntime.ensureAdminBundle(),
        ]);
      } catch (_error) {
        void _error;
        section = "settings";
        shellState.activeTab = "settings";
        shellState.screen = "settings";
        showAdminUnavailable();
      }
    }

    const supportRoute = resolveSupportLoadRoute({
      pathname: routePathnameFromLocation(),
      routePrefix,
      section,
    });
    const initialSupportTicketId = supportRoute.initialSupportTicketId;
    if (isDocsDemo()) shellState.docsDemoParentRouteConsumed = true;
    shellState.activeTab =
      section === loadedRoute.section ? loadedRoute.activeTab : activeTabForWebappSection(section);
    shellState.mode = "app";
    shellState.screen = section;
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
      plans: arrayField(payload.plans) as PlanView[],
      search: getWindowSearch(),
      subscription: recordField(payload.subscription) as SubscriptionView,
    });
    return payload;
  }

  return {
    loadData,
  };
}
