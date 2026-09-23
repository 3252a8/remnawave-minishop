import { activeTabForWebappSection } from "./sectionAvailability.js";
import {
  resolveInitialLoadRoute,
  resolveLoadedWebappRoute,
  resolveSupportLoadRoute,
} from "./appLoadFlow.js";
import type { ApplyPostLoadBillingDeeplinksInput } from "./billingDeeplinkEffects.js";
import type { LoadSectionDataInput } from "./sectionDataLoader.js";
import { createLoadPerfProbe } from "./loadPerfProbe.js";
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
  preloadAdminBundle: () => Promise<unknown>;
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
  ensureWebappLanguage: (language: string) => Promise<void>;
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
  rememberLanguage: (language: string) => void;
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
  ensureWebappLanguage,
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
  rememberLanguage,
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
    const perfProbe = createLoadPerfProbe(currentQuery.has("perfprobe"), initialRoute.routeSection);
    const installGuidesPromise = initialRoute.shouldPreloadInstallGuides
      ? loadInstallGuides()
      : null;
    const pendingAdminPreload =
      initialRoute.routeSection === "admin"
        ? adminRuntime.preloadAdminBundle().catch(() => false)
        : null;
    const payload = await dataClientLoadData({ fresh: options.fresh === true });
    perfProbe.mark("data");
    if (!payload.ok) throw new Error(String(payload.error || "load_failed"));
    const userLanguage = String(recordField(payload.user).language_code || "");
    if (userLanguage) {
      try {
        await ensureWebappLanguage(userLanguage);
      } catch (_error) {
        void _error;
      }
      rememberLanguage(userLanguage);
    }
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
          pendingAdminPreload,
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
    perfProbe.mark("admin");

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
    perfProbe.mark("section");

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
    perfProbe.finish(section);
    return payload;
  }

  return {
    loadData,
  };
}
