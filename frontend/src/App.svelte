<script lang="ts">
  import { onMount, setContext, tick } from "svelte";
  import { Toaster, toast as sonnerToast } from "svelte-sonner";
  import { createAuthStore } from "./lib/webapp/stores/authStore";
  import { createBillingStore } from "./lib/webapp/stores/billingStore";
  import { createDevicesStore } from "./lib/webapp/stores/devicesStore";
  import { createInstallGuidesStore } from "./lib/webapp/stores/installGuidesStore";
  import { createSupportStore } from "./lib/webapp/stores/supportStore";
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
  import { createActivationWatcher } from "./lib/webapp/activationWatcher";
  import { createAdminBundle } from "./lib/webapp/adminBundle";
  import { isPasswordLoginPath, syncPasswordLoginPath } from "./lib/webapp/passwordLoginRoute.js";
  import {
    currentSearchParams,
    hasEmailCodeLoginDeeplink,
    readEmailCodeLoginDeeplink,
    readRenewalDeeplink,
    stripRenewalLoginQueryFromUrl,
    stripTopupQueryFromUrl,
  } from "./lib/webapp/deeplinks";
  import { createDemoAuth } from "./lib/webapp/demoAuth";
  import { createDocsDemoRouter } from "./lib/webapp/docsDemoRoutes.js";
  import { createTelegramLaunch } from "./lib/webapp/telegramLaunch";
  import { createUiChrome } from "./lib/webapp/uiChrome";
  import { createEmailAvatarSync } from "./lib/webapp/emailAvatarSync.js";
  import {
    type BillingPlan,
    type PaymentMethod,
    type TariffCatalogEntry,
  } from "./lib/webapp/tariffs.js";
  import { reconcileBillingSelection } from "./lib/webapp/billingSelectionSync.js";
  import { renewalPaymentConfig, resolveTopupDeeplinkKind } from "./lib/webapp/billingDeeplinks.js";
  import { activeTabForWebappSection } from "./lib/webapp/sectionAvailability.js";
  import { readThemePreviewDraft, syncThemeGoogleFonts } from "./lib/webapp/themeStyle.js";
  import { computeThemeView } from "./lib/webapp/themeView.js";
  import { computeBillingView } from "./lib/webapp/billingView.js";
  import { computeLanguageView, type LanguageOption } from "./lib/webapp/languageView.js";
  import { computeTelegramLoginView } from "./lib/webapp/telegramLoginView.js";
  import { computeAccountView } from "./lib/webapp/accountView.js";
  import { computeAppDataView } from "./lib/webapp/appDataView.js";
  import { createWebappNavigation } from "./lib/webapp/webappNavigation.js";
  import { adminPayloadHasFrontendReloadChange } from "./lib/webapp/adminPersistedSettings.js";
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
  import { createExternalLinkRuntime } from "./lib/webapp/externalLinkRuntime.js";
  import {
    resolveInitialLoadRoute,
    resolveLoadedWebappRoute,
    resolveSupportLoadRoute,
  } from "./lib/webapp/appLoadFlow.js";
  import { resolvePopstateRoute } from "./lib/webapp/appRouteLifecycle.js";

  /** Used-traffic percent from which top-up modals and CTAs unlock in the web app home screen */
  const TRAFFIC_TOPUP_UNLOCK_PERCENT = 80;
  const ACTIVATION_HANDOFF_STORAGE_KEY = "rw_webapp_activation_handoff_v1";
  const ACTIVATION_HANDOFF_TTL_MS = 48 * 60 * 60 * 1000;
  const TELEGRAM_NOTIFICATIONS_RESUME_REFRESH_COOLDOWN_MS = 1500;
  import { createActivationHandoff } from "./lib/webapp/activationHandoff.js";
  import { createBillingActions } from "./lib/webapp/billingActions";
  import { invalidateWebappTariffOptionCaches } from "./lib/webapp/billingOptionCache.js";
  import { runWebappBoot } from "./lib/webapp/webappBoot.js";
  import { CSRF_COOKIE_NAME, readCookie } from "./lib/webapp/session.js";
  import { createTelegramSdk } from "./lib/webapp/telegramSdk.js";
  import { publicInstallTokenFromPath, sectionFromPath } from "./lib/webapp/routes.js";

  type AnyRecord = Record<string, any>;
  type TelegramWebApp = AnyRecord & {
    initData?: string;
    openInvoice?: (url: string, callback: (status: string) => void) => void;
    openLink?: (url: string, options?: AnyRecord) => void;
    openTelegramLink?: (url: string) => void;
    platform?: string;
    ready?: () => void;
    expand?: () => void;
  };
  type AppLoadDataOptions = {
    fresh?: boolean;
    preserveView?: boolean;
    section?: string;
    adminSection?: string | null;
    [key: string]: any;
  };
  type AdminPersistOptions = {
    updates?: Record<string, unknown>;
    deletes?: string[];
    reloadFrontend?: boolean;
    deferFrontendReload?: boolean;
  };
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
  let adminI18nLoaded = false;
  let adminI18nPromise: Promise<unknown> | null = null;
  let adminBundleApi: AnyRecord | null = null;
  let adminBundleError = "";
  let adminMountTarget: HTMLElement | null = null;
  let adminPanelProps: AnyRecord = {};
  let adminActiveSection = "stats";
  let tg: TelegramWebApp | null = null;
  const telegramSdk = createTelegramSdk({
    scriptUrl: TELEGRAM_WEBAPP_SCRIPT_URL,
    bootTimeoutMs: TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    actionTimeoutMs: TELEGRAM_SDK_ACTION_TIMEOUT_MS,
    miniAppAuthTimeoutMs: TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS,
    onStatusChange: (status: string) => (telegramSdkStatus = status),
    onInitDataChange: (initData: string) => (telegramMiniAppInitData = initData || ""),
  } as any);
  tg = telegramSdk.refresh();
  telegramSdkStatus = tg ? "ready" : "idle";
  telegramMiniAppInitData = telegramSdk.initData;
  const telegramLaunch = createTelegramLaunch<TelegramWebApp | null>({
    telegramSdk,
    defaultTimeoutMs: TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    onLoaded: (value, initData) => {
      tg = value;
      telegramMiniAppInitData = initData;
    },
  });
  const readTelegramMiniAppInitDataFromLocation = telegramLaunch.readInitDataFromLocation;
  const hasTelegramLaunchParams = telegramLaunch.hasLaunchParams;
  const loadTelegramSdk = telegramLaunch.load;
  const { openAppLaunchTarget, openAppLink, openExternalLink, refreshAppLaunchTarget } =
    createExternalLinkRuntime({
      assignLocation: (url) => window.location.assign(url),
      getCurrentLang: () => currentLang,
      getTelegram: () => tg,
      hasTelegramLaunchParams,
      refreshTelegram: () => telegramSdk.refresh(),
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
  const activationHandoff = createActivationHandoff({
    storageKey: ACTIVATION_HANDOFF_STORAGE_KEY,
    ttlMs: ACTIVATION_HANDOFF_TTL_MS,
  } as any) as any;
  const activationWatcher = createActivationWatcher({
    activationHandoff,
    billing,
    getData: () => data,
    loadData,
    maybeShowActivationSuccessDialog,
    shouldWatch: () =>
      mode === "app" &&
      activationHandoff.hasPending(data || {}) &&
      !activationSuccessDialogOpen &&
      screen !== "admin",
    canRefreshOnResume: () =>
      mode === "app" &&
      screen !== "admin" &&
      !activationSuccessDialogOpen &&
      !paymentModalOpen &&
      !topupModalOpen &&
      !deviceTopupModalOpen &&
      !changeModalOpen &&
      !changeConfirmOpen &&
      activationHandoff.hasPending(data || {}),
  });
  const adminBundle = createAdminBundle({
    ensureI18nScope: () => ensureI18nScope("admin"),
    getAssets: () => ({
      adminCssAsset: CFG.adminCssAsset,
      adminJsAsset: CFG.adminJsAsset,
    }),
    shouldPrefetch: () => isAdmin && screen !== "admin",
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
  const devicesStore = createDevicesStore({ api, t, showToast });
  const supportStore = createSupportStore({ api, t, showToast, routePrefix });
  const installGuidesStore = createInstallGuidesStore({ api, t, showToast });
  const actionsStore = createActionsStore({
    api,
    t,
    showToast,
    loadData,
    maybeShowActivationSuccessDialog,
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
  $: if (typeof document !== "undefined" && effectiveThemeEntry?.tokens) {
    const scheme = effectiveThemeEntry.tokens.color_scheme || "dark";
    document.documentElement.style.colorScheme = scheme;
    const bg = effectiveThemeEntry.tokens.bg;
    if (bg) document.body.style.backgroundColor = bg;
  }
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
  $: if (!emailAuthEnabled && linkEmailOpen) {
    accountStore.closeLinkEmailDialog();
  }
  $: if (!emailAuthEnabled && setPasswordOpen) {
    accountStore.closeSetPasswordDialog();
  }
  $: {
    const billingSelectionPatch = reconcileBillingSelection(
      {
        paymentStep: $billingStore.paymentStep,
        selectedMethod: $billingStore.selectedMethod,
        selectedPlan,
        selectedTariffKey,
      },
      {
        methods,
        plans,
        selectedTariffPlans,
        singleTariffMode,
        tariffCatalog,
        tariffMode,
      }
    );
    if (billingSelectionPatch) billingStore.update((s) => ({ ...s, ...billingSelectionPatch }));
  }
  $: {
    emailAvatarSync.sync(user?.email, (url) => {
      emailAvatarUrl = url;
    });
  }

  function canUseInstallGuides() {
    return canUseSubscriptionInstallGuides({
      installGuidesEnabled,
      subscription,
    });
  }

  function hasPendingActivationHandoff(payload: AnyRecord | null = data) {
    return activationHandoff.hasPending(payload || {});
  }

  function rememberActivationPending(context: AnyRecord = {}) {
    activationHandoff.rememberPending(context, data || {});
  }

  async function maybeShowActivationSuccessDialog(context: AnyRecord = {}) {
    if (activationSuccessDialogOpen) return false;
    await tick();
    const payload = context.payload || data;
    const subscriptionKey = activationHandoff.subscriptionKey(payload);
    if (!subscriptionKey) return false;
    const state = activationHandoff.read();
    const pending = state.pending;
    if (!context.force && activationHandoff.isAcknowledged(subscriptionKey, state)) {
      if (pending && activationHandoff.pendingMatchesUser(pending, payload)) {
        activationHandoff.write({ ...state, pending: null });
      }
      return false;
    }
    if (
      !context.force &&
      (!pending ||
        !activationHandoff.isPendingFresh(pending) ||
        !activationHandoff.pendingMatchesUser(pending, payload))
    ) {
      return false;
    }
    activationHandoff.acknowledge(subscriptionKey, context, payload, state);
    stopPendingActivationWatch();
    activationSuccessUseInstallGuides = canUseInstallGuides();
    billingStore.closePaymentModal();
    activeTab = "home";
    if (!activationSuccessUseInstallGuides) {
      screen = "home";
      syncAppSectionPath("home", true);
    }
    activationSuccessDialogOpen = true;
    return true;
  }

  function stopPendingActivationWatch() {
    activationWatcher.stop();
  }

  function startPendingActivationWatch() {
    activationWatcher.start();
  }

  async function refreshPendingActivationOnResume() {
    await activationWatcher.refreshOnResume();
  }

  async function refreshTelegramNotificationsOnResume() {
    if (
      mode !== "app" ||
      !telegramNotificationsNeedPrompt ||
      !telegramNotificationsBotOpenedAt ||
      telegramNotificationsResumeRefreshBusy
    ) {
      return;
    }
    const now = Date.now();
    if (
      now - telegramNotificationsResumeLastCheckAt <
      TELEGRAM_NOTIFICATIONS_RESUME_REFRESH_COOLDOWN_MS
    ) {
      return;
    }
    telegramNotificationsResumeLastCheckAt = now;
    telegramNotificationsResumeRefreshBusy = true;
    try {
      await loadData({ fresh: true, preserveView: true });
      if (!telegramNotificationsNeedPrompt) telegramNotificationsBotOpenedAt = 0;
    } catch (_error) {
      void _error;
    } finally {
      telegramNotificationsResumeRefreshBusy = false;
    }
  }

  onMount(() => {
    if (isPreviewBoard) return;
    if (isAppLaunchRoute) return;
    const onAnyPointerDown = () => {
      if (mode === "login") loginEmailTooltipOpen = false;
    };
    const onActivationResume = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      void refreshPendingActivationOnResume();
      void refreshTelegramNotificationsOnResume();
    };
    const onVisibilityChange = () => {
      if (document.visibilityState !== "hidden") onActivationResume();
    };
    const onPopState = () => {
      const currentQuery = currentSearchParams();
      const decision = resolvePopstateRoute({
        canUseInstallGuides: canUseInstallGuides(),
        devicesEnabled,
        fallbackAdminSection: initialAdminSectionFromLocation(),
        isAdmin,
        isDocsDemo,
        mode,
        pathname: routePathnameFromLocation(),
        routePrefix,
        screenQuery: currentQuery.get("screen"),
        supportEnabled,
      });
      if (decision.kind === "publicInstall") {
        void loadPublicInstall(decision.shareToken);
        return;
      }
      if (decision.kind === "boot") {
        void boot();
        return;
      }
      if (decision.kind === "login") {
        setPasswordLoginMode(decision.passwordLoginEnabled, true);
        screen = "login";
        return;
      }
      if (decision.kind === "admin") {
        adminActiveSection = decision.adminSection;
        cancelAdminAssetsPrefetch();
        activeTab = decision.activeTab;
        screen = decision.section;
        const pathAtStart = window.location.pathname;
        void Promise.all([ensureI18nScope("admin"), ensureAdminBundle()]).catch(() => {
          if (sectionFromPath(routePathnameFromLocation(), routePrefix) !== "admin") return;
          if (window.location.pathname !== pathAtStart) return;
          if (screen === "admin") {
            activeTab = "settings";
            screen = "settings";
            syncAppSectionPath("settings", true);
          }
          showToast(t("wa_unavailable"));
        });
        return;
      }
      if (decision.kind === "section") {
        activeTab = decision.activeTab;
        screen = decision.section;
        if (decision.loadDevices) devicesStore.loadDevices(devicesEnabled);
        if (decision.loadSupport) {
          supportStore.loadList();
          supportStore.startPolling({ includeList: true });
        }
        if (decision.loadInstallGuides) installGuidesStore.load();
      }
    };
    window.addEventListener("popstate", onPopState);
    window.addEventListener("pointerdown", onAnyPointerDown);
    window.addEventListener("focus", onActivationResume);
    window.addEventListener("pageshow", onActivationResume);
    document.addEventListener("visibilitychange", onVisibilityChange);
    boot();
    return () => {
      window.removeEventListener("popstate", onPopState);
      window.removeEventListener("pointerdown", onAnyPointerDown);
      window.removeEventListener("focus", onActivationResume);
      window.removeEventListener("pageshow", onActivationResume);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      authStore.stopTelegramLoginWatchdog();
      authStore.clearCooldownTimer();
      accountStore.clearLinkEmailResendTimer();
      accountStore.clearSetPasswordResendTimer();
      supportStore.closePolling();
      stopPendingActivationWatch();
      clearLanguageClickGuard();
      cancelAdminAssetsPrefetch();
      syncBodyScrollLock(false);
      destroyAdminMount();
    };
  });

  async function ensureI18nScope(scope: string) {
    if (MOCK || scope !== "admin" || adminI18nLoaded) return;
    if (adminI18nPromise) return adminI18nPromise;
    const apiBase = String(CFG.apiBase || "/api").replace(/\/+$/, "");
    adminI18nPromise = fetch(`${apiBase}/i18n?scope=admin`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (!payload?.ok || !payload.i18n) return;
        i18n.mergeMessages(payload.i18n);
        adminI18nLoaded = true;
      })
      .catch((_error) => {
        void _error;
      })
      .finally(() => {
        adminI18nPromise = null;
      });
    return adminI18nPromise;
  }

  function scheduleAdminAssetsPrefetch(adminAllowed = isAdmin) {
    adminBundle.schedulePrefetch(adminAllowed);
  }

  function cancelAdminAssetsPrefetch() {
    adminBundle.cancelPrefetch();
  }

  async function ensureAdminBundle() {
    try {
      return await adminBundle.ensure();
    } finally {
      syncAdminBundleState();
    }
  }

  function syncAdminBundleState() {
    adminBundleApi = adminBundle.getApi();
    adminBundleError = adminBundle.getError();
  }

  function destroyAdminMount() {
    adminBundle.destroyMount();
  }

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
    refreshTelegram: () => telegramSdk.refresh(),
    setTelegram: (value) => {
      tg = value;
    },
    showToast,
    t,
  });

  async function startEmailCodeLoginFromDeeplink() {
    if (emailLoginDeeplinkConsumed) return;
    const emailHint = readEmailCodeLoginDeeplink();
    if (!emailHint) return;
    emailLoginDeeplinkConsumed = true;
    authStore.clearPendingEmailCode();
    authStore.update((s) => ({
      ...s,
      email: emailHint,
      emailCode: "",
      pendingEmail: "",
      passwordLoginMode: false,
      passwordLoginFallback: false,
    }));
    await tick();
    await authStore.requestEmailCode((nextScreen) => {
      screen = nextScreen;
    });
  }

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
    onSettingsSaved: handleAdminPersistedSaved,
    onTariffsSaved: handleAdminPersistedSaved,
    onThemesSaved: handleAdminPersistedSaved,
    onToast: (text: string) => showToast(text),
    onTranslationsSaved: handleAdminTranslationsSaved,
    pathname: routePathnameFromLocation(),
    routePrefix,
    screen,
    t,
  });

  $: {
    const shouldMountAdmin = screen === "admin" && isAdmin && adminBundleApi && adminMountTarget;
    const props = adminPanelProps;

    if (shouldMountAdmin) {
      adminBundle.mount(adminMountTarget!, props as Record<string, unknown>);
      syncAdminBundleState();
    } else {
      destroyAdminMount();
    }
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

  function setPasswordLoginMode(enabled: boolean, replace = false) {
    const nextEnabled = Boolean(enabled);
    authStore.update((s) => ({
      ...s,
      passwordLoginMode: nextEnabled,
      passwordLoginFallback: false,
      authStatus: "",
      authIsError: false,
    }));
    syncPasswordLoginPath({
      cleanDocsDemoRouteQuery,
      enabled: nextEnabled,
      isDocsDemo,
      replace,
      routePrefix,
    });
  }

  async function loadData(options: AppLoadDataOptions = {}) {
    const currentQuery = currentSearchParams();
    const initialRoute = resolveInitialLoadRoute({
      activeTab,
      adminActiveSection,
      adminSection: options?.adminSection,
      fallbackAdminSection: initialAdminSectionFromLocation(),
      mock: Boolean(MOCK),
      pathname: routePathnameFromLocation(),
      preserveView: options?.preserveView === true,
      routePrefix,
      screen,
      screenQuery: currentQuery.get("screen"),
      section: options?.section,
    });
    const installGuidesPromise = initialRoute.shouldPreloadInstallGuides
      ? installGuidesStore.load()
      : null;
    const payload = (await dataClient.loadData({ fresh: options?.fresh === true })) as AnyRecord;
    if (!payload.ok) throw new Error(payload.error || "load_failed");
    data = payload;
    billingStore.update((s) => ({
      ...s,
      selectedPlan: null,
      selectedTariffKey: "",
      paymentStep: "tariff",
      renewHwidDevices: true,
      selectedMethod: payload.payment_methods?.[0]?.id || "",
    }));
    const loadedRoute = resolveLoadedWebappRoute({
      fallbackAdminSection: initialAdminSectionFromLocation(),
      payload,
      preservedAdminSection: initialRoute.preservedAdminSection,
      routeSection: initialRoute.routeSection,
    });
    let section = loadedRoute.section;
    const initialAdminSection = loadedRoute.initialAdminSection;
    if (section === "admin" && payload.user?.is_admin) {
      cancelAdminAssetsPrefetch();
      adminActiveSection = initialAdminSection || "stats";
      activeTab = "settings";
      screen = "admin";
      mode = "app";
      try {
        await ensureI18nScope("admin");
        await ensureAdminBundle();
      } catch (_error) {
        void _error;
        section = "settings";
        activeTab = "settings";
        screen = "settings";
        showToast(t("wa_unavailable"));
      }
    }
    const supportRoute = resolveSupportLoadRoute({
      pathname: routePathnameFromLocation(),
      routePrefix,
      section,
    });
    const initialSupportTicketId = supportRoute.initialSupportTicketId;
    if (isDocsDemo) docsDemoParentRouteConsumed = true;
    activeTab =
      section === loadedRoute.section ? loadedRoute.activeTab : activeTabForWebappSection(section);
    screen = section;
    mode = "app";
    if (loadedRoute.shouldPrefetchAdminAssets) {
      scheduleAdminAssetsPrefetch(true);
    }
    if (loadedRoute.supportEnabled) {
      if (typeof payload.support_unread_count !== "undefined") {
        supportStore.hydrateUnread(payload.support_unread_count);
      } else {
        void supportStore.refreshUnread();
      }
      supportStore.startPolling({ includeList: false });
    }
    if (section === "support" && initialSupportTicketId && supportRoute.targetPath) {
      if (
        window.location.protocol !== "file:" &&
        window.location.pathname !== supportRoute.targetPath
      ) {
        window.history.replaceState(
          null,
          "",
          `${supportRoute.targetPath}${window.location.search}${window.location.hash}`
        );
      }
      cleanDocsDemoRouteQuery();
    } else {
      syncAppSectionPath(section, true, initialAdminSection);
    }
    if (section === "devices" && payload.settings?.my_devices_enabled) {
      await devicesStore.loadDevices(true, true);
    }
    if (section === "install") {
      await (installGuidesPromise || installGuidesStore.load());
    } else if (payload.settings?.subscription_guides_enabled && payload.subscription?.active) {
      void installGuidesStore.load();
    }
    if (section === "support") {
      if (initialSupportTicketId)
        await supportStore.openTicket(initialSupportTicketId, { skipPush: true });
      else await supportStore.loadList();
      supportStore.startPolling({ includeList: true });
    }
    if (topupModalOpen) await billingStore.loadTopupOptions(topupKind);
    if (deviceTopupModalOpen) await billingStore.loadDeviceTopupOptions();
    if (changeModalOpen) await billingStore.loadTariffChangeOptions();

    const deeplinkPlans = (payload.plans?.length ? payload.plans : []) as BillingPlan[];
    const deeplinkDefaultMethod = String(payload.payment_methods?.[0]?.id || "");
    const topupDeeplinkKind = resolveTopupDeeplinkKind({
      plans: deeplinkPlans,
      search: window.location.search,
      subscription: (payload.subscription || {}) as AnyRecord,
    });
    if (topupDeeplinkKind) {
      billingStore.openTopupModal(topupDeeplinkKind, deeplinkDefaultMethod);
      stripTopupQueryFromUrl();
    }

    const renewalDeep = readRenewalDeeplink();
    if (renewalDeep) {
      const renewalPayment = renewalPaymentConfig({
        defaultMethod: deeplinkDefaultMethod,
        plans: deeplinkPlans,
        subscription: (payload.subscription || {}) as AnyRecord,
        tariffKey: renewalDeep.tariffKey,
      });
      activeTab = "home";
      screen = "home";
      syncAppSectionPath("home", true);
      billingStore.openPaymentModal(
        renewalPayment.tariffMode,
        renewalPayment.singleTariffMode,
        renewalPayment.tariffCatalog,
        renewalPayment.subscription,
        renewalPayment.plans,
        renewalPayment.defaultMethod,
        renewalPayment.options
      );
      stripRenewalLoginQueryFromUrl();
    }
    return payload;
  }

  function showLogin() {
    mode = "login";
    screen = "login";
    activeTab = "home";
    setPasswordLoginMode(isPasswordLoginPath(routePathnameFromLocation()), true);
    authStore.restorePendingEmailCode((nextScreen) => {
      screen = nextScreen;
    });
    void startEmailCodeLoginFromDeeplink();
  }

  function submitEmailOnEnter(event: KeyboardEvent) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    authStore.requestEmailCode((s) => (screen = s));
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

  function navigateToActivationTarget({ replace = true } = {}) {
    const useInstallGuides = canUseInstallGuides();
    activationSuccessUseInstallGuides = useInstallGuides;
    billingStore.closePaymentModal();
    activeTab = "home";
    if (useInstallGuides) {
      screen = "install";
      syncAppSectionPath("install", replace);
      installGuidesStore.load(true);
      return;
    }
    screen = "home";
    syncAppSectionPath("home", replace);
  }

  async function handleSubscriptionActivated(context = {}) {
    await tick();
    if (!subscription?.active) return;
    await maybeShowActivationSuccessDialog({ ...context, force: true, source: "payment" });
  }

  function closeActivationSuccessDialog() {
    const shouldOpenConnect = !activationSuccessUseInstallGuides;
    activationSuccessDialogOpen = false;
    if (activationSuccessUseInstallGuides) {
      navigateToActivationTarget({ replace: true });
      return;
    }
    if (shouldOpenConnect) openActivationConnectLink();
  }

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
    cancelAdminAssetsPrefetch,
    clearLanguageClickGuard,
    closePaymentModal: () => billingStore.closePaymentModal(),
    ensureAdminBundle,
    ensureI18nScope,
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

  async function handleAdminPersistedSaved(options: AdminPersistOptions = {}) {
    invalidateWebappTariffOptionCaches(billingStore);
    installGuidesStore.reset();
    try {
      await loadData({ fresh: true, preserveView: true });
    } catch {
      // Admin save already succeeded; a later full refresh will pick up new settings or catalog.
    }
    const shouldReloadFrontend =
      options?.reloadFrontend === true ||
      (!options?.deferFrontendReload && adminPayloadHasFrontendReloadChange(options));
    if (shouldReloadFrontend && typeof window !== "undefined") {
      window.location.reload();
    }
  }

  async function refreshI18nScope(scope: string) {
    if (MOCK) return;
    const apiBase = String(CFG.apiBase || "/api").replace(/\/+$/, "");
    try {
      const response = await fetch(`${apiBase}/i18n?scope=${encodeURIComponent(scope)}`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const payload = await response.json();
      if (payload?.ok && payload.i18n) i18n.mergeMessages(payload.i18n);
      if (scope === "admin") adminI18nLoaded = true;
    } catch (_error) {
      void _error;
    }
  }

  async function handleAdminTranslationsSaved(options = {}) {
    adminI18nLoaded = false;
    await Promise.all([refreshI18nScope("webapp"), refreshI18nScope("admin")]);
    await handleAdminPersistedSaved({ ...options, deferFrontendReload: true });
  }

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
