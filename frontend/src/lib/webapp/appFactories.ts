import { createAuthStore } from "./stores/authStore";
import { createBillingStore } from "./stores/billingStore";
import { createAccountStore } from "./stores/accountStore";
import { createActionsStore } from "./stores/actionsStore";
import { createWebappDataClient } from "./dataClient";
import { buildApiUrl } from "./publicApi";
import { createWebappActivationContext } from "./webappActivationContext";
import { createAuthRuntime } from "./authRuntime.js";
import { createResumeLifecycle } from "./resumeLifecycle.js";
import { createAppBootRuntime } from "./appBootRuntime.js";
import { createDemoAuth } from "./demoAuth";
import { createUiChrome } from "./uiChrome";
import { createEmailAvatarSync } from "./emailAvatarSync.js";
import {
  setAccountStore,
  setActionsStore,
  setAuthStore,
  setBillingStore,
  setDevicesStore,
  setInstallGuidesStore,
  setSupportStore,
} from "./context";
import { createBillingDeeplinkEffects } from "./billingDeeplinkEffects.js";
import { createWebappSectionContext } from "./webappSectionContext";
import { createWebappSessionActions } from "./webappSessionActions.js";
import { createAdminRuntime } from "./adminRuntime.js";
import { createBillingActions } from "./billingActions";
import { invalidateWebappTariffOptionCaches } from "./billingOptionCache.js";
import { buildAdminPanelProps } from "./adminPanelProps.js";
import { shellState } from "./shellState.svelte";
import { structuredCloneSafe } from "./browser.js";
import {
  createAppActionRuntime,
  type AppActionRuntime,
  type AppActionRuntimeDeps,
} from "./appActionRuntime.js";
import type { AppLoadDataOptions } from "./appLoadExecutor.js";
import type { AppShellView } from "./appShellView.js";
import type { TelegramRuntime, TelegramWebApp } from "./telegramRuntime.js";
import {
  asWebappRecord,
  asWebappRecordOrNull,
  type AdminPanelProps,
  type PaymentMethod,
  type PlanView,
  type SubscriptionView,
  type TariffView,
  type UserProfile,
  type WebappConfig,
  type WebappData,
  type WebappMockRuntime,
  type WebappMockSource,
  type WebappRecord,
} from "./types.js";

type Tick = typeof import("svelte").tick;
type TelegramSdk = TelegramRuntime<TelegramWebApp | null>["telegramSdk"];
type LoadTelegramSdk = Parameters<typeof createAppBootRuntime>[0]["loadTelegramSdk"];
type SyncAppSectionPath = (section: string, replace?: boolean) => void;
type LoadData = (options?: AppLoadDataOptions) => Promise<WebappData>;
type RuntimeMockApi = NonNullable<WebappMockRuntime["mockApi"]>;

export type AppFactoriesDeps = {
  CFG: WebappConfig;
  MOCK: WebappMockSource | null;
  MOCK_SOURCE: WebappMockSource;
  adminBundleApi: () => WebappRecord | null;
  adminBundleError: () => string;
  canUseInstallGuides: () => boolean;
  cleanDocsDemoRouteQuery: () => void;
  currentSearchParams: () => URLSearchParams;
  csrfCookieName: string;
  docsDemoParentSearchParams: () => URLSearchParams | null;
  getAppActions: () => AppActionRuntime;
  getChangeConfirmOpen: () => boolean;
  getChangeModalOpen: () => boolean;
  getCurrentLang: () => string;
  getData: () => WebappData | null;
  getDemoAuthLogin: () => boolean;
  getDeviceTopupModalOpen: () => boolean;
  getIsAdmin: () => boolean;
  getMethods: () => PaymentMethod[];
  getPaymentModalOpen: () => boolean;
  getPlans: () => PlanView[];
  getRuntimeMockApi: () => RuntimeMockApi | null;
  getScreen: () => string;
  getSingleTariffMode: () => boolean;
  getSubscription: () => SubscriptionView;
  getTariffCatalog: () => TariffView[];
  getTariffMode: () => boolean;
  getTelegramMiniAppInitData: () => string;
  getTelegramNotificationsNeedPrompt: () => boolean;
  getTelegramOAuthClientId: () => number;
  getTg: () => TelegramWebApp | null;
  getTopupModalOpen: () => boolean;
  getUser: () => UserProfile;
  hasEmailCodeLoginDeeplink: () => boolean;
  hasTelegramLaunchParams: () => boolean;
  initialTg: TelegramWebApp | null;
  isDocsDemo: boolean;
  loadData: LoadData;
  loadTelegramSdk: LoadTelegramSdk;
  manualLogoutFlagKey: string;
  normalizeLangCode: (language: string) => string;
  openExternalLink: (url: string) => void;
  readCheckoutPromoDeeplink: () => string;
  readRenewalDeeplink: () => { tariffKey: string } | null;
  readTelegramMiniAppInitDataFromLocation: () => string;
  routePathnameFromLocation: () => string;
  routePrefix: string;
  showToast: (message: unknown) => void;
  stripCheckoutPromoQueryFromUrl: () => void;
  stripRenewalLoginQueryFromUrl: () => void;
  stripTopupQueryFromUrl: () => void;
  syncAppSectionPath: SyncAppSectionPath;
  t: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  telegramNotificationsResumeCooldownMs: number;
  telegramSdk: TelegramSdk;
  tick: Tick;
  updateI18nMessages: (messages: WebappRecord) => void;
};

export function createAppFactories({
  CFG,
  MOCK,
  MOCK_SOURCE,
  adminBundleApi,
  adminBundleError,
  canUseInstallGuides,
  cleanDocsDemoRouteQuery,
  currentSearchParams,
  csrfCookieName,
  docsDemoParentSearchParams,
  getAppActions,
  getChangeConfirmOpen,
  getChangeModalOpen,
  getCurrentLang,
  getData,
  getDemoAuthLogin,
  getDeviceTopupModalOpen,
  getIsAdmin,
  getMethods,
  getPaymentModalOpen,
  getPlans,
  getRuntimeMockApi,
  getScreen,
  getSingleTariffMode,
  getSubscription,
  getTariffCatalog,
  getTariffMode,
  getTelegramMiniAppInitData,
  getTelegramNotificationsNeedPrompt,
  getTelegramOAuthClientId,
  getTg,
  getTopupModalOpen,
  getUser,
  hasEmailCodeLoginDeeplink,
  hasTelegramLaunchParams,
  initialTg,
  isDocsDemo,
  loadData,
  loadTelegramSdk,
  manualLogoutFlagKey,
  normalizeLangCode,
  openExternalLink,
  readCheckoutPromoDeeplink,
  readRenewalDeeplink,
  readTelegramMiniAppInitDataFromLocation,
  routePathnameFromLocation,
  routePrefix,
  showToast,
  stripCheckoutPromoQueryFromUrl,
  stripRenewalLoginQueryFromUrl,
  stripTopupQueryFromUrl,
  syncAppSectionPath,
  t,
  telegramNotificationsResumeCooldownMs,
  telegramSdk,
  tick,
  updateI18nMessages,
}: AppFactoriesDeps) {
  let billingStore!: ReturnType<typeof createBillingStore>;
  let installGuidesStore!: ReturnType<typeof createWebappSectionContext>["installGuidesStore"];
  let authStore!: ReturnType<typeof createAuthStore>;
  let actionsStore!: ReturnType<typeof createActionsStore>;
  let accountStore!: ReturnType<typeof createAccountStore>;
  let bootRuntime!: ReturnType<typeof createAppBootRuntime>;
  let showLogin!: ReturnType<typeof createAuthRuntime>["showLogin"];

  const adminRuntime = createAdminRuntime({
    fetchI18nScope: async (scope) => {
      const response = await fetch(buildApiUrl(`/i18n?scope=${encodeURIComponent(scope)}`), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      return response.ok ? response.json() : null;
    },
    getAdminAssets: () => ({
      adminCssAsset: CFG.adminCssAsset,
      adminJsAsset: CFG.adminJsAsset,
    }),
    getIsMock: () => Boolean(MOCK),
    getShouldPrefetch: () => getIsAdmin() && getScreen() !== "admin",
    invalidateTariffOptionCaches: () => {
      invalidateWebappTariffOptionCaches(billingStore);
    },
    loadData: (options) => loadData(options as AppLoadDataOptions),
    mergeMessages: (messages) => {
      updateI18nMessages(asWebappRecord(messages));
    },
    reloadWindow: () => {
      if (typeof window !== "undefined") window.location.reload();
    },
    resetInstallGuides: () => {
      installGuidesStore.reset();
    },
    setBundleState: (api, error) => {
      const nextApi = asWebappRecordOrNull(api);
      if (adminBundleApi() !== nextApi) shellState.adminBundleApi = nextApi;
      if (adminBundleError() !== error) shellState.adminBundleError = error;
    },
  });
  shellState.guestLanguage = normalizeLangCode(CFG.language || "ru");
  const { clearLanguageClickGuard, setLanguageMenuOpen, syncBodyScrollLock, updateGuestLanguage } =
    createUiChrome({
      normalizeLangCode,
      getCurrentLang,
    });
  const { clearManualLogoutFlag, clearToken, isManuallyLoggedOut, markManualLogout, setToken } =
    createWebappSessionActions({
      csrfCookieName,
      isMock: () => Boolean(MOCK),
      manualLogoutFlagKey,
    });
  const dataClient = createWebappDataClient({
    csrfCookieName,
    getAuthToken: () => shellState.token,
    getCsrfToken: () => shellState.csrfToken,
    onUnauthorized: () => {
      clearToken();
      showLogin();
    },
    mockApi:
      MOCK && getRuntimeMockApi()
        ? (path, options, context) => getRuntimeMockApi()?.(path, options, context) ?? null
        : null,
    getMockContext: () => ({
      currentLang: getCurrentLang(),
      normalizeLangCode,
      clone: structuredCloneSafe,
    }),
  });
  const api = dataClient.api;
  const publicApi = dataClient.publicApi;
  const billing = createBillingActions({
    api,
  });
  const emailAvatarSync = createEmailAvatarSync();
  const activation = createWebappActivationContext({
    billing,
    loadData,
    getPaymentModalOpen,
    getTopupModalOpen,
    getDeviceTopupModalOpen,
    getChangeModalOpen,
    getChangeConfirmOpen,
    canUseInstallGuides,
    closePaymentModal: () => billingStore.closePaymentModal(),
    loadInstallGuides: (force) => installGuidesStore.load(force),
    openActivationConnectLink: () => getAppActions().openActivationConnectLink(),
    syncAppSectionPath,
  });
  authStore = createAuthStore({
    publicApi,
    setToken,
    loadData,
    telegramSdk,
    getTg,
    t,
    currentLang: getCurrentLang,
  });
  const demoAuth = createDemoAuth({
    authStore,
    getCurrentSearchParams: currentSearchParams,
    getMockSource: () => MOCK_SOURCE,
    getParentSearchParams: docsDemoParentSearchParams,
    isMockEnabled: () => Boolean(MOCK),
  });
  billingStore = createBillingStore({
    billing,
    loadData,
    t,
    showToast,
    openExternalLink,
    onSubscriptionActivationPending: activation.rememberActivationPending,
    onSubscriptionActivated: activation.handleSubscriptionActivated,
    tg: initialTg,
    getTg: () => getTg() || telegramSdk.refresh(),
    telegramSdk,
  });
  const { applyPostLoadBillingDeeplinks } = createBillingDeeplinkEffects({
    billingStore,
    // actionsStore is created below; the deeplink fires post-load, so the
    // lazy closure always sees the initialized store.
    handleCheckoutPromoDeeplink: (code, context) => {
      void actionsStore.handlePromoDeeplink(code, context);
    },
    readCheckoutPromoDeeplink,
    readRenewalDeeplink,
    setHomeRoute: () => {
      shellState.activeTab = "home";
      shellState.screen = "home";
      syncAppSectionPath("home", true);
    },
    stripCheckoutPromoQueryFromUrl,
    stripRenewalLoginQueryFromUrl,
    stripTopupQueryFromUrl,
  });
  const sectionContext = createWebappSectionContext({
    api,
    t,
    showToast,
    routePrefix,
    cleanDocsDemoRouteQuery,
    syncAppSectionPath,
  });
  const { devicesStore, supportStore, loadSectionData, hydrateSupportUnread, syncLoadedRoute } =
    sectionContext;
  installGuidesStore = sectionContext.installGuidesStore;
  actionsStore = createActionsStore({
    api,
    t,
    showToast,
    loadData,
    maybeShowActivationSuccessDialog: activation.maybeShowActivationSuccessDialog,
    startCheckoutPromo: (code) => {
      shellState.activeTab = "home";
      shellState.screen = "home";
      syncAppSectionPath("home", true);
      billingStore.setCheckoutPromoInput(code);
      billingStore.openPaymentModal(
        getTariffMode(),
        getSingleTariffMode(),
        getTariffCatalog(),
        getSubscription(),
        getPlans(),
        String(getMethods()?.[0]?.id || ""),
        {
          preferCheckout: true,
          selectDefaultTariff: true,
        }
      );
      void billingStore.applyCheckoutPromo();
    },
    prefillCheckoutPromo: (code) => {
      billingStore.setCheckoutPromoInput(code);
      void billingStore.applyCheckoutPromo();
    },
  });
  const authRuntime = createAuthRuntime({
    authStore,
    cleanDocsDemoRouteQuery,
    isDocsDemo,
    routePathnameFromLocation,
    routePrefix,
    tick,
  });
  const authRuntimeActions = authRuntime;
  showLogin = authRuntimeActions.showLogin;
  bootRuntime = createAppBootRuntime({
    loadPublicInstall: (shareToken) => getAppActions().loadPublicInstall(shareToken),
    isDemoAuthMock: () => Boolean(MOCK) && demoAuth.isDemoAuthMock(),
    prepareDemoAuthState: () => demoAuth.prepareAuthState(),
    mock: MOCK,
    hasTelegramLaunchParams,
    loadTelegramSdk,
    loadData,
    showLogin,
    clearToken,
    refreshSession: () => api("/auth/session"),
    clearManualLogoutFlag,
    isManuallyLoggedOut,
    hasEmailCodeLoginDeeplink,
    finalizeMagicLogin: (loginToken) => authStore.finalizeMagicLogin(loginToken),
    finalizeTelegramAuth: (authData, source) => authStore.finalizeTelegramAuth(authData, source),
    setAuthStatus: (message, isError = false) => authStore.setAuthStatus(message, isError),
    t,
    readTelegramMiniAppInitDataFromLocation,
    continueTelegramLinkPendingAction: () => getAppActions().continueTelegramLinkPendingAction(),
    hasPendingActivationHandoff: activation.hasPendingActivationHandoff,
    maybeShowActivationSuccessDialog: activation.maybeShowActivationSuccessDialog,
    startPendingActivationWatch: activation.startPendingActivationWatch,
    telegramNotificationsResumeCooldownMs,
    getTelegramNotificationsNeedPrompt,
  });
  const resumeLifecycle = createResumeLifecycle({
    clearLoginTooltip: () => {
      authStore.update((state) => ({ ...state, loginEmailTooltipOpen: false }));
    },
    refreshPendingActivationOnResume: () => {
      void activation.refreshPendingActivationOnResume();
    },
    refreshTelegramNotificationsOnResume: () => {
      void bootRuntime.refreshTelegramNotificationsOnResume();
    },
  });
  accountStore = createAccountStore({
    api,
    publicApi,
    setToken,
    loadData,
    t,
    showToast,
    clearToken,
    markManualLogout,
    showLogin,
    telegramSdk,
    getTg,
    getCurrentUser: () => getData()?.user || getUser() || {},
    getTelegramMiniAppInitData: () =>
      getTelegramMiniAppInitData() ||
      getTg()?.initData ||
      readTelegramMiniAppInitDataFromLocation(),
    isDemoAuthLogin: getDemoAuthLogin,
    getDemoTelegramAuthPayload: () => demoAuth.telegramAuthPayload(),
    telegramOAuthClientId: getTelegramOAuthClientId,
    currentLang: getCurrentLang,
    normalizeLangCode,
    updateLocalData: (updatedLanguage) => {
      const data = getData();
      if (!data?.user) return;
      shellState.data = { ...data, user: { ...data.user, language_code: updatedLanguage } };
    },
    activateTrial: () => actionsStore.activateTrial(),
    claimReferralWelcomeBonus: () => actionsStore.claimReferralWelcomeBonus(),
  });

  setAuthStore(authStore);
  setBillingStore(billingStore);
  setDevicesStore(devicesStore);
  setSupportStore(supportStore);
  setInstallGuidesStore(installGuidesStore);
  setActionsStore(actionsStore);
  setAccountStore(accountStore);

  return {
    accountStore,
    actionsStore,
    adminRuntime,
    api,
    applyPostLoadBillingDeeplinks,
    authStore,
    billing,
    billingStore,
    bootRuntime,
    clearLanguageClickGuard,
    closeActivationSuccessDialog: activation.closeActivationSuccessDialog,
    dataClient,
    demoAuth,
    devicesStore,
    emailAvatarSync,
    hydrateSupportUnread,
    installGuidesStore,
    loadSectionData,
    resumeLifecycle,
    setLanguageMenuOpen,
    setPasswordLoginMode: authRuntimeActions.setPasswordLoginMode,
    showLogin,
    stopPendingActivationWatch: activation.stopPendingActivationWatch,
    submitEmailOnEnter: authRuntimeActions.submitEmailOnEnter,
    supportStore,
    syncBodyScrollLock,
    syncLoadedRoute,
    updateGuestLanguage,
  };
}

export type ShellAppActionsDeps = {
  accountStore: AppActionRuntimeDeps["accountStore"];
  actionsStore: AppActionRuntimeDeps["actionsStore"];
  adminRuntime: AppActionRuntimeDeps["adminRuntime"];
  authStore: AppActionRuntimeDeps["authStore"];
  billing: AppActionRuntimeDeps["billing"];
  billingStore: AppActionRuntimeDeps["billingStore"];
  canUseInstallGuides: AppActionRuntimeDeps["canUseInstallGuides"];
  clearLanguageClickGuard: AppActionRuntimeDeps["clearLanguageClickGuard"];
  demoAuth: ReturnType<typeof createDemoAuth>;
  devicesStore: AppActionRuntimeDeps["devicesStore"];
  externalLinkActions: AppActionRuntimeDeps["externalLinkActions"];
  getRoutePathname: AppActionRuntimeDeps["getRoutePathname"];
  getSelectedPlan: AppActionRuntimeDeps["getSelectedPlan"];
  getShellView: () => AppShellView;
  getTrialActivationResult: AppActionRuntimeDeps["getTrialActivationResult"];
  installGuidesStore: AppActionRuntimeDeps["installGuidesStore"];
  loadData: AppActionRuntimeDeps["loadData"];
  refreshTelegram: AppActionRuntimeDeps["refreshTelegram"];
  routePrefix: string;
  showToast: AppActionRuntimeDeps["showToast"];
  supportStore: AppActionRuntimeDeps["supportStore"];
  syncAppSectionPath: AppActionRuntimeDeps["syncAppSectionPath"];
  t: AppActionRuntimeDeps["t"];
};

export function createShellAppActions({
  accountStore,
  actionsStore,
  adminRuntime,
  authStore,
  billing,
  billingStore,
  canUseInstallGuides,
  clearLanguageClickGuard,
  demoAuth,
  devicesStore,
  externalLinkActions,
  getRoutePathname,
  getSelectedPlan,
  getShellView,
  getTrialActivationResult,
  installGuidesStore,
  loadData,
  refreshTelegram,
  routePrefix,
  showToast,
  supportStore,
  syncAppSectionPath,
  t,
}: ShellAppActionsDeps): AppActionRuntime {
  return createAppActionRuntime({
    accountStore,
    actionsStore,
    adminRuntime,
    authStore,
    billing,
    billingStore,
    canUseInstallGuides,
    clearLanguageClickGuard,
    demoEmail: () => demoAuth.demoEmail(),
    devicesStore,
    externalLinkActions,
    getAppSettings: () => getShellView().appDataView.appSettings,
    getDevicesEnabled: () => getShellView().appDataView.devicesEnabled,
    getDemoTelegramAuthPayload: () => demoAuth.telegramAuthPayload(),
    getEmailAuthEnabled: () => getShellView().appDataView.emailAuthEnabled,
    getIsAdmin: () => getShellView().isAdmin,
    getIsFileProtocol: () => window.location.protocol === "file:",
    getMethods: () => getShellView().appDataView.methods,
    getOrigin: () => (typeof window !== "undefined" ? window.location.origin : ""),
    getPlans: () => getShellView().appDataView.plans,
    getPreloadHost: () => (typeof window !== "undefined" ? asWebappRecord(window) : null),
    getRoutePathname,
    getSelectedPlan,
    getSelectedTariffPlans: () => getShellView().billingView.selectedTariffPlans,
    getSingleTariffMode: () => getShellView().billingView.singleTariffMode,
    getSubscription: () => getShellView().appDataView.subscription,
    getSupportEnabled: () => getShellView().appDataView.supportEnabled,
    getTariffCatalog: () => getShellView().billingView.tariffCatalog,
    getTariffMode: () => getShellView().billingView.tariffMode,
    getTelegramNotificationsStartLink: () =>
      getShellView().accountView.telegramNotificationsStartLink,
    getTelegramOAuthClientId: () => getShellView().telegramOAuthClientId,
    getTrafficMode: () => getShellView().billingView.trafficMode,
    getTrialActivationResult,
    installGuidesStore,
    loadData,
    refreshTelegram,
    routePrefix,
    showToast,
    supportStore,
    syncAppSectionPath,
    t,
  });
}

export type AppAdminPanelPropsDeps = {
  adminActiveSection: string;
  adminRuntime: ReturnType<typeof createAdminRuntime>;
  api: ReturnType<typeof createWebappDataClient>["api"];
  appActions: AppActionRuntime;
  cfg: WebappConfig;
  getShellView: () => AppShellView;
  initialAdminSectionFromLocation: () => string;
  languageBusy: boolean;
  onLanguageChange: ReturnType<typeof createAccountStore>["updateAccountLanguage"];
  routePathnameFromLocation: () => string;
  routePrefix: string;
  screen: string;
  showToast: (message: unknown) => void;
  t: AppActionRuntimeDeps["t"];
};

export function buildAppAdminPanelProps({
  adminActiveSection,
  adminRuntime,
  api,
  appActions,
  cfg,
  getShellView,
  initialAdminSectionFromLocation,
  languageBusy,
  onLanguageChange,
  routePathnameFromLocation,
  routePrefix,
  screen,
  showToast,
  t,
}: AppAdminPanelPropsDeps): AdminPanelProps {
  const shellView = getShellView();
  return buildAdminPanelProps({
    adminActiveSection,
    api,
    appFaviconUrl: cfg.faviconUrl,
    appFaviconUseCustom: cfg.faviconUseCustom,
    appRepositoryUrl: cfg.appRepositoryUrl,
    appVersion: cfg.appVersion,
    brand: shellView.appDataView.brand,
    brandTitle: shellView.appDataView.brandTitle,
    currentLang: shellView.currentLang,
    fallbackAdminSection: initialAdminSectionFromLocation(),
    languageBusy,
    languageOptions: shellView.languageView.languageOptions,
    onClose: appActions.closeAdminPanel,
    onLanguageChange,
    onSectionChange: appActions.handleAdminSectionChange,
    onSettingsSaved: adminRuntime.handleAdminPersistedSaved,
    onTariffsSaved: adminRuntime.handleAdminPersistedSaved,
    onThemesSaved: adminRuntime.handleAdminPersistedSaved,
    onToast: showToast,
    onTranslationsSaved: adminRuntime.handleAdminTranslationsSaved,
    pathname: routePathnameFromLocation(),
    routePrefix,
    screen,
    t,
  });
}
