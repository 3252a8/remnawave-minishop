<script lang="ts">
  import { onMount, tick } from "svelte";
  import { Toaster, toast as sonnerToast } from "svelte-sonner";
  import { Tooltip } from "$components/ui/primitives.js";

  import AppModeContent from "./webapp/AppModeContent.svelte";

  import {
    MANUAL_LOGOUT_FLAG_KEY,
    TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS,
    TELEGRAM_SDK_ACTION_TIMEOUT_MS,
    TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    TELEGRAM_WEBAPP_SCRIPT_URL,
  } from "./lib/webapp/constants";

  import {
    applyFavicon,
    applyDocumentTitle,
    readJsonScript,
    structuredCloneSafe,
  } from "./lib/webapp/browser.js";
  import { isExternalAppLaunchPath, readExternalAppLaunchTarget } from "./lib/webapp/appLinks.js";
  import { canUseSubscriptionInstallGuides } from "./lib/webapp/connectLinks.js";
  import { createI18n } from "./lib/webapp/i18n.js";
  import {
    currentSearchParams,
    hasEmailCodeLoginDeeplink,
    readCheckoutPromoDeeplink,
    readRenewalDeeplink,
    stripCheckoutPromoQueryFromUrl,
    stripRenewalLoginQueryFromUrl,
    stripTopupQueryFromUrl,
  } from "./lib/webapp/deeplinks";
  import { createDocsDemoRouter } from "./lib/webapp/docsDemoRoutes.js";
  import { readThemePreviewDraft, syncThemeGoogleFonts } from "./lib/webapp/themeStyle";
  import { computeAppShellView, type AppShellView } from "./lib/webapp/appShellView.js";
  import type { AppActionRuntime } from "./lib/webapp/appActionRuntime.js";
  import { createExternalLinkRuntime } from "./lib/webapp/externalLinkRuntime.js";
  import { createAppLoadExecutor, type AppLoadDataOptions } from "./lib/webapp/appLoadExecutor.js";
  import { createPopstateLifecycle } from "./lib/webapp/popstateLifecycle.js";
  import { miniAppPathFromSearch } from "./lib/webapp/miniAppStartRoute.js";
  import {
    buildAppAdminPanelProps,
    createAppFactories,
    createShellAppActions,
  } from "./lib/webapp/appFactories";
  import {
    applyThemeDocumentEffects,
    closeDisabledEmailAuthDialogs,
    syncShellBillingSelection,
    syncShellEmailAvatar,
  } from "./lib/webapp/shellEffects.js";

  /** Used-traffic percent from which top-up modals and CTAs unlock in the web app home screen */
  const TRAFFIC_TOPUP_UNLOCK_PERCENT = 80;
  const TELEGRAM_NOTIFICATIONS_RESUME_REFRESH_COOLDOWN_MS = 1500;
  import { CSRF_COOKIE_NAME, readCookie } from "./lib/webapp/session.js";
  import { createTelegramRuntime, type TelegramWebApp } from "./lib/webapp/telegramRuntime.js";
  import { resetShellState, shellState } from "./lib/webapp/shellState.svelte";
  import {
    FALLBACK_WEBAPP_CONFIG,
    asWebappRecord,
    asWebappRecordOrNull,
    type AdminPanelProps,
    type SubscriptionView,
    type UserProfile,
    type WebappConfig,
    type WebappData,
    type WebappMockRuntime,
    type WebappMockSource,
    type WebappRecord,
  } from "./lib/webapp/types.js";

  let { mockRuntime = null }: { mockRuntime?: WebappMockRuntime | null } = $props();

  function initialMockRuntime(): WebappMockRuntime | null {
    return mockRuntime;
  }

  const stableMockRuntime = initialMockRuntime();

  const FALLBACK_BRAND_TITLE = "Subscription";
  const EMPTY_MOCK: WebappMockSource = {
    config: {
      ...FALLBACK_WEBAPP_CONFIG,
      title: FALLBACK_BRAND_TITLE,
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
  const MOCK_SOURCE: WebappMockSource = stableMockRuntime?.source || EMPTY_MOCK;
  const MOCK_DATA = MOCK_SOURCE.data || {};
  const runtimeMockApi = stableMockRuntime?.mockApi || null;
  const previewBoardComponent = stableMockRuntime?.PreviewBoard || null;
  const isDocsDemo = stableMockRuntime?.docsDemo === true;
  const routePrefix = isDocsDemo ? "/demo/runtime" : "";
  const query = new URLSearchParams(window.location.search);
  const miniAppStartPath = miniAppPathFromSearch(window.location.search);
  if (miniAppStartPath && window.location.pathname !== miniAppStartPath) {
    window.history.replaceState(
      null,
      "",
      `${miniAppStartPath}${window.location.search}${window.location.hash}`
    );
  }
  const isAppLaunchRoute = isExternalAppLaunchPath(window.location.pathname);
  stableMockRuntime?.applyPreviewMock?.(query.get("mock"));
  const isPreviewBoard = Boolean(previewBoardComponent) && query.get("preview") === "all";
  const injectedConfig = asWebappRecordOrNull(readJsonScript("webapp-config"));
  const injectedI18n = asWebappRecordOrNull(readJsonScript("i18n"));
  const isLocalShell =
    window.location.protocol === "file:" ||
    ["", "localhost", "127.0.0.1"].includes(window.location.hostname);
  const MOCK: WebappMockSource | null =
    stableMockRuntime?.mockApi && !injectedConfig && (isLocalShell || isDocsDemo)
      ? MOCK_SOURCE
      : null;
  const CFG = {
    ...MOCK_SOURCE.config,
    ...(MOCK ? MOCK.config : {}),
    ...(injectedConfig || {}),
  } as WebappConfig;
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
  const I18N: WebappRecord = injectedI18n || {};

  resetShellState({
    appLaunchTarget: isAppLaunchRoute ? readExternalAppLaunchTarget() : "",
    csrfToken: MOCK ? "" : readCookie(CSRF_COOKIE_NAME) || "",
    data: isPreviewBoard ? structuredCloneSafe(MOCK_DATA) : null,
    mode: isAppLaunchRoute ? "appLaunch" : isPreviewBoard ? "preview" : "loading",
    token: MOCK ? "local-preview" : "",
  });

  const docsDemoParentRouteConsumed = $derived(shellState.docsDemoParentRouteConsumed);
  const telegramSdkStatus = $derived(shellState.telegramSdkStatus);
  const telegramMiniAppInitData = $derived(shellState.telegramMiniAppInitData);
  const telegramHasLaunchParams = $derived(shellState.telegramHasLaunchParams);
  const mode = $derived(shellState.mode);
  const screen = $derived(shellState.screen);
  const data: WebappData | null = $derived(
    asWebappRecordOrNull(shellState.data) as WebappData | null
  );
  const user: UserProfile = $derived(asWebappRecord(data?.user) as UserProfile);
  const isAdmin = $derived(Boolean(user?.is_admin));
  const publicInstallSubscription: SubscriptionView | null = $derived(
    asWebappRecordOrNull(shellState.publicInstallSubscription) as SubscriptionView | null
  );
  const guestLanguage = $derived(shellState.guestLanguage);
  const emailAvatarUrl = $derived(shellState.emailAvatarUrl);
  const adminBundleApi: WebappRecord | null = $derived(
    asWebappRecordOrNull(shellState.adminBundleApi)
  );
  const adminBundleError = $derived(shellState.adminBundleError);
  const adminMountTarget = $derived(shellState.adminMountTarget);
  const adminActiveSection = $derived(shellState.adminActiveSection);
  const tg: TelegramWebApp | null = $derived(shellState.tg);
  const demoAuthLogin = $derived(shellState.demoAuthLogin);
  const appActions: AppActionRuntime = $derived(shellState.appActions as AppActionRuntime);
  const telegramRuntime = createTelegramRuntime<TelegramWebApp | null>({
    scriptUrl: TELEGRAM_WEBAPP_SCRIPT_URL,
    bootTimeoutMs: TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    actionTimeoutMs: TELEGRAM_SDK_ACTION_TIMEOUT_MS,
    miniAppAuthTimeoutMs: TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS,
  });
  const telegramSdk = telegramRuntime.telegramSdk;
  const readTelegramMiniAppInitDataFromLocation = telegramRuntime.readInitDataFromLocation;
  const hasTelegramLaunchParams = telegramRuntime.hasLaunchParams;
  const loadTelegramSdk = telegramRuntime.load;
  function initialTelegram(): TelegramWebApp | null {
    return tg;
  }

  const initialTg = initialTelegram();
  const { openAppLaunchTarget, openAppLink, openExternalLink, refreshAppLaunchTarget } =
    createExternalLinkRuntime({
      assignLocation: (url) => window.location.assign(url),
      getCurrentLang: () => currentLang,
      hasTelegramLaunchParams,
      refreshTelegram: telegramRuntime.refreshTelegram,
    });
  const i18n = createI18n({
    messages: I18N,
    defaultLang: "ru",
    getLang: () => user?.language_code || guestLanguage || CFG.language || "ru",
  });
  const normalizeLangCode = i18n.normalizeLangCode;
  const t = i18n.t;
  const termUnitLabel = i18n.termUnitLabel;
  const languageName = i18n.languageName;
  $effect(() => {
    shellState.telegramHasLaunchParams = hasTelegramLaunchParams();
  });
  const appFactories = createAppFactories({
    CFG,
    MOCK,
    MOCK_SOURCE,
    adminBundleApi: () => adminBundleApi,
    adminBundleError: () => adminBundleError,
    canUseInstallGuides,
    cleanDocsDemoRouteQuery,
    currentSearchParams,
    csrfCookieName: CSRF_COOKIE_NAME,
    docsDemoParentSearchParams,
    getAppActions: () => appActions,
    getChangeConfirmOpen: () => changeConfirmOpen,
    getChangeModalOpen: () => changeModalOpen,
    getCurrentLang: () => currentLang,
    getData: () => data,
    getDemoAuthLogin: () => Boolean(demoAuthLogin),
    getDeviceTopupModalOpen: () => deviceTopupModalOpen,
    getIsAdmin: () => isAdmin,
    getMethods: () => methods,
    getPaymentModalOpen: () => paymentModalOpen,
    getPlans: () => plans,
    getRuntimeMockApi: () => runtimeMockApi,
    getScreen: () => screen,
    getSingleTariffMode: () => singleTariffMode,
    getSubscription: () => subscription,
    getTariffCatalog: () => tariffCatalog,
    getTariffMode: () => tariffMode,
    getTelegramMiniAppInitData: () => telegramMiniAppInitData,
    getTelegramNotificationsNeedPrompt: () => telegramNotificationsNeedPrompt,
    getTelegramOAuthClientId: () => telegramOAuthClientId,
    getTg: () => tg,
    getTopupModalOpen: () => topupModalOpen,
    getUser: () => user,
    hasEmailCodeLoginDeeplink,
    hasTelegramLaunchParams,
    initialTg,
    isDocsDemo,
    loadData,
    loadTelegramSdk,
    manualLogoutFlagKey: MANUAL_LOGOUT_FLAG_KEY,
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
    telegramNotificationsResumeCooldownMs: TELEGRAM_NOTIFICATIONS_RESUME_REFRESH_COOLDOWN_MS,
    telegramSdk,
    tick,
    updateI18nMessages: (messages) => {
      i18n.mergeMessages(messages);
    },
  });
  const {
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
    dataClient,
    demoAuth,
    devicesStore,
    emailAvatarSync,
    hydrateSupportUnread,
    installGuidesStore,
    loadSectionData,
    resumeLifecycle,
    setPasswordLoginMode,
    stopPendingActivationWatch,
    supportStore,
    syncBodyScrollLock,
    syncLoadedRoute,
  } = appFactories;

  const authState = $derived(authStore);
  const authStatus = $derived(authState.authStatus);
  const authBusy = $derived(Boolean(authState.authBusy));
  const telegramLoginBusy = $derived(Boolean(authState.telegramLoginBusy));
  const billingState = $derived(billingStore);
  const paymentModalOpen = $derived(Boolean(billingState.paymentModalOpen));
  const selectedTariffKey = $derived(String(billingState.selectedTariffKey || ""));
  const selectedPlan = $derived(billingState.selectedPlan);
  const topupModalOpen = $derived(Boolean(billingState.topupModalOpen));
  const topupKind = $derived(billingState.topupKind);
  const deviceTopupModalOpen = $derived(Boolean(billingState.deviceTopupModalOpen));
  const changeModalOpen = $derived(Boolean(billingState.changeModalOpen));
  const changeConfirmOpen = $derived(Boolean(billingState.changeConfirmOpen));
  const linkEmailOpen = $derived(Boolean(accountStore.linkEmailOpen));
  const setPasswordOpen = $derived(Boolean(accountStore.setPasswordOpen));
  const languageBusy = $derived(Boolean(accountStore.languageBusy));
  const trialActivationResult = $derived(actionsStore.trialActivationResult);

  const shellView: AppShellView = $derived(
    computeAppShellView({
      authBusy,
      authStatus,
      cfg: CFG,
      data,
      emailAvatarUrl,
      fallbackBrandTitle: FALLBACK_BRAND_TITLE,
      guestLanguage,
      hasTelegramLaunchParams: () => telegramHasLaunchParams,
      i18nMessages: I18N,
      isDemoAuthMock: () => demoAuth.isDemoAuthMock(),
      languageName,
      mockData: MOCK_DATA,
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
    })
  );

  const telegramNotificationsNeedPrompt = $derived(
    shellView.accountView.telegramNotificationsNeedPrompt
  );
  const brandTitle = $derived(shellView.appDataView.brandTitle);
  const devicesEnabled = $derived(shellView.appDataView.devicesEnabled);
  const emailAuthEnabled = $derived(shellView.appDataView.emailAuthEnabled);
  const faviconBrand = $derived(shellView.appDataView.faviconBrand);
  const installGuidesEnabled = $derived(shellView.appDataView.installGuidesEnabled);
  const methods = $derived(shellView.appDataView.methods);
  const plans = $derived(shellView.appDataView.plans);
  const subscription = $derived(shellView.appDataView.subscription);
  const supportEnabled = $derived(shellView.appDataView.supportEnabled);
  const selectedTariffPlans = $derived(shellView.billingView.selectedTariffPlans);
  const singleTariffMode = $derived(shellView.billingView.singleTariffMode);
  const tariffCatalog = $derived(shellView.billingView.tariffCatalog);
  const tariffMode = $derived(shellView.billingView.tariffMode);
  const currentLang = $derived(shellView.currentLang);
  const telegramOAuthClientId = $derived(shellView.telegramOAuthClientId);
  const effectiveThemeEntry = $derived(shellView.themeView.effectiveThemeEntry);
  const resolvedThemeKey = $derived(shellView.themeView.resolvedThemeKey);
  const shellStyle = $derived(shellView.themeView.shellStyle);
  const shellThemeCssHref = $derived(shellView.themeView.shellThemeCssHref);
  const toastTheme = $derived(shellView.themeView.toastTheme);
  const appModeViewState = $derived({
    ...shellState,
    cfg: CFG,
    languageBusy,
    publicInstallSubscription,
    telegramPlatform: tg?.platform || "",
  });

  $effect(() => {
    shellState.demoAuthLogin = shellView.demoAuthLogin;
    shellState.telegramMiniAppInitData = shellView.telegramMiniAppInitData;
  });

  $effect(() => {
    supportStore.setActive(Boolean(mode === "app" && screen === "support" && supportEnabled));
  });

  $effect(() => {
    applyThemeDocumentEffects(effectiveThemeEntry);
    syncThemeGoogleFonts(effectiveThemeEntry);
  });

  $effect(() => {
    if (screen === "admin" && !isAdmin) {
      shellState.screen = "settings";
      shellState.activeTab = "settings";
    }
  });

  $effect(() => {
    applyFavicon(faviconBrand);
    applyDocumentTitle(brandTitle);
  });

  $effect(() => {
    syncBodyScrollLock(
      paymentModalOpen ||
        changeModalOpen ||
        changeConfirmOpen ||
        topupModalOpen ||
        deviceTopupModalOpen ||
        (emailAuthEnabled && linkEmailOpen) ||
        (emailAuthEnabled && setPasswordOpen)
    );
  });

  $effect(() => {
    closeDisabledEmailAuthDialogs({
      closeLinkEmailDialog: () => accountStore.closeLinkEmailDialog(),
      closeSetPasswordDialog: () => accountStore.closeSetPasswordDialog(),
      emailAuthEnabled,
      linkEmailOpen,
      setPasswordOpen,
    });
  });

  $effect(() => {
    syncShellBillingSelection({
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
        paymentStep: billingState.paymentStep,
        selectedMethod: billingState.selectedMethod,
        selectedPlan,
        selectedTariffKey,
      },
    });
  });

  $effect(() => {
    syncShellEmailAvatar({
      email: user?.email,
      emailAvatarSync,
      setEmailAvatarUrl: (url) => {
        shellState.emailAvatarUrl = url;
      },
    });
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
    setPasswordLoginMode,
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
    dataClientLoadData: (options) => dataClient.loadData(options),
    getModalState: () => ({
      changeModalOpen,
      deviceTopupModalOpen,
      topupKind,
      topupModalOpen,
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

  shellState.appActions = createShellAppActions({
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
    externalLinkActions: {
      openAppLaunchTarget,
      openAppLink,
      openExternalLink,
      refreshAppLaunchTarget,
    },
    getRoutePathname: routePathnameFromLocation,
    getSelectedPlan: () => selectedPlan,
    getShellView: () => shellView,
    getTrialActivationResult: () => trialActivationResult,
    installGuidesStore,
    loadData,
    refreshTelegram: telegramRuntime.refreshTelegram,
    routePrefix,
    showToast,
    supportStore,
    syncAppSectionPath,
    t,
  });

  const adminPanelProps: AdminPanelProps = $derived(
    buildAppAdminPanelProps({
      adminActiveSection,
      adminRuntime,
      api,
      appActions,
      cfg: CFG,
      getShellView: () => shellView,
      initialAdminSectionFromLocation,
      languageBusy,
      onLanguageChange: accountStore.updateAccountLanguage,
      routePathnameFromLocation,
      routePrefix,
      screen,
      showToast,
      t,
    })
  );

  let lastAdminMountTarget: HTMLElement | null = null;
  let lastAdminMountShouldMount = false;
  let lastAdminMountProps: AdminPanelProps | null = null;

  function sameAdminMountProps(left: AdminPanelProps | null, right: AdminPanelProps): boolean {
    if (!left) return false;
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every((key) => Object.is(left[key], right[key]))
    );
  }

  $effect(() => {
    const shouldMount = Boolean(
      screen === "admin" && isAdmin && adminBundleApi && adminMountTarget
    );
    const target = adminMountTarget;
    if (
      target === lastAdminMountTarget &&
      shouldMount === lastAdminMountShouldMount &&
      sameAdminMountProps(lastAdminMountProps, adminPanelProps)
    ) {
      return;
    }
    lastAdminMountTarget = target;
    lastAdminMountShouldMount = shouldMount;
    lastAdminMountProps = { ...adminPanelProps };
    adminRuntime.syncAdminMount({ props: adminPanelProps, shouldMount, target });
  });

  async function loadData(options: AppLoadDataOptions = {}): Promise<WebappData> {
    return appLoadExecutor.loadData(options);
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
      <PreviewBoardComponent config={CFG} mockData={MOCK_DATA} />
    {:else}
      <AppModeContent
        stores={appFactories}
        {shellView}
        {appActions}
        viewState={appModeViewState}
        controls={{ ...appFactories, t, termUnitLabel }}
        bind:adminMountTarget={shellState.adminMountTarget}
        bind:languageMenuOpen={shellState.languageMenuOpen}
        bind:screen={shellState.screen}
      />
    {/if}
  {/key}
</Tooltip.Provider>
