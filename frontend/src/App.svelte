<script lang="ts">
  import { onMount, setContext, tick } from "svelte";
  import { Toaster, toast as sonnerToast } from "svelte-sonner";
  import { createAuthStore } from "./lib/webapp/stores/authStore";
  import { createBillingStore } from "./lib/webapp/stores/billingStore";
  import { createAccountStore } from "./lib/webapp/stores/accountStore";
  import { createActionsStore } from "./lib/webapp/stores/actionsStore";
  import { Tooltip } from "$components/ui/primitives.js";

  import AppModeContent from "./webapp/AppModeContent.svelte";

  import {
    MANUAL_LOGOUT_FLAG_KEY,
    TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS,
    TELEGRAM_SDK_ACTION_TIMEOUT_MS,
    TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    TELEGRAM_WEBAPP_SCRIPT_URL,
  } from "./lib/webapp/constants.js";

  import {
    applyFavicon,
    applyDocumentTitle,
    readJsonScript,
    structuredCloneSafe,
  } from "./lib/webapp/browser.js";
  import { isExternalAppLaunchPath, readExternalAppLaunchTarget } from "./lib/webapp/appLinks.js";
  import { createWebappDataClient } from "./lib/webapp/dataClient";
  import { canUseSubscriptionInstallGuides } from "./lib/webapp/connectLinks.js";
  import { createI18n } from "./lib/webapp/i18n.js";
  import { createWebappActivationContext } from "./lib/webapp/webappActivationContext";
  import { createAuthRuntime } from "./lib/webapp/authRuntime.js";
  import { createResumeLifecycle } from "./lib/webapp/resumeLifecycle.js";
  import { createAppBootRuntime } from "./lib/webapp/appBootRuntime.js";
  import {
    currentSearchParams,
    hasEmailCodeLoginDeeplink,
    readRenewalDeeplink,
    stripRenewalLoginQueryFromUrl,
    stripTopupQueryFromUrl,
  } from "./lib/webapp/deeplinks";
  import { createDemoAuth } from "./lib/webapp/demoAuth";
  import { createDocsDemoRouter } from "./lib/webapp/docsDemoRoutes.js";
  import { createUiChrome } from "./lib/webapp/uiChrome";
  import { createEmailAvatarSync } from "./lib/webapp/emailAvatarSync.js";
  import { createBillingDeeplinkEffects } from "./lib/webapp/billingDeeplinkEffects.js";
  import { createWebappSectionContext } from "./lib/webapp/webappSectionContext";
  import { readThemePreviewDraft, syncThemeGoogleFonts } from "./lib/webapp/themeStyle.js";
  import { computeAppShellView, type AppShellView } from "./lib/webapp/appShellView.js";
  import { createAppActionRuntime, type AppActionRuntime } from "./lib/webapp/appActionRuntime.js";
  import { createWebappSessionActions } from "./lib/webapp/webappSessionActions.js";
  import { buildAdminPanelProps } from "./lib/webapp/adminPanelProps.js";
  import { createAdminRuntime } from "./lib/webapp/adminRuntime.js";
  import { createExternalLinkRuntime } from "./lib/webapp/externalLinkRuntime.js";
  import { createAppLoadExecutor, type AppLoadDataOptions } from "./lib/webapp/appLoadExecutor.js";
  import { createPopstateLifecycle } from "./lib/webapp/popstateLifecycle.js";
  import {
    applyThemeDocumentEffects,
    closeDisabledEmailAuthDialogs,
    syncShellBillingSelection,
    syncShellEmailAvatar,
  } from "./lib/webapp/shellEffects.js";

  /** Used-traffic percent from which top-up modals and CTAs unlock in the web app home screen */
  const TRAFFIC_TOPUP_UNLOCK_PERCENT = 80;
  const TELEGRAM_NOTIFICATIONS_RESUME_REFRESH_COOLDOWN_MS = 1500;
  import { createBillingActions } from "./lib/webapp/billingActions";
  import { invalidateWebappTariffOptionCaches } from "./lib/webapp/billingOptionCache.js";
  import { CSRF_COOKIE_NAME, readCookie } from "./lib/webapp/session.js";
  import { createTelegramRuntime, type TelegramWebApp } from "./lib/webapp/telegramRuntime.js";

  type AnyRecord = Record<string, any>;
  export let mockRuntime: AnyRecord | null = null;

  const FALLBACK_BRAND_TITLE = "Subscription";
  const EMPTY_MOCK: AnyRecord = {
    config: {
      title: FALLBACK_BRAND_TITLE,
      primaryColor: "#00fe7a",
      apiBase: "/api",
      language: "ru",
      languages: [],
    },
    data: {
      plans: [],
      payment_methods: [],
      subscription: {},
      settings: {},
      referral: {},
      themes_catalog: { default_theme: "dark", themes: [] },
    },
  };
  const MOCK_SOURCE: AnyRecord = mockRuntime?.source || EMPTY_MOCK;
  const previewBoardComponent = mockRuntime?.PreviewBoard || null;
  const isDocsDemo = mockRuntime?.docsDemo === true;
  const routePrefix = isDocsDemo ? "/demo/runtime" : "";
  let docsDemoParentRouteConsumed = false;
  const query = new URLSearchParams(window.location.search);
  const isAppLaunchRoute = isExternalAppLaunchPath(window.location.pathname);
  mockRuntime?.applyPreviewMock?.(query.get("mock"));
  const isPreviewBoard = Boolean(previewBoardComponent) && query.get("preview") === "all";
  const injectedConfig = readJsonScript("webapp-config") as AnyRecord | null;
  const injectedI18n = readJsonScript("i18n") as AnyRecord | null;
  const isLocalShell =
    window.location.protocol === "file:" ||
    ["", "localhost", "127.0.0.1"].includes(window.location.hostname);
  const MOCK: AnyRecord | null =
    mockRuntime?.mockApi && !injectedConfig && (isLocalShell || isDocsDemo) ? MOCK_SOURCE : null;
  const CFG: AnyRecord = {
    ...MOCK_SOURCE.config,
    ...(MOCK ? MOCK.config : {}),
    ...(injectedConfig || {}),
  };
  const docsDemoRouter = createDocsDemoRouter({
    currentSearchParams,
    getParentRouteConsumed: () => docsDemoParentRouteConsumed,
    isDocsDemo,
    isMockEnabled: () => Boolean(MOCK),
    routePrefix,
  });
  const cleanDocsDemoRouteQuery = docsDemoRouter.cleanRouteQuery;
  const docsDemoParentSearchParams = docsDemoRouter.parentSearchParams;
  const initialAdminSectionFromLocation = docsDemoRouter.initialAdminSectionFromLocation;
  const routePathnameFromLocation = docsDemoRouter.routePathnameFromLocation;
  const syncAppSectionPath = docsDemoRouter.syncAppSectionPath;
  const themePreviewKey = String(CFG.themePreviewKey || query.get("theme_preview") || "").trim();
  const themePreviewDraft = readThemePreviewDraft(themePreviewKey);
  const I18N: AnyRecord = injectedI18n || {};
  let telegramSdkStatus = "idle";
  let telegramMiniAppInitData = "";

  let mode = isAppLaunchRoute ? "appLaunch" : isPreviewBoard ? "preview" : "loading";
  let activeTab = "home";
  let screen = "home";
  let emailLoginDeeplinkConsumed = false;
  let data: AnyRecord | null = isPreviewBoard ? structuredCloneSafe(MOCK_SOURCE.data) : null;
  let appLaunchTarget = isAppLaunchRoute ? readExternalAppLaunchTarget() : "";
  let publicInstallSubscription: AnyRecord | null = null;
  let publicInstallToken = "";
  let autoRenewBusy = false;
  let activationSuccessDialogOpen = false;
  let activationSuccessUseInstallGuides = false;
  let telegramNotificationsBotOpenedAt = 0;
  let telegramNotificationsResumeRefreshBusy = false;
  let telegramNotificationsResumeLastCheckAt = 0;
  let languageMenuOpen = false;
  let languageClickGuard = false;
  let languageClickGuardArmed = false;
  let guestLanguage = "";
  let emailAvatarUrl = "";
  let token = MOCK ? "local-preview" : "";
  let csrfToken = MOCK ? "" : readCookie(CSRF_COOKIE_NAME) || "";
  let adminBundleApi: AnyRecord | null = null;
  let adminBundleError = "";
  let adminMountTarget: HTMLElement | null = null;
  let adminPanelProps: AnyRecord = {};
  let adminActiveSection = "stats";
  let tg: TelegramWebApp | null = null;
  let currentLang = String(CFG.language || "ru");
  let demoAuthLogin: unknown = false;
  let installGuidesEnabled = false;
  let isAdmin = false;
  let subscription: AnyRecord = {};
  let telegramNotificationsNeedPrompt = false;
  let telegramOAuthClientId = 0;
  let user: AnyRecord = {};
  let appActions: AppActionRuntime;
  const telegramRuntime = createTelegramRuntime<TelegramWebApp | null>({
    scriptUrl: TELEGRAM_WEBAPP_SCRIPT_URL,
    bootTimeoutMs: TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    actionTimeoutMs: TELEGRAM_SDK_ACTION_TIMEOUT_MS,
    miniAppAuthTimeoutMs: TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS,
    setInitData: (initData) => {
      telegramMiniAppInitData = initData || "";
    },
    setStatus: (status) => {
      telegramSdkStatus = status;
    },
    setTelegram: (value) => {
      tg = value;
    },
  });
  const telegramSdk = telegramRuntime.telegramSdk;
  const readTelegramMiniAppInitDataFromLocation = telegramRuntime.readInitDataFromLocation;
  const hasTelegramLaunchParams = telegramRuntime.hasLaunchParams;
  const loadTelegramSdk = telegramRuntime.load;
  const { openAppLaunchTarget, openAppLink, openExternalLink, refreshAppLaunchTarget } =
    createExternalLinkRuntime({
      assignLocation: (url) => window.location.assign(url),
      getCurrentLang: () => currentLang,
      getTelegram: () => tg,
      hasTelegramLaunchParams,
      refreshTelegram: telegramRuntime.refreshTelegram,
      setAppLaunchTarget: (target) => {
        appLaunchTarget = target;
      },
      setTelegram: (value) => {
        tg = value;
      },
    });
  const i18n = createI18n({
    messages: I18N,
    defaultLang: "ru",
    getLang: () => user?.language_code || guestLanguage || CFG.language || "ru",
  } as any);
  const normalizeLangCode = i18n.normalizeLangCode;
  const t = i18n.t;
  const termUnitLabel = i18n.termUnitLabel;
  const languageName = i18n.languageName;
  const adminRuntime = createAdminRuntime({
    fetchI18nScope: async (scope) => {
      const apiBase = String(CFG.apiBase || "/api").replace(/\/+$/, "");
      const response = await fetch(`${apiBase}/i18n?scope=${encodeURIComponent(scope)}`, {
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
    getShouldPrefetch: () => isAdmin && screen !== "admin",
    invalidateTariffOptionCaches: () => {
      invalidateWebappTariffOptionCaches(billingStore);
    },
    loadData: (options) => loadData(options as AppLoadDataOptions),
    mergeMessages: (messages) => {
      i18n.mergeMessages((messages || {}) as AnyRecord);
    },
    reloadWindow: () => {
      if (typeof window !== "undefined") window.location.reload();
    },
    resetInstallGuides: () => {
      installGuidesStore.reset();
    },
    setBundleState: (api, error) => {
      adminBundleApi = api as AnyRecord | null;
      adminBundleError = error;
    },
  });
  guestLanguage = normalizeLangCode(CFG.language || "ru");
  const { clearLanguageClickGuard, setLanguageMenuOpen, syncBodyScrollLock, updateGuestLanguage } =
    createUiChrome({
      normalizeLangCode,
      getCurrentLang: () => currentLang,
      setGuestLanguage: (value) => {
        guestLanguage = value;
      },
      setLanguageMenuOpenState: (value) => {
        languageMenuOpen = value;
      },
      setLanguageClickGuard: (value) => {
        languageClickGuard = value;
      },
      setLanguageClickGuardArmed: (value) => {
        languageClickGuardArmed = value;
      },
    });
  const { clearManualLogoutFlag, clearToken, isManuallyLoggedOut, markManualLogout, setToken } =
    createWebappSessionActions({
      csrfCookieName: CSRF_COOKIE_NAME,
      isMock: () => Boolean(MOCK),
      manualLogoutFlagKey: MANUAL_LOGOUT_FLAG_KEY,
      setCsrfToken: (nextToken) => {
        csrfToken = nextToken;
      },
      setToken: (nextToken) => {
        token = nextToken;
      },
    });
  const dataClient = createWebappDataClient({
    apiBase: CFG.apiBase,
    csrfCookieName: CSRF_COOKIE_NAME,
    getCsrfToken: () => csrfToken,
    onUnauthorized: () => {
      clearToken();
      showLogin();
    },
    mockApi:
      MOCK && mockRuntime?.mockApi
        ? (path, options, context) => mockRuntime.mockApi(path, options, context)
        : null,
    getMockContext: () => ({ currentLang, normalizeLangCode, clone: structuredCloneSafe }),
  });
  const api = dataClient.api;
  const publicApi = dataClient.publicApi;
  const billing = createBillingActions({
    api,
  });
  const emailAvatarSync = createEmailAvatarSync();
  const {
    closeActivationSuccessDialog,
    handleSubscriptionActivated,
    hasPendingActivationHandoff,
    maybeShowActivationSuccessDialog,
    refreshPendingActivationOnResume,
    rememberActivationPending,
    startPendingActivationWatch,
    stopPendingActivationWatch,
  } = createWebappActivationContext({
    billing,
    loadData,
    getData: () => data,
    getSubscription: () => subscription,
    getMode: () => mode,
    getScreen: () => screen,
    getActivationSuccessDialogOpen: () => activationSuccessDialogOpen,
    getActivationSuccessUseInstallGuides: () => activationSuccessUseInstallGuides,
    getPaymentModalOpen: () => paymentModalOpen,
    getTopupModalOpen: () => topupModalOpen,
    getDeviceTopupModalOpen: () => deviceTopupModalOpen,
    getChangeModalOpen: () => changeModalOpen,
    getChangeConfirmOpen: () => changeConfirmOpen,
    setActivationSuccessDialogOpen: (open) => {
      activationSuccessDialogOpen = open;
    },
    setActivationSuccessUseInstallGuides: (useInstallGuides) => {
      activationSuccessUseInstallGuides = useInstallGuides;
    },
    setActiveTab: (tab) => {
      activeTab = tab;
    },
    setScreen: (nextScreen) => {
      screen = nextScreen;
    },
    canUseInstallGuides,
    closePaymentModal: () => billingStore.closePaymentModal(),
    loadInstallGuides: (force) => installGuidesStore.load(force),
    openActivationConnectLink: () => appActions.openActivationConnectLink(),
    syncAppSectionPath,
  });
  const authStore = createAuthStore({
    publicApi,
    setToken,
    loadData,
    telegramSdk: telegramSdk as any,
    getTg: () => tg,
    t,
    currentLang: () => currentLang,
  });
  const demoAuth = createDemoAuth({
    authStore,
    getCurrentSearchParams: currentSearchParams,
    getMockSource: () => MOCK_SOURCE,
    getParentSearchParams: docsDemoParentSearchParams,
    isMockEnabled: () => Boolean(MOCK),
  });
  const billingStore = createBillingStore({
    billing,
    loadData,
    t,
    showToast,
    openExternalLink,
    onSubscriptionActivationPending: rememberActivationPending,
    onSubscriptionActivated: handleSubscriptionActivated,
    tg: tg as any,
    getTg: () => tg || telegramSdk.refresh(),
    telegramSdk: telegramSdk as any,
  });
  const { applyPostLoadBillingDeeplinks } = createBillingDeeplinkEffects({
    billingStore,
    readRenewalDeeplink,
    setHomeRoute: () => {
      activeTab = "home";
      screen = "home";
      syncAppSectionPath("home", true);
    },
    stripRenewalLoginQueryFromUrl,
    stripTopupQueryFromUrl,
  });
  const {
    devicesStore,
    supportStore,
    installGuidesStore,
    loadSectionData,
    hydrateSupportUnread,
    syncLoadedRoute,
  } = createWebappSectionContext({
    api,
    t,
    showToast,
    routePrefix,
    cleanDocsDemoRouteQuery,
    syncAppSectionPath,
  });
  const actionsStore = createActionsStore({
    api,
    t,
    showToast,
    loadData,
    maybeShowActivationSuccessDialog,
  });
  const authRuntime = createAuthRuntime({
    authStore,
    cleanDocsDemoRouteQuery,
    getEmailLoginDeeplinkConsumed: () => emailLoginDeeplinkConsumed,
    isDocsDemo,
    routePathnameFromLocation,
    routePrefix,
    setActiveTab: (tab) => {
      activeTab = tab;
    },
    setEmailLoginDeeplinkConsumed: (consumed) => {
      emailLoginDeeplinkConsumed = consumed;
    },
    setMode: (nextMode) => {
      mode = nextMode;
    },
    setScreen: (nextScreen) => {
      screen = nextScreen;
    },
    tick,
  });
  const { setPasswordLoginMode, showLogin, submitEmailOnEnter } = authRuntime;
  const bootRuntime = createAppBootRuntime({
    loadPublicInstall: (shareToken) => appActions.loadPublicInstall(shareToken),
    isDemoAuthMock: () => Boolean(MOCK) && demoAuth.isDemoAuthMock(),
    prepareDemoAuthState: () => demoAuth.prepareAuthState(),
    mock: MOCK,
    getTelegram: () => tg,
    setMode: (next) => {
      mode = next;
    },
    hasTelegramLaunchParams,
    loadTelegramSdk,
    loadData,
    showLogin,
    clearToken,
    clearManualLogoutFlag,
    isManuallyLoggedOut,
    hasEmailCodeLoginDeeplink,
    finalizeMagicLogin: (loginToken) => authStore.finalizeMagicLogin(loginToken),
    finalizeTelegramAuth: (authData, source) => authStore.finalizeTelegramAuth(authData, source),
    setAuthStatus: (message, isError = false) => authStore.setAuthStatus(message, isError),
    t,
    getInitDataForBoot: () =>
      telegramMiniAppInitData || tg?.initData || readTelegramMiniAppInitDataFromLocation(),
    getToken: () => token,
    getCsrfToken: () => csrfToken,
    getMode: () => mode,
    getScreen: () => screen,
    continueTelegramLinkPendingAction: () => appActions.continueTelegramLinkPendingAction(),
    hasPendingActivationHandoff,
    maybeShowActivationSuccessDialog,
    startPendingActivationWatch,
    telegramNotificationsResumeCooldownMs: TELEGRAM_NOTIFICATIONS_RESUME_REFRESH_COOLDOWN_MS,
    readTelegramNotificationsResumeState: () => ({
      botOpenedAt: telegramNotificationsBotOpenedAt,
      lastCheckAt: telegramNotificationsResumeLastCheckAt,
      mode,
      needPrompt: telegramNotificationsNeedPrompt,
      refreshBusy: telegramNotificationsResumeRefreshBusy,
    }),
    setTelegramNotificationsBotOpenedAt: (openedAt) => {
      telegramNotificationsBotOpenedAt = openedAt;
    },
    setTelegramNotificationsResumeLastCheckAt: (checkedAt) => {
      telegramNotificationsResumeLastCheckAt = checkedAt;
    },
    setTelegramNotificationsResumeRefreshBusy: (busy) => {
      telegramNotificationsResumeRefreshBusy = busy;
    },
  });
  const resumeLifecycle = createResumeLifecycle({
    clearLoginTooltip: () => {
      authStore.update((state) => ({ ...state, loginEmailTooltipOpen: false }));
    },
    getMode: () => mode,
    refreshPendingActivationOnResume: () => {
      void refreshPendingActivationOnResume();
    },
    refreshTelegramNotificationsOnResume: () => {
      void bootRuntime.refreshTelegramNotificationsOnResume();
    },
  });
  const accountStore = createAccountStore({
    api,
    publicApi,
    setToken,
    loadData,
    t,
    showToast,
    clearToken,
    markManualLogout,
    showLogin,
    telegramSdk: telegramSdk as any,
    getTg: () => tg,
    getCurrentUser: () => data?.user || user || {},
    getTelegramMiniAppInitData: () =>
      telegramMiniAppInitData || tg?.initData || readTelegramMiniAppInitDataFromLocation(),
    isDemoAuthLogin: () => Boolean(demoAuthLogin),
    getDemoTelegramAuthPayload: () => demoAuth.telegramAuthPayload(),
    telegramOAuthClientId: () => telegramOAuthClientId,
    currentLang: () => currentLang,
    normalizeLangCode,
    updateLocalData: (updatedLanguage) => {
      if (!data?.user) return;
      data = { ...data, user: { ...data.user, language_code: updatedLanguage } };
    },
    activateTrial: () => actionsStore.activateTrial(),
    claimReferralWelcomeBonus: () => actionsStore.claimReferralWelcomeBonus(),
  });

  setContext("authStore", authStore);
  setContext("billingStore", billingStore);
  setContext("devicesStore", devicesStore);
  setContext("supportStore", supportStore);
  setContext("installGuidesStore", installGuidesStore);
  setContext("actionsStore", actionsStore);
  setContext("accountStore", accountStore);

  let shellView: AppShellView;
  $: ({ authStatus, authBusy, telegramLoginBusy } = $authStore);
  $: ({
    paymentModalOpen,
    selectedTariffKey,
    selectedPlan,
    topupModalOpen,
    topupKind,
    deviceTopupModalOpen,
    changeModalOpen,
    changeConfirmOpen,
  } = $billingStore);
  $: ({ linkEmailOpen, setPasswordOpen, languageBusy } = $accountStore);
  $: ({ trialActivationResult } = $actionsStore);

  $: user = (data?.user || {}) as AnyRecord;
  $: isAdmin = Boolean(user?.is_admin);

  $: shellView = computeAppShellView({
    authBusy,
    authStatus,
    cfg: CFG,
    data,
    emailAvatarUrl,
    fallbackBrandTitle: FALLBACK_BRAND_TITLE,
    guestLanguage,
    hasTelegramLaunchParams,
    i18nMessages: I18N,
    isDemoAuthMock: () => demoAuth.isDemoAuthMock(),
    languageName,
    mockData: MOCK_SOURCE.data,
    mockEnabled: Boolean(MOCK),
    normalizeLangCode,
    readTelegramMiniAppInitDataFromLocation,
    screen,
    selectedTariffKey,
    telegramLoginBusy,
    telegramSdkStatus,
    tg,
    themePreviewDraft,
    themePreviewKey,
    topupUnlockPercent: TRAFFIC_TOPUP_UNLOCK_PERCENT,
    t,
  });

  $: ({
    accountView: { telegramNotificationsNeedPrompt, telegramNotificationsStartLink },
    appDataView: {
      appSettings,
      brand,
      brandTitle,
      devicesEnabled,
      emailAuthEnabled,
      faviconBrand,
      installGuidesEnabled,
      methods,
      plans,
      subscription,
      supportEnabled,
    },
    billingView: { selectedTariffPlans, singleTariffMode, tariffCatalog, tariffMode, trafficMode },
    currentLang,
    demoAuthLogin,
    languageView: { languageOptions },
    telegramMiniAppInitData,
    telegramOAuthClientId,
    themeView: { effectiveThemeEntry, resolvedThemeKey, shellStyle, shellThemeCssHref, toastTheme },
  } = shellView);
  $: supportStore.setActive(Boolean(mode === "app" && screen === "support" && supportEnabled));
  $: applyThemeDocumentEffects(effectiveThemeEntry);
  $: syncThemeGoogleFonts(effectiveThemeEntry);
  $: if (screen === "admin" && !isAdmin) {
    screen = "settings";
    activeTab = "settings";
  }
  $: applyFavicon(faviconBrand);
  $: applyDocumentTitle(brandTitle);
  $: syncBodyScrollLock(
    paymentModalOpen ||
      changeModalOpen ||
      changeConfirmOpen ||
      topupModalOpen ||
      deviceTopupModalOpen ||
      (emailAuthEnabled && linkEmailOpen) ||
      (emailAuthEnabled && setPasswordOpen)
  );
  $: closeDisabledEmailAuthDialogs({
    closeLinkEmailDialog: () => accountStore.closeLinkEmailDialog(),
    closeSetPasswordDialog: () => accountStore.closeSetPasswordDialog(),
    emailAuthEnabled,
    linkEmailOpen,
    setPasswordOpen,
  });
  $: syncShellBillingSelection({
    applyPatch: (patch) => billingStore.update((s) => ({ ...s, ...patch })),
    input: {
      methods,
      plans,
      selectedTariffPlans,
      singleTariffMode,
      tariffCatalog,
      tariffMode,
    },
    state: {
      paymentStep: $billingStore.paymentStep,
      selectedMethod: $billingStore.selectedMethod,
      selectedPlan,
      selectedTariffKey,
    },
  });
  $: syncShellEmailAvatar({
    email: user?.email,
    emailAvatarSync,
    setEmailAvatarUrl: (url) => {
      emailAvatarUrl = url;
    },
  });

  function canUseInstallGuides() {
    return canUseSubscriptionInstallGuides({
      installGuidesEnabled,
      subscription,
    });
  }

  const popstateLifecycle = createPopstateLifecycle({
    adminRuntime,
    boot: bootRuntime.boot,
    canUseInstallGuides,
    currentSearchParams,
    getDevicesEnabled: () => devicesEnabled,
    getFallbackAdminSection: initialAdminSectionFromLocation,
    getIsAdmin: () => isAdmin,
    getMode: () => mode,
    getScreen: () => screen,
    getSupportEnabled: () => supportEnabled,
    isDocsDemo,
    loadDevices: () => {
      devicesStore.loadDevices(devicesEnabled);
    },
    loadInstallGuides: () => {
      installGuidesStore.load();
    },
    loadPublicInstall: (shareToken) => appActions.loadPublicInstall(shareToken),
    loadSupport: () => {
      supportStore.loadList();
    },
    routePathnameFromLocation,
    routePrefix,
    setActiveTab: (tab) => {
      activeTab = tab;
    },
    setAdminActiveSection: (section) => {
      adminActiveSection = section;
    },
    setPasswordLoginMode,
    setScreen: (nextScreen) => {
      screen = nextScreen;
    },
    showAdminUnavailable: () => {
      showToast(t("wa_unavailable"));
    },
    startSupportPolling: () => {
      supportStore.startPolling({ includeList: true });
    },
    syncAppSectionPath,
  });

  const appLoadExecutor = createAppLoadExecutor({
    adminRuntime,
    applyPostLoadBillingDeeplinks,
    currentSearchParams,
    dataClientLoadData: (options) => dataClient.loadData(options) as Promise<AnyRecord>,
    getModalState: () => ({
      changeModalOpen,
      deviceTopupModalOpen,
      topupKind,
      topupModalOpen,
    }),
    getRouteState: () => ({
      activeTab,
      adminActiveSection,
      screen,
    }),
    getWindowSearch: () => window.location.search,
    hydrateSupportUnread,
    initialAdminSectionFromLocation,
    isDocsDemo: () => isDocsDemo,
    isMock: () => Boolean(MOCK),
    loadDeviceTopupOptions: () => billingStore.loadDeviceTopupOptions(),
    loadInstallGuides: () => installGuidesStore.load(),
    loadSectionData,
    loadTariffChangeOptions: () => billingStore.loadTariffChangeOptions(),
    loadTopupOptions: (kind) => billingStore.loadTopupOptions(kind),
    resetBillingSelection: (defaultMethod) => {
      billingStore.update((s) => ({
        ...s,
        selectedPlan: null,
        selectedTariffKey: "",
        paymentStep: "tariff",
        renewHwidDevices: true,
        selectedMethod: defaultMethod,
      }));
    },
    routePathnameFromLocation,
    routePrefix,
    setData: (payload) => {
      data = payload;
    },
    setDocsDemoParentRouteConsumed: () => {
      docsDemoParentRouteConsumed = true;
    },
    setRouteState: (patch) => {
      if (patch.activeTab !== undefined) activeTab = patch.activeTab;
      if (patch.adminActiveSection !== undefined) adminActiveSection = patch.adminActiveSection;
      if (patch.mode !== undefined) mode = patch.mode;
      if (patch.screen !== undefined) screen = patch.screen;
    },
    showAdminUnavailable: () => {
      showToast(t("wa_unavailable"));
    },
    syncLoadedRoute,
  });

  onMount(() => {
    if (isPreviewBoard) return;
    if (isAppLaunchRoute) return;
    const onPopState = popstateLifecycle.handlePopstate;
    window.addEventListener("popstate", onPopState);
    const cleanupResumeLifecycle = resumeLifecycle.mount();
    bootRuntime.boot();
    return () => {
      window.removeEventListener("popstate", onPopState);
      cleanupResumeLifecycle();
      authStore.stopTelegramLoginWatchdog();
      authStore.clearCooldownTimer();
      accountStore.clearLinkEmailResendTimer();
      accountStore.clearSetPasswordResendTimer();
      supportStore.closePolling();
      stopPendingActivationWatch();
      clearLanguageClickGuard();
      adminRuntime.cancelAdminAssetsPrefetch();
      syncBodyScrollLock(false);
      adminRuntime.destroyAdminMount();
    };
  });

  appActions = createAppActionRuntime({
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
    externalLinkActions: {
      openAppLaunchTarget,
      openAppLink,
      openExternalLink,
      refreshAppLaunchTarget,
    },
    getAdminActiveSection: () => adminActiveSection,
    getAppSettings: () => appSettings,
    getAutoRenewBusy: () => autoRenewBusy,
    getDevicesEnabled: () => devicesEnabled,
    getDemoTelegramAuthPayload: () => demoAuth.telegramAuthPayload(),
    getEmailAuthEnabled: () => emailAuthEnabled,
    getIsAdmin: () => isAdmin,
    getIsFileProtocol: () => window.location.protocol === "file:",
    getMethods: () => methods,
    getOrigin: () => (typeof window !== "undefined" ? window.location.origin : ""),
    getPlans: () => plans,
    getPreloadHost: () => (typeof window !== "undefined" ? (window as unknown as AnyRecord) : null),
    getPublicInstallSubscription: () => publicInstallSubscription,
    getRoutePathname: routePathnameFromLocation,
    getScreen: () => screen,
    getSelectedPlan: () => selectedPlan,
    getSelectedTariffPlans: () => selectedTariffPlans,
    getSingleTariffMode: () => singleTariffMode,
    getSubscription: () => subscription,
    getSupportEnabled: () => supportEnabled,
    getTariffCatalog: () => tariffCatalog,
    getTariffMode: () => tariffMode,
    getTelegram: () => tg,
    getTelegramMiniAppInitData: () => telegramMiniAppInitData,
    getTelegramNotificationsStartLink: () => telegramNotificationsStartLink,
    getTelegramOAuthClientId: () => telegramOAuthClientId,
    getTrafficMode: () => trafficMode,
    getTrialActivationResult: () => trialActivationResult,
    installGuidesStore,
    isDemoAuthLogin: () => Boolean(demoAuthLogin),
    loadData,
    markTelegramNotificationsBotOpened: (openedAt) => {
      telegramNotificationsBotOpenedAt = openedAt;
    },
    refreshTelegram: telegramRuntime.refreshTelegram,
    routePrefix,
    setActiveTab: (tab) => {
      activeTab = tab;
    },
    setAdminActiveSection: (section) => {
      adminActiveSection = section;
    },
    setAutoRenewBusy: (busy) => {
      autoRenewBusy = busy;
    },
    setMode: (nextMode) => {
      mode = nextMode;
    },
    setPublicInstallSubscription: (subscription) => {
      publicInstallSubscription = subscription;
    },
    setPublicInstallToken: (nextToken) => {
      publicInstallToken = nextToken;
    },
    setScreen: (nextScreen) => {
      screen = nextScreen;
    },
    setTelegram: (value) => {
      tg = value;
    },
    showToast,
    supportStore,
    syncAppSectionPath,
    t,
  });

  $: adminPanelProps = buildAdminPanelProps({
    adminActiveSection,
    api,
    appFaviconUrl: CFG.faviconUrl,
    appFaviconUseCustom: CFG.faviconUseCustom,
    appRepositoryUrl: CFG.appRepositoryUrl,
    appVersion: CFG.appVersion,
    brand,
    brandTitle,
    currentLang,
    fallbackAdminSection: initialAdminSectionFromLocation(),
    languageBusy,
    languageOptions,
    onClose: appActions.closeAdminPanel,
    onLanguageChange: accountStore.updateAccountLanguage,
    onSectionChange: appActions.handleAdminSectionChange,
    onSettingsSaved: adminRuntime.handleAdminPersistedSaved,
    onTariffsSaved: adminRuntime.handleAdminPersistedSaved,
    onThemesSaved: adminRuntime.handleAdminPersistedSaved,
    onToast: (text: string) => showToast(text),
    onTranslationsSaved: adminRuntime.handleAdminTranslationsSaved,
    pathname: routePathnameFromLocation(),
    routePrefix,
    screen,
    t,
  });

  $: {
    adminRuntime.syncAdminMount({
      props: adminPanelProps,
      shouldMount: Boolean(screen === "admin" && isAdmin && adminBundleApi && adminMountTarget),
      target: adminMountTarget,
    });
  }

  async function loadData(options: AppLoadDataOptions = {}) {
    return appLoadExecutor.loadData(options) as Promise<AnyRecord>;
  }

  function showToast(message: unknown) {
    const text = String(message ?? "").trim();
    if (!text) return;
    sonnerToast(text, { duration: 2400 });
  }
</script>

<svelte:head>
  <title>{brandTitle}</title>
  {#if shellThemeCssHref}
    <link rel="stylesheet" href={shellThemeCssHref} data-theme-css={resolvedThemeKey} />
  {/if}
</svelte:head>

<Tooltip.Provider>
  <Toaster
    position="bottom-right"
    theme={toastTheme}
    duration={2400}
    visibleToasts={3}
    gap={10}
    offset="16px"
    style={shellStyle}
    toastOptions={{ class: "app-toast", unstyled: true }}
  />
  {#key currentLang}
    {#if isPreviewBoard}
      {@const PreviewBoardComponent = previewBoardComponent}
      <PreviewBoardComponent config={CFG} mockData={MOCK_SOURCE.data} />
    {:else}
      <AppModeContent
        {accountStore}
        {shellView}
        {appActions}
        {activationSuccessDialogOpen}
        {activationSuccessUseInstallGuides}
        {activeTab}
        {adminBundleApi}
        {adminBundleError}
        bind:adminMountTarget
        {appLaunchTarget}
        {actionsStore}
        {authStore}
        {autoRenewBusy}
        {billingStore}
        cfg={CFG}
        {closeActivationSuccessDialog}
        {devicesStore}
        {languageBusy}
        {languageClickGuard}
        {languageClickGuardArmed}
        bind:languageMenuOpen
        {mode}
        {publicInstallSubscription}
        {publicInstallToken}
        bind:screen
        {setLanguageMenuOpen}
        {setPasswordLoginMode}
        {submitEmailOnEnter}
        {supportStore}
        {t}
        telegramPlatform={tg?.platform || ""}
        {termUnitLabel}
        {updateGuestLanguage}
      />
    {/if}
  {/key}
</Tooltip.Provider>
