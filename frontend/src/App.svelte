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
  import { refreshTelegramNotificationsAfterResume } from "./lib/webapp/telegramNotificationsResume.js";
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
  import {
    type BillingPlan,
    type PaymentMethod,
    type TariffCatalogEntry,
  } from "./lib/webapp/tariffs.js";
  import { createBillingDeeplinkEffects } from "./lib/webapp/billingDeeplinkEffects.js";
  import { createWebappSectionContext } from "./lib/webapp/webappSectionContext";
  import { readThemePreviewDraft, syncThemeGoogleFonts } from "./lib/webapp/themeStyle.js";
  import { computeThemeView } from "./lib/webapp/themeView.js";
  import { computeBillingView } from "./lib/webapp/billingView.js";
  import { computeLanguageView, type LanguageOption } from "./lib/webapp/languageView.js";
  import { computeTelegramLoginView } from "./lib/webapp/telegramLoginView.js";
  import { computeAccountView } from "./lib/webapp/accountView.js";
  import { computeAppDataView } from "./lib/webapp/appDataView.js";
  import { createWebappNavigation } from "./lib/webapp/webappNavigation.js";
  import { createBillingModalActions } from "./lib/webapp/billingModalActions.js";
  import { createAutoRenewAction } from "./lib/webapp/autoRenewAction.js";
  import { createAdminPanelActions } from "./lib/webapp/adminPanelActions.js";
  import { createWebappSessionActions } from "./lib/webapp/webappSessionActions.js";
  import { createAccountUiActions } from "./lib/webapp/accountUiActions.js";
  import { createConnectActions } from "./lib/webapp/connectActions.js";
  import { createInstallRuntime } from "./lib/webapp/installRuntime.js";
  import { createClipboardActions } from "./lib/webapp/clipboardActions.js";
  import { createPromoTrialActions } from "./lib/webapp/promoTrialActions.js";
  import { createTariffActions } from "./lib/webapp/tariffActions.js";
  import { createPrimaryPayActionLabel } from "./lib/webapp/primaryPayActionLabel.js";
  import { createTelegramLoginActions } from "./lib/webapp/telegramLoginActions.js";
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
  import { runWebappBoot } from "./lib/webapp/webappBoot.js";
  import { CSRF_COOKIE_NAME, readCookie } from "./lib/webapp/session.js";
  import { createTelegramRuntime, type TelegramWebApp } from "./lib/webapp/telegramRuntime.js";
  import { publicInstallTokenFromPath } from "./lib/webapp/routes.js";

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
    openActivationConnectLink: () => openActivationConnectLink(),
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
  const resumeLifecycle = createResumeLifecycle({
    clearLoginTooltip: () => {
      loginEmailTooltipOpen = false;
    },
    getMode: () => mode,
    refreshPendingActivationOnResume: () => {
      void refreshPendingActivationOnResume();
    },
    refreshTelegramNotificationsOnResume: () => {
      void refreshTelegramNotificationsOnResume();
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

  $: ({
    authStatus,
    authIsError,
    authBusy,
    telegramLoginBusy,
    loginEmailFieldError,
    loginEmailTooltipOpen,
    passwordLoginFallback,
    passwordLoginMode,
    authResendCooldown,
    pendingEmail,
  } = $authStore);
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
  $: ({ devicesData, devicesLoaded, devicesBusy, devicesStatus, devicesIsError, devicesErrorCode } =
    $devicesStore);
  $: ({
    unreadCount: supportUnreadCount,
    unreadLoading: supportUnreadLoading,
    unreadLoaded: supportUnreadLoaded,
  } = $supportStore);
  $: ({ linkEmailOpen, linkEmailBusy, linkTelegramBusy, setPasswordOpen, languageBusy } =
    $accountStore);
  $: ({
    promoCode,
    promoBusy,
    promoStatus,
    promoIsError,
    promoFieldError,
    trialBusy,
    trialActivationResult,
    trialActivationError,
  } = $actionsStore);

  let brandTitle = FALLBACK_BRAND_TITLE;
  let brand: AnyRecord = {};
  let faviconBrand: AnyRecord = {};
  let plans: AnyRecord[] = [];
  let methods: PaymentMethod[] = [];
  let appSettings: AnyRecord = {};
  let emailAuthEnabled = true;
  let subscriptionPurchaseDescription = "";
  let devicesEnabled = false;
  let supportEnabled = true;
  let installGuidesEnabled = false;
  let subscription: AnyRecord = {};
  let referral: AnyRecord = {};
  let referralBonusDetails: AnyRecord[] = [];
  let referralWelcomeBonusDays = 0;
  let referralOneBonusPerReferee = false;
  $: {
    const appDataView = computeAppDataView({
      cfg: CFG,
      data,
      fallbackBrandTitle: FALLBACK_BRAND_TITLE,
      mockData: MOCK_SOURCE.data,
    });
    brandTitle = appDataView.brandTitle;
    brand = appDataView.brand;
    faviconBrand = appDataView.faviconBrand;
    plans = appDataView.plans;
    methods = appDataView.methods;
    appSettings = appDataView.appSettings;
    emailAuthEnabled = appDataView.emailAuthEnabled;
    subscriptionPurchaseDescription = appDataView.subscriptionPurchaseDescription;
    devicesEnabled = appDataView.devicesEnabled;
    supportEnabled = appDataView.supportEnabled;
    installGuidesEnabled = appDataView.installGuidesEnabled;
    subscription = appDataView.subscription;
    referral = appDataView.referral;
    referralBonusDetails = appDataView.referralBonusDetails;
    referralWelcomeBonusDays = appDataView.referralWelcomeBonusDays;
    referralOneBonusPerReferee = appDataView.referralOneBonusPerReferee;
  }
  $: supportStore.setActive(Boolean(mode === "app" && screen === "support" && supportEnabled));
  let trafficMode = false;
  let tariffMode = false;
  let tariffCatalog: TariffCatalogEntry[] = [];
  let singleTariffMode = false;
  let hasMultipleTariffs = false;
  let selectedTariff: TariffCatalogEntry | null = null;
  let selectedTariffPlans: BillingPlan[] = [];
  let hasActiveTariffSubscription = false;
  let canChangeTariff = false;
  let currentTariffName = "";
  let regularTrafficTopupUnlocked = false;
  let premiumTrafficTopupUnlocked = false;
  let regularTrafficTopupBarClickable = false;
  let premiumTrafficTopupBarClickable = false;
  $: {
    const billingView = computeBillingView({
      appSettings,
      plans,
      selectedTariffKey,
      subscription,
      topupUnlockPercent: TRAFFIC_TOPUP_UNLOCK_PERCENT,
    });
    trafficMode = billingView.trafficMode;
    tariffMode = billingView.tariffMode;
    tariffCatalog = billingView.tariffCatalog;
    singleTariffMode = billingView.singleTariffMode;
    hasMultipleTariffs = billingView.hasMultipleTariffs;
    selectedTariff = billingView.selectedTariff;
    selectedTariffPlans = billingView.selectedTariffPlans;
    hasActiveTariffSubscription = billingView.hasActiveTariffSubscription;
    canChangeTariff = billingView.canChangeTariff;
    currentTariffName = billingView.currentTariffName;
    regularTrafficTopupUnlocked = billingView.regularTrafficTopupUnlocked;
    premiumTrafficTopupUnlocked = billingView.premiumTrafficTopupUnlocked;
    regularTrafficTopupBarClickable = billingView.regularTrafficTopupBarClickable;
    premiumTrafficTopupBarClickable = billingView.premiumTrafficTopupBarClickable;
  }
  $: user = (data?.user || {}) as AnyRecord;
  let resolvedThemeKey = "";
  let effectiveThemeEntry: AnyRecord | null = null;
  let shellStyle = "";
  let shellToneClass = "";
  let shellThemeClass = "";
  let shellThemeCssHref: string | null = null;
  let toastTheme: "dark" | "light" = "dark";
  $: {
    const themeView = computeThemeView({
      themePreviewDraft,
      themePreviewKey,
      data,
      user,
      screen,
      cfgThemesCatalog: CFG.themesCatalog,
      primaryColor: CFG.primaryColor,
    });
    resolvedThemeKey = themeView.resolvedThemeKey;
    effectiveThemeEntry = themeView.effectiveThemeEntry;
    shellStyle = themeView.shellStyle;
    shellToneClass = themeView.shellToneClass;
    shellThemeClass = themeView.shellThemeClass;
    shellThemeCssHref = themeView.shellThemeCssHref;
    toastTheme = themeView.toastTheme;
  }
  $: applyThemeDocumentEffects(effectiveThemeEntry);
  $: syncThemeGoogleFonts(effectiveThemeEntry);
  $: isAdmin = Boolean(user?.is_admin);
  $: if (screen === "admin" && !isAdmin) {
    screen = "settings";
    activeTab = "settings";
  }
  $: currentLang = normalizeLangCode(user?.language_code || guestLanguage || CFG.language || "ru");
  let languageOptions: LanguageOption[] = [];
  let currentLanguageOption: LanguageOption | null = null;
  $: {
    const languageView = computeLanguageView({
      cfgLanguages: CFG.languages,
      currentLang,
      i18nMessages: I18N,
    });
    languageOptions = languageView.languageOptions;
    currentLanguageOption = languageView.currentLanguageOption || null;
  }
  $: userLanguage = languageName(currentLang);
  let emailLinkStatus = "";
  let telegramNotificationsStatus = "unknown";
  let telegramNotificationsNeedPrompt = false;
  let telegramNotificationsStartLink = "";
  let hasUnlinkedIdentity = false;
  let telegramProfileName = "";
  let profileEmail = "";
  let profileTelegramId = "";
  let profileAvatarUrl = "";
  let privacyPolicyUrl = "";
  let userAgreementUrl = "";
  let supportUrl = "";
  let serverStatusUrl = "";
  $: {
    const accountView = computeAccountView({
      appSettings,
      cfg: CFG,
      emailAuthEnabled,
      emailAvatarUrl,
      t,
      user,
    });
    emailLinkStatus = accountView.emailLinkStatus;
    telegramNotificationsStatus = accountView.telegramNotificationsStatus;
    telegramNotificationsNeedPrompt = accountView.telegramNotificationsNeedPrompt;
    telegramNotificationsStartLink = accountView.telegramNotificationsStartLink;
    hasUnlinkedIdentity = accountView.hasUnlinkedIdentity;
    telegramProfileName = accountView.telegramProfileName;
    profileEmail = accountView.profileEmail;
    profileTelegramId = accountView.profileTelegramId;
    profileAvatarUrl = accountView.profileAvatarUrl;
    privacyPolicyUrl = accountView.privacyPolicyUrl;
    userAgreementUrl = accountView.userAgreementUrl;
    supportUrl = accountView.supportUrl;
    serverStatusUrl = accountView.serverStatusUrl;
  }
  $: telegramLoginBotId = Number(CFG.telegramLoginBotId || 0);
  $: telegramOAuthClientId = Number(CFG.telegramOAuthClientId || telegramLoginBotId || 0);
  $: telegramMiniAppInitData = tg?.initData || readTelegramMiniAppInitDataFromLocation();
  $: telegramMiniAppAuthAvailable = Boolean(telegramMiniAppInitData);
  $: telegramMiniAppContext = hasTelegramLaunchParams();
  $: demoAuthLogin = MOCK && demoAuth.isDemoAuthMock();
  let telegramLoginUnavailable = false;
  let telegramLoginChecking = false;
  let telegramLoginLabel = "";
  let telegramLoginUnavailableMessage = "";
  $: {
    const telegramLoginView = computeTelegramLoginView({
      authBusy,
      authStatus,
      demoAuthLogin,
      telegramLoginBusy,
      telegramMiniAppAuthAvailable,
      telegramOAuthClientId,
      telegramSdkStatus,
      t,
    });
    telegramLoginUnavailable = telegramLoginView.telegramLoginUnavailable;
    telegramLoginChecking = telegramLoginView.telegramLoginChecking;
    telegramLoginLabel = telegramLoginView.telegramLoginLabel;
    telegramLoginUnavailableMessage = telegramLoginView.telegramLoginUnavailableMessage;
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

  async function refreshTelegramNotificationsOnResume() {
    await refreshTelegramNotificationsAfterResume({
      cooldownMs: TELEGRAM_NOTIFICATIONS_RESUME_REFRESH_COOLDOWN_MS,
      loadData: () => loadData({ fresh: true, preserveView: true }),
      readState: () => ({
        botOpenedAt: telegramNotificationsBotOpenedAt,
        lastCheckAt: telegramNotificationsResumeLastCheckAt,
        mode,
        needPrompt: telegramNotificationsNeedPrompt,
        refreshBusy: telegramNotificationsResumeRefreshBusy,
      }),
      setBotOpenedAt: (openedAt) => {
        telegramNotificationsBotOpenedAt = openedAt;
      },
      setLastCheckAt: (checkedAt) => {
        telegramNotificationsResumeLastCheckAt = checkedAt;
      },
      setRefreshBusy: (busy) => {
        telegramNotificationsResumeRefreshBusy = busy;
      },
    });
  }

  const popstateLifecycle = createPopstateLifecycle({
    adminRuntime,
    boot,
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
    loadPublicInstall: (shareToken) => loadPublicInstall(shareToken),
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
    boot();
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

  const { openLoginTelegram } = createTelegramLoginActions({
    authStore,
    getDemoTelegramAuthPayload: () => demoAuth.telegramAuthPayload(),
    getTelegramMiniAppInitData: () => telegramMiniAppInitData,
    getTelegramOAuthClientId: () => telegramOAuthClientId,
    isDemoAuthLogin: () => Boolean(demoAuthLogin),
  });

  const {
    continueTelegramLinkPendingAction,
    linkTelegramAndActivateTrial,
    linkTelegramAndClaimReferralWelcome,
    openSettingsLinkEmailDialog,
    openSettingsSetPasswordDialog,
    openTelegramNotificationsBot,
  } = createAccountUiActions({
    accountStore,
    demoEmail: () => demoAuth.demoEmail(),
    emailAuthEnabled: () => emailAuthEnabled,
    getTelegram: () => tg,
    getTelegramNotificationsStartLink: () => telegramNotificationsStartLink,
    isDemoAuthLogin: () => Boolean(demoAuthLogin),
    markTelegramNotificationsBotOpened: (openedAt) => {
      telegramNotificationsBotOpenedAt = openedAt;
    },
    openExternalLink,
    refreshTelegram: telegramRuntime.refreshTelegram,
    setTelegram: (value) => {
      tg = value;
    },
    showToast,
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
    onClose: closeAdminPanel,
    onLanguageChange: accountStore.updateAccountLanguage,
    onSectionChange: handleAdminSectionChange,
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

  async function boot() {
    const shareToken = publicInstallTokenFromPath(window.location.pathname);
    if (shareToken) {
      await loadPublicInstall(shareToken);
      return;
    }
    if (MOCK && demoAuth.isDemoAuthMock()) {
      demoAuth.prepareAuthState();
      showLogin();
      return;
    }
    await runWebappBoot({
      MOCK,
      setMode: (next: string) => {
        mode = next;
      },
      hasTelegramLaunchParams,
      loadTelegramSdk,
      prepareTelegramMiniApp: () => {
        if (!tg) return;
        try {
          tg.ready?.();
          tg.expand?.();
        } catch (_error) {
          void _error;
        }
      },
      loadData,
      showLogin,
      clearToken,
      clearManualLogoutFlag,
      isManuallyLoggedOut,
      hasEmailCodeLoginDeeplink,
      finalizeMagicLogin: (loginToken: string) => authStore.finalizeMagicLogin(loginToken),
      finalizeTelegramAuth: (authData: unknown, source: "auth_data" | "init_data" | "id_token") =>
        authStore.finalizeTelegramAuth(authData, source),
      setAuthStatus: (message: string, isError = false) =>
        authStore.setAuthStatus(message, isError),
      t,
      getInitDataForBoot: () =>
        telegramMiniAppInitData || tg?.initData || readTelegramMiniAppInitDataFromLocation(),
      getToken: () => token,
      getCsrfToken: () => csrfToken,
    });
    if (mode === "app" && screen !== "admin") {
      const telegramActionHandled = await continueTelegramLinkPendingAction();
      if (!telegramActionHandled) {
        if (hasPendingActivationHandoff()) await loadData({ fresh: true });
        const shown = await maybeShowActivationSuccessDialog({ source: "boot" });
        if (!shown) startPendingActivationWatch();
      }
    }
  }

  async function loadData(options: AppLoadDataOptions = {}) {
    return appLoadExecutor.loadData(options) as Promise<AnyRecord>;
  }

  const {
    openActivationConnectLink,
    openConnectLink,
    openPublicConnectLink,
    openTrialConnectLink,
  } = createConnectActions({
    getPublicInstallSubscription: () => publicInstallSubscription,
    getSubscription: () => subscription,
    getTrialActivationResult: () => trialActivationResult,
    openExternalLink,
    showToast,
    t,
  });

  const { copyText } = createClipboardActions({ showToast, t });

  const { activateTrial, applyPromo, clearPromoFieldError, setPromoCode } = createPromoTrialActions(
    {
      actionsStore,
    }
  );

  function showToast(message: unknown) {
    const text = String(message ?? "").trim();
    if (!text) return;
    sonnerToast(text, { duration: 2400 });
  }

  const { toggleAutoRenew } = createAutoRenewAction({
    billing,
    getBusy: () => autoRenewBusy,
    loadData,
    setBusy: (busy) => {
      autoRenewBusy = busy;
    },
    showToast,
    t,
  });

  const { goDevices, goHome, goInstall, goInvite, goSettings, goSupport } = createWebappNavigation({
    canUseInstallGuides,
    closePaymentModal: () => billingStore.closePaymentModal(),
    devicesEnabled: () => devicesEnabled,
    loadDevices: () => devicesStore.loadDevices(devicesEnabled),
    loadInstallGuides: () => installGuidesStore.load(),
    loadSupport: () => {
      supportStore.loadList();
      supportStore.startPolling({ includeList: true });
    },
    openConnectLink,
    setActiveTab: (tab) => {
      activeTab = tab;
    },
    setScreen: (nextScreen) => {
      screen = nextScreen;
    },
    supportEnabled: () => supportEnabled,
    syncSectionPath: syncAppSectionPath,
  });
  const { loadPublicInstall, openInstallOrConnect, openTrialInstallOrConnect } =
    createInstallRuntime({
      canUseInstallGuides,
      getOrigin: () => (typeof window !== "undefined" ? window.location.origin : ""),
      getPreloadHost: () =>
        typeof window !== "undefined" ? (window as unknown as AnyRecord) : null,
      goInstall,
      installGuidesStore,
      openConnectLink,
      openTrialConnectLink,
      setActiveTab: (tab) => {
        activeTab = tab;
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
    });

  const {
    closeDeviceTopupModal,
    disconnectDevice,
    loadDevices,
    openDeviceTopupModal,
    openPaymentModal,
    openPremiumTopupModal,
    openRegularTopupModal,
    openTariffChangeModal,
  } = createBillingModalActions({
    billingStore,
    devicesEnabled: () => devicesEnabled,
    devicesStore,
    methods: () => methods,
    plans: () => plans,
    singleTariffMode: () => singleTariffMode,
    subscription: () => subscription,
    tariffCatalog: () => tariffCatalog,
    tariffMode: () => tariffMode,
  });

  const { closeAdminPanel, handleAdminSectionChange, openAdminPanel } = createAdminPanelActions({
    cancelAdminAssetsPrefetch: adminRuntime.cancelAdminAssetsPrefetch,
    clearLanguageClickGuard,
    closePaymentModal: () => billingStore.closePaymentModal(),
    ensureAdminBundle: adminRuntime.ensureAdminBundle,
    ensureI18nScope: adminRuntime.ensureI18nScope,
    getAdminActiveSection: () => adminActiveSection,
    getRoutePathname: routePathnameFromLocation,
    getScreen: () => screen,
    isAdmin: () => isAdmin,
    isFileProtocol: () => window.location.protocol === "file:",
    routePrefix,
    setActiveTab: (tab) => {
      activeTab = tab;
    },
    setAdminActiveSection: (section) => {
      adminActiveSection = section;
    },
    setScreen: (nextScreen) => {
      screen = nextScreen;
    },
    showToast,
    syncAppSectionPath,
    t,
  });

  const { backToTariffList, continueWithSelectedTariff, selectTariff } = createTariffActions({
    billingStore,
    getPlans: () => plans,
    getSelectedTariffPlans: () => selectedTariffPlans,
    getSubscription: () => subscription,
    getTariffCatalog: () => tariffCatalog,
  });
  const primaryPayActionLabel = createPrimaryPayActionLabel({
    getAppSettings: () => appSettings,
    getSelectedPlan: () => selectedPlan,
    getSubscription: () => subscription,
    getTrafficMode: () => trafficMode,
    t,
  });
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
      <svelte:component this={previewBoardComponent} config={CFG} mockData={MOCK_SOURCE.data} />
    {:else}
      <AppModeContent
        {accountStore}
        {activateTrial}
        {activationSuccessDialogOpen}
        {activationSuccessUseInstallGuides}
        {activeTab}
        {adminBundleApi}
        {adminBundleError}
        bind:adminMountTarget
        {appLaunchTarget}
        {appSettings}
        {applyPromo}
        {authBusy}
        {authIsError}
        {authResendCooldown}
        {authStatus}
        {authStore}
        {autoRenewBusy}
        {backToTariffList}
        {billingStore}
        {brand}
        {brandTitle}
        {canChangeTariff}
        cfg={CFG}
        {clearPromoFieldError}
        {closeActivationSuccessDialog}
        {closeDeviceTopupModal}
        {continueWithSelectedTariff}
        {copyText}
        {currentLang}
        {currentLanguageOption}
        {currentTariffName}
        {devicesBusy}
        {devicesData}
        {devicesEnabled}
        {devicesErrorCode}
        {devicesIsError}
        {devicesLoaded}
        {devicesStatus}
        {devicesStore}
        {disconnectDevice}
        {emailAuthEnabled}
        {emailLinkStatus}
        {goDevices}
        {goHome}
        {goInvite}
        {goSettings}
        {goSupport}
        {hasActiveTariffSubscription}
        {hasMultipleTariffs}
        {hasUnlinkedIdentity}
        {isAdmin}
        {languageBusy}
        {languageClickGuard}
        {languageClickGuardArmed}
        bind:languageMenuOpen
        {languageOptions}
        {linkEmailBusy}
        {linkTelegramAndActivateTrial}
        {linkTelegramAndClaimReferralWelcome}
        {linkTelegramBusy}
        {loadDevices}
        {loginEmailFieldError}
        {loginEmailTooltipOpen}
        {methods}
        {mode}
        {openAdminPanel}
        {openAppLaunchTarget}
        {openAppLink}
        {openConnectLink}
        {openDeviceTopupModal}
        {openExternalLink}
        {openInstallOrConnect}
        {openLoginTelegram}
        {openPaymentModal}
        {openPremiumTopupModal}
        {openPublicConnectLink}
        {openRegularTopupModal}
        {openSettingsLinkEmailDialog}
        {openSettingsSetPasswordDialog}
        {openTariffChangeModal}
        {openTelegramNotificationsBot}
        {openTrialInstallOrConnect}
        {passwordLoginFallback}
        {passwordLoginMode}
        {pendingEmail}
        {plans}
        {premiumTrafficTopupBarClickable}
        {premiumTrafficTopupUnlocked}
        {primaryPayActionLabel}
        {privacyPolicyUrl}
        {profileAvatarUrl}
        {profileEmail}
        {profileTelegramId}
        {promoBusy}
        {promoCode}
        {promoFieldError}
        {promoIsError}
        {promoStatus}
        {publicInstallSubscription}
        {publicInstallToken}
        {referral}
        {referralBonusDetails}
        {referralOneBonusPerReferee}
        {referralWelcomeBonusDays}
        {refreshAppLaunchTarget}
        {regularTrafficTopupBarClickable}
        {regularTrafficTopupUnlocked}
        bind:screen
        {selectedTariff}
        {selectedTariffPlans}
        {selectTariff}
        {serverStatusUrl}
        {setLanguageMenuOpen}
        {setPasswordLoginMode}
        {setPromoCode}
        {shellStyle}
        {shellThemeClass}
        {shellToneClass}
        {singleTariffMode}
        {submitEmailOnEnter}
        {subscription}
        {subscriptionPurchaseDescription}
        {supportEnabled}
        {supportStore}
        {supportUnreadCount}
        {supportUnreadLoaded}
        {supportUnreadLoading}
        {supportUrl}
        {t}
        {tariffCatalog}
        {tariffMode}
        {telegramLoginBusy}
        {telegramLoginChecking}
        {telegramLoginLabel}
        {telegramLoginUnavailable}
        {telegramLoginUnavailableMessage}
        {telegramMiniAppContext}
        {telegramNotificationsNeedPrompt}
        {telegramNotificationsStartLink}
        {telegramNotificationsStatus}
        telegramPlatform={tg?.platform || ""}
        {telegramProfileName}
        {termUnitLabel}
        {toggleAutoRenew}
        {trafficMode}
        {trialActivationError}
        {trialActivationResult}
        {trialBusy}
        {user}
        {userAgreementUrl}
        {userLanguage}
        {updateGuestLanguage}
      />
    {/if}
  {/key}
</Tooltip.Provider>
