<script>
  import { onMount, setContext, tick } from "svelte";
  import { createAuthStore } from "./lib/webapp/stores/authStore.js";
  import { createBillingStore } from "./lib/webapp/stores/billingStore.js";
  import { createDevicesStore } from "./lib/webapp/stores/devicesStore.js";
  import { createInstallGuidesStore } from "./lib/webapp/stores/installGuidesStore.js";
  import { createSupportStore } from "./lib/webapp/stores/supportStore.js";
  import { createAccountStore } from "./lib/webapp/stores/accountStore.js";
  import { Tooltip } from "$components/ui/primitives.js";
  import { CheckCircle2 } from "$components/ui/icons.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import Button from "$components/ui/button.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import WebAppShell from "./webapp/WebAppShell.svelte";
  import AuthScreen from "./webapp/auth/AuthScreen.svelte";
  import PaymentDialogs from "./webapp/PaymentDialogs.svelte";
  import TariffDialogs from "./webapp/TariffDialogs.svelte";
  import AppLaunchScreen from "./webapp/screens/AppLaunchScreen.svelte";
  import DevicesScreen from "./webapp/screens/DevicesScreen.svelte";
  import HomeScreen from "./webapp/screens/HomeScreen.svelte";
  import InstallGuideScreen from "./webapp/screens/InstallGuideScreen.svelte";
  import InviteScreen from "./webapp/screens/InviteScreen.svelte";
  import SettingsScreen from "./webapp/screens/SettingsScreen.svelte";
  import SupportScreen from "./webapp/screens/SupportScreen.svelte";
  import SupportTicketScreen from "./webapp/screens/SupportTicketScreen.svelte";
  import TrialActivationScreen from "./webapp/screens/TrialActivationScreen.svelte";

  import {
    LANGUAGE_FLAGS,
    LANGUAGE_LABELS,
    MANUAL_LOGOUT_FLAG_KEY,
    TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS,
    TELEGRAM_SDK_ACTION_TIMEOUT_MS,
    TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    TELEGRAM_WEBAPP_SCRIPT_URL,
    uniqueLanguageCodes,
    WEBAPP_LANGUAGE_ORDER,
  } from "./lib/webapp/constants.js";

  import {
    applyFavicon,
    applyDocumentTitle,
    normalizeBrand,
    readJsonScript,
    structuredCloneSafe,
  } from "./lib/webapp/browser.js";
  import {
    buildExternalAppLaunchUrl,
    hasControlChars,
    isExternalAppLaunchPath,
    isHttpUrl,
    openUrlWithHiddenAnchor,
    readExternalAppLaunchTarget,
  } from "./lib/webapp/appLinks.js";
  import { createApiClient } from "./lib/webapp/publicApi.js";
  import { createI18n } from "./lib/webapp/i18n.js";
  import { normalizedEmail, telegramName } from "./lib/webapp/formatters.js";
  import { activeTariffName, buildTariffCatalog } from "./lib/webapp/tariffs.js";
  import { premiumTrafficPercent, trafficPercent } from "./lib/webapp/traffic.js";
  import {
    findThemeEntry,
    resolveEffectiveThemeKey,
    themeCssHref,
    themeEntryToInlineStyle,
    themeRootClass,
  } from "./lib/webapp/themeStyle.js";

  /** Used-traffic percent from which top-up modals and CTAs unlock in the web app home screen */
  const TRAFFIC_TOPUP_UNLOCK_PERCENT = 80;
  const ACTIVATION_HANDOFF_STORAGE_KEY = "rw_webapp_activation_handoff_v1";
  const ACTIVATION_HANDOFF_TTL_MS = 48 * 60 * 60 * 1000;
  const ACTIVATION_PENDING_WATCH_INTERVAL_MS = 2000;
  const ACTIVATION_PENDING_WATCH_MAX_ATTEMPTS = 45;
  const ACTIVATION_RESUME_CHECK_COOLDOWN_MS = 1500;
  const TELEGRAM_NOTIFICATIONS_RESUME_REFRESH_COOLDOWN_MS = 1500;
  import {
    activationPaymentFailed,
    createActivationHandoff,
  } from "./lib/webapp/activationHandoff.js";
  import { buildGravatarUrl } from "./lib/webapp/gravatar.js";
  import { createBillingActions } from "./lib/webapp/billingActions.js";
  import { invalidateWebappTariffOptionCaches } from "./lib/webapp/billingOptionCache.js";
  import { runWebappBoot } from "./lib/webapp/webappBoot.js";
  import {
    clearManualLogoutFlag as clearManualLogoutFlagInStorage,
    clearStoredToken,
    CSRF_COOKIE_NAME,
    isManuallyLoggedOut as readManualLogoutFlag,
    markManualLogout as markManualLogoutInStorage,
    readCookie,
  } from "./lib/webapp/session.js";
  import { createTelegramSdk } from "./lib/webapp/telegramSdk.js";
  import {
    adminPaymentIdFromPath,
    adminPaymentsUserIdFromPath,
    adminSectionFromPath,
    adminUserIdFromPath,
    normalizeAdminSection,
    normalizeSection,
    publicInstallTokenFromPath,
    sectionFromPath,
    supportTicketIdFromPath,
    syncSectionPath,
    withRoutePrefix,
  } from "./lib/webapp/routes.js";

  export let mockRuntime = null;

  const EMPTY_MOCK = {
    config: {
      title: "/minishop",
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
  const MOCK_SOURCE = mockRuntime?.source || EMPTY_MOCK;
  const previewBoardComponent = mockRuntime?.PreviewBoard || null;
  const isDocsDemo = mockRuntime?.docsDemo === true;
  const routePrefix = isDocsDemo ? "/demo/runtime" : "";
  let docsDemoParentRouteConsumed = false;
  const query = new URLSearchParams(window.location.search);
  const isAppLaunchRoute = isExternalAppLaunchPath(window.location.pathname);
  mockRuntime?.applyPreviewMock?.(query.get("mock"));
  const isPreviewBoard = Boolean(previewBoardComponent) && query.get("preview") === "all";
  const injectedConfig = readJsonScript("webapp-config");
  const injectedI18n = readJsonScript("i18n");
  const isLocalShell =
    window.location.protocol === "file:" ||
    ["", "localhost", "127.0.0.1"].includes(window.location.hostname);
  const MOCK =
    mockRuntime?.mockApi && !injectedConfig && (isLocalShell || isDocsDemo) ? MOCK_SOURCE : null;
  const CFG = {
    ...MOCK_SOURCE.config,
    ...(MOCK ? MOCK.config : {}),
    ...(injectedConfig || {}),
  };
  const themePreviewKey = String(CFG.themePreviewKey || query.get("theme_preview") || "").trim();
  const I18N = injectedI18n || {};
  let telegramSdkStatus = "idle";
  let telegramMiniAppInitData = "";

  let mode = isAppLaunchRoute ? "appLaunch" : isPreviewBoard ? "preview" : "loading";
  let activeTab = "home";
  let screen = "home";
  let emailLoginDeeplinkConsumed = false;
  let data = isPreviewBoard ? structuredCloneSafe(MOCK_SOURCE.data) : null;
  let appLaunchTarget = isAppLaunchRoute ? readExternalAppLaunchTarget() : "";
  let publicInstallSubscription = null;
  let publicInstallToken = "";
  let trialBusy = false;
  let trialActivationResult = null;
  let trialActivationError = "";
  let activationSuccessDialogOpen = false;
  let activationSuccessUseInstallGuides = false;
  let activationPendingWatchTimer = null;
  let activationPendingWatchAttempts = 0;
  let activationPendingWatchBusy = false;
  let activationResumeRefreshBusy = false;
  let activationResumeLastCheckAt = 0;
  let telegramNotificationsBotOpenedAt = 0;
  let telegramNotificationsResumeRefreshBusy = false;
  let telegramNotificationsResumeLastCheckAt = 0;
  let promoCode = "";
  let promoBusy = false;
  let promoStatus = "";
  let promoIsError = false;
  let promoFieldError = "";
  let toastText = "";
  let toastTimer = null;
  let languageMenuOpen = false;
  let languageClickGuard = false;
  let languageClickGuardArmed = false;
  let languageClickGuardTimer = null;
  let languageClickGuardArmTimer = null;
  let guestLanguage = "";
  let emailAvatarUrl = "";
  let avatarHashToken = "";
  let token = MOCK ? "local-preview" : "";
  let csrfToken = MOCK ? "" : readCookie(CSRF_COOKIE_NAME) || "";
  let scrollLockApplied = false;
  let adminI18nLoaded = false;
  let adminI18nPromise = null;
  let adminBundleApi = null;
  let adminBundlePromise = null;
  let adminBundleError = "";
  let adminMountTarget = null;
  let adminMountHandle = null;
  let adminMountedTarget = null;
  let adminPanelProps = {};
  let adminActiveSection = "stats";
  let tg = null;
  const telegramSdk = createTelegramSdk({
    scriptUrl: TELEGRAM_WEBAPP_SCRIPT_URL,
    bootTimeoutMs: TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    actionTimeoutMs: TELEGRAM_SDK_ACTION_TIMEOUT_MS,
    miniAppAuthTimeoutMs: TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS,
    onStatusChange: (status) => (telegramSdkStatus = status),
    onInitDataChange: (initData) => (telegramMiniAppInitData = initData || ""),
  });
  tg = telegramSdk.refresh();
  telegramSdkStatus = tg ? "ready" : "idle";
  telegramMiniAppInitData = telegramSdk.initData;
  const i18n = createI18n({
    messages: I18N,
    defaultLang: "ru",
    getLang: () => user?.language_code || guestLanguage || CFG.language || "ru",
  });
  const normalizeLangCode = i18n.normalizeLangCode;
  const t = i18n.t;
  const termUnitLabel = i18n.termUnitLabel;
  const languageName = i18n.languageName;
  guestLanguage = normalizeLangCode(CFG.language || "ru");
  const apiClient = createApiClient({
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
  const billing = createBillingActions({
    api: (path, options) => apiClient.api(path, options),
    t: (...args) => t(...args),
  });
  const activationHandoff = createActivationHandoff({
    storageKey: ACTIVATION_HANDOFF_STORAGE_KEY,
    ttlMs: ACTIVATION_HANDOFF_TTL_MS,
  });

  const authStore = createAuthStore({
    publicApi,
    setToken,
    loadData,
    telegramSdk,
    getTg: () => tg,
    t,
    currentLang: () => currentLang,
    clearManualLogoutFlag,
  });
  const billingStore = createBillingStore({
    billing,
    loadData,
    t,
    showToast,
    openExternalLink,
    onSubscriptionActivationPending: rememberActivationPending,
    onSubscriptionActivated: handleSubscriptionActivated,
    tg,
    getTg: () => tg || telegramSdk.refresh(),
    telegramSdk,
  });
  const devicesStore = createDevicesStore({ api, t, showToast });
  const supportStore = createSupportStore({ api, t, showToast, routePrefix });
  const installGuidesStore = createInstallGuidesStore({ api, t, showToast });
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
    telegramSdk,
    getTg: () => tg,
    telegramOAuthClientId: () => telegramOAuthClientId,
    currentLang: () => currentLang,
    normalizeLangCode,
    updateLocalData: (updatedLanguage) => {
      if (!data?.user) return;
      data = { ...data, user: { ...data.user, language_code: updatedLanguage } };
    },
  });

  setContext("authStore", authStore);
  setContext("billingStore", billingStore);
  setContext("devicesStore", devicesStore);
  setContext("supportStore", supportStore);
  setContext("installGuidesStore", installGuidesStore);
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
    topupOptions,
    deviceTopupOptions,
    changeOptions,
    changeConfirmOpen,
    tariffActionBusy,
    payBusy,
  } = $billingStore);
  $: ({
    devicesData,
    devicesLoaded,
    devicesBusy,
    devicesStatus,
    devicesIsError,
    devicesErrorCode,
    deviceConfirmOpen,
    deviceToDisconnect,
    deviceDisconnectBusy,
  } = $devicesStore);
  $: ({
    unreadCount: supportUnreadCount,
    unreadLoading: supportUnreadLoading,
    unreadLoaded: supportUnreadLoaded,
  } = $supportStore);
  $: ({
    linkEmailOpen,
    linkEmailBusy,
    linkTelegramBusy,
    linkEmailPending,
    linkEmailStatus,
    linkEmailIsError,
    linkEmailResendCooldown,
    setPasswordBusy,
    setPasswordIsError,
    setPasswordOpen,
    setPasswordPending,
    setPasswordResendCooldown,
    setPasswordStatus,
    languageBusy,
  } = $accountStore);

  $: brandTitle = CFG.title || "/minishop";
  $: brandEmoji = CFG.logoEmoji || "🫥";
  $: brandEmojiFont = CFG.logoEmojiFont || "system";
  $: brand = normalizeBrand({
    title: brandTitle,
    logoUrl: CFG.logoUseEmoji ? "" : CFG.logoUrl,
    emoji: brandEmoji,
    emojiFont: brandEmojiFont,
  });
  $: faviconBrand = normalizeBrand({
    ...brand,
    logoUrl: String(CFG.faviconUrl || "").trim() || brand.logoUrl,
  });
  $: plans = data?.plans?.length ? data.plans : MOCK_SOURCE.data.plans;
  $: methods = data?.payment_methods?.length ? data.payment_methods : [];
  $: appSettings = data?.settings || MOCK_SOURCE.data.settings;
  $: subscriptionPurchaseDescription = String(
    appSettings?.subscription_purchase_description || ""
  ).trim();
  $: trafficMode = Boolean(appSettings?.traffic_mode);
  $: tariffMode = plans.some((plan) => plan?.tariff_key);
  $: tariffCatalog = buildTariffCatalog(plans);
  $: singleTariffMode = tariffMode && tariffCatalog.length === 1;
  $: hasMultipleTariffs = tariffCatalog.length > 1;
  $: selectedTariff = tariffCatalog.find((tariff) => tariff.key === selectedTariffKey) || null;
  $: selectedTariffPlans = tariffMode
    ? selectedTariffKey
      ? plans.filter((plan) => plan?.tariff_key === selectedTariffKey)
      : []
    : plans;
  $: devicesEnabled = Boolean(appSettings?.my_devices_enabled);
  $: supportEnabled = Boolean(appSettings?.support_tickets_enabled ?? true);
  $: installGuidesEnabled = Boolean(appSettings?.subscription_guides_enabled);
  $: supportStore.setActive(Boolean(mode === "app" && screen === "support" && supportEnabled));
  $: subscription = data?.subscription || MOCK_SOURCE.data.subscription;
  $: hasActiveTariffSubscription = Boolean(
    tariffMode && subscription?.active && subscription?.tariff_key
  );
  $: canChangeTariff = Boolean(hasActiveTariffSubscription && hasMultipleTariffs);
  $: currentTariffName = activeTariffName(subscription, plans);
  $: canOpenRegularTopupModal = Boolean(
    hasActiveTariffSubscription &&
    (subscription?.can_topup_regular_traffic ?? subscription?.can_topup_traffic) &&
    Number(subscription?.traffic_limit_bytes || 0) > 0
  );
  $: canOpenPremiumTopupModal = Boolean(
    hasActiveTariffSubscription &&
    (subscription?.can_topup_premium_traffic ?? subscription?.can_topup_traffic) &&
    Number(subscription?.premium_limit_bytes || 0) > 0
  );
  $: activeTariffCatalogEntry =
    tariffCatalog.find((entry) => entry.key === String(subscription?.tariff_key || "").trim()) ||
    null;
  $: subscriptionIsTrafficTariff = Boolean(
    String(
      subscription?.billing_model || activeTariffCatalogEntry?.billing_model || ""
    ).toLowerCase() === "traffic"
  );
  $: regularTrafficTopupUnlocked = Boolean(
    canOpenRegularTopupModal && trafficPercent(subscription) >= TRAFFIC_TOPUP_UNLOCK_PERCENT
  );
  $: premiumTrafficTopupUnlocked = Boolean(
    canOpenPremiumTopupModal && premiumTrafficPercent(subscription) >= TRAFFIC_TOPUP_UNLOCK_PERCENT
  );
  /** Progress-bar card opens top-up immediately on traffic-only tariffs; period tariffs still need 80% usage */
  $: regularTrafficTopupBarClickable = Boolean(
    canOpenRegularTopupModal &&
    (subscriptionIsTrafficTariff || trafficPercent(subscription) >= TRAFFIC_TOPUP_UNLOCK_PERCENT)
  );
  $: premiumTrafficTopupBarClickable = Boolean(
    canOpenPremiumTopupModal &&
    (subscriptionIsTrafficTariff ||
      premiumTrafficPercent(subscription) >= TRAFFIC_TOPUP_UNLOCK_PERCENT)
  );
  $: user = data?.user || {};
  $: themesCatalog = data?.themes_catalog ||
    CFG.themesCatalog || { default_theme: "dark", themes: [] };
  $: previewThemeAllowed = Boolean(themePreviewKey && (!data?.user || user?.is_admin));
  $: previewThemeEntry = previewThemeAllowed
    ? findThemeEntry(themesCatalog, themePreviewKey)
    : null;
  $: resolvedThemeKey = previewThemeEntry?.key || resolveEffectiveThemeKey(themesCatalog);
  $: activeThemeEntry = findThemeEntry(themesCatalog, resolvedThemeKey);
  $: darkThemeEntry = findThemeEntry(themesCatalog, "dark");
  $: effectiveThemeEntry =
    screen === "admin" && activeThemeEntry?.use_in_admin === false
      ? darkThemeEntry || activeThemeEntry
      : activeThemeEntry;
  $: shellStyle = themeEntryToInlineStyle(effectiveThemeEntry, CFG.primaryColor);
  $: shellToneClass =
    effectiveThemeEntry?.tokens?.color_scheme === "light" ? "theme-light" : "theme-dark";
  $: shellThemeClass = themeRootClass(effectiveThemeEntry);
  $: shellThemeCssHref = themeCssHref(effectiveThemeEntry);
  $: if (typeof document !== "undefined" && effectiveThemeEntry?.tokens) {
    const scheme = effectiveThemeEntry.tokens.color_scheme || "dark";
    document.documentElement.style.colorScheme = scheme;
    const bg = effectiveThemeEntry.tokens.bg;
    if (bg) document.body.style.backgroundColor = bg;
  }
  $: isAdmin = Boolean(user?.is_admin);
  $: if (screen === "admin" && !isAdmin) {
    screen = "settings";
    activeTab = "settings";
  }
  $: referral = data?.referral || MOCK_SOURCE.data.referral;
  $: currentLang = normalizeLangCode(user?.language_code || guestLanguage || CFG.language || "ru");
  $: languageCodes = uniqueLanguageCodes(
    WEBAPP_LANGUAGE_ORDER,
    CFG.languages,
    Object.keys(I18N || {}),
    [currentLang]
  );
  $: languageOptions = languageCodes.map((code) => {
    const serverLanguage = (CFG.languages || []).find((language) => language.code === code);
    return {
      value: code,
      label: serverLanguage?.label || LANGUAGE_LABELS[code] || code.toUpperCase(),
      flag: serverLanguage?.flag || LANGUAGE_FLAGS[code] || "🏳️",
    };
  });
  $: currentLanguageOption =
    languageOptions.find((option) => option.value === currentLang) || languageOptions[0];
  $: userLanguage = languageName(currentLang);
  $: emailLinkStatus = user?.email ? t("wa_settings_linked") : t("wa_settings_email_not_linked");
  $: telegramNotificationsStatus = String(user?.telegram_notifications_status || "unknown");
  $: telegramNotificationsNeedPrompt = Boolean(
    user?.telegram_linked && user?.telegram_notifications_need_prompt
  );
  $: telegramNotificationsStartLink = String(user?.telegram_notifications_start_link || "");
  $: hasUnlinkedIdentity =
    !user?.telegram_linked || !user?.email || telegramNotificationsNeedPrompt;
  $: referralBonusDetails = Array.isArray(referral?.bonus_details) ? referral.bonus_details : [];
  $: referralWelcomeBonusDays = Math.max(0, Number(referral?.welcome_bonus_days || 0));
  $: referralOneBonusPerReferee = Boolean(referral?.one_bonus_per_referee);
  $: telegramProfileName = telegramName(user);
  $: profileEmail = user?.email || t("wa_settings_email_not_linked");
  $: profileTelegramId = user?.telegram_id ? `TG ID ${user.telegram_id}` : t("wa_tg_id_not_linked");
  $: profileAvatarUrl = user?.telegram_photo_url || emailAvatarUrl || "";
  $: privacyPolicyUrl = String(CFG.privacyPolicyUrl || "").trim();
  $: userAgreementUrl = String(CFG.userAgreementUrl || "").trim();
  $: supportUrl = String(appSettings?.support_url || CFG.supportUrl || "").trim();
  $: telegramLoginBotId = Number(CFG.telegramLoginBotId || 0);
  $: telegramOAuthClientId = Number(CFG.telegramOAuthClientId || telegramLoginBotId || 0);
  $: telegramMiniAppInitData = tg?.initData || readTelegramMiniAppInitDataFromLocation();
  $: telegramMiniAppAuthAvailable = Boolean(telegramMiniAppInitData);
  $: telegramMiniAppContext = hasTelegramLaunchParams();
  $: demoAuthLogin = MOCK && isDemoAuthMock();
  $: telegramLoginUnavailable =
    !demoAuthLogin &&
    !telegramMiniAppAuthAvailable &&
    !telegramOAuthClientId &&
    telegramSdkStatus !== "loading";
  $: telegramLoginChecking =
    telegramLoginBusy || (authBusy && authStatus === t("wa_auth_checking_telegram"));
  $: telegramLoginLabel = telegramLoginUnavailable
    ? t("wa_login_telegram_unavailable_button")
    : telegramLoginChecking
      ? t("wa_auth_checking_telegram")
      : t("wa_login_telegram_button");
  $: telegramLoginUnavailableMessage = demoAuthLogin
    ? ""
    : telegramLoginUnavailable && telegramSdkStatus === "unavailable"
      ? t("wa_auth_telegram_unavailable")
      : telegramLoginUnavailable
        ? t("wa_auth_telegram_not_configured")
        : "";
  $: applyFavicon(faviconBrand);
  $: applyDocumentTitle(brandTitle);
  $: syncBodyScrollLock(
    paymentModalOpen ||
      changeModalOpen ||
      changeConfirmOpen ||
      topupModalOpen ||
      deviceTopupModalOpen ||
      linkEmailOpen ||
      setPasswordOpen
  );
  $: if (!tariffMode && !$billingStore.selectedPlan && plans.length) {
    billingStore.update((s) => ({ ...s, selectedPlan: plans[Math.min(1, plans.length - 1)] }));
  }
  $: if (singleTariffMode && tariffCatalog[0]?.key && selectedTariffKey !== tariffCatalog[0].key) {
    const tariffKey = tariffCatalog[0].key;
    billingStore.update((s) => ({
      ...s,
      selectedTariffKey: tariffKey,
      selectedPlan: plans.find((plan) => plan?.tariff_key === tariffKey) || null,
      paymentStep: s.paymentStep === "tariff" ? "checkout" : s.paymentStep,
    }));
  }
  $: if (
    tariffMode &&
    selectedTariffKey &&
    !tariffCatalog.some((tariff) => tariff.key === selectedTariffKey)
  ) {
    billingStore.update((s) => ({
      ...s,
      selectedTariffKey: "",
      selectedPlan: null,
      paymentStep: singleTariffMode ? "checkout" : "tariff",
    }));
  }
  $: if (
    tariffMode &&
    selectedTariffKey &&
    (!selectedPlan || selectedPlan.tariff_key !== selectedTariffKey)
  ) {
    billingStore.update((s) => ({ ...s, selectedPlan: selectedTariffPlans[0] || null }));
  }
  $: if (methods.length) {
    const selectedMethodAvailable = methods.some(
      (method) => method.id === $billingStore.selectedMethod
    );
    if (!$billingStore.selectedMethod || !selectedMethodAvailable) {
      billingStore.update((s) => ({ ...s, selectedMethod: methods[0].id }));
    }
  } else if ($billingStore.selectedMethod) {
    billingStore.update((s) => ({ ...s, selectedMethod: "" }));
  }
  $: {
    const emailKey = normalizedEmail(user?.email);
    if (!emailKey) {
      avatarHashToken = "";
      emailAvatarUrl = "";
    } else if (avatarHashToken !== emailKey) {
      avatarHashToken = emailKey;
      buildGravatarUrl(emailKey).then((url) => {
        if (avatarHashToken === emailKey) emailAvatarUrl = url;
      });
    }
  }

  function canUseInstallGuides(settings = appSettings, sub = subscription) {
    const enabled =
      settings === appSettings
        ? installGuidesEnabled
        : Boolean(settings?.subscription_guides_enabled);
    return Boolean(enabled && sub?.active);
  }

  function hasPendingActivationHandoff(payload = data) {
    return activationHandoff.hasPending(payload);
  }

  function rememberActivationPending(context = {}) {
    activationHandoff.rememberPending(context, data);
  }

  function clearPendingActivationHandoff() {
    activationHandoff.clearPending();
  }

  async function maybeShowActivationSuccessDialog(context = {}) {
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
    if (activationPendingWatchTimer) {
      window.clearTimeout(activationPendingWatchTimer);
      activationPendingWatchTimer = null;
    }
    activationPendingWatchAttempts = 0;
    activationPendingWatchBusy = false;
  }

  function schedulePendingActivationWatch() {
    if (activationPendingWatchTimer || !hasPendingActivationHandoff()) return;
    activationPendingWatchTimer = window.setTimeout(() => {
      activationPendingWatchTimer = null;
      void checkPendingActivationWatch();
    }, ACTIVATION_PENDING_WATCH_INTERVAL_MS);
  }

  function startPendingActivationWatch() {
    if (
      mode !== "app" ||
      !hasPendingActivationHandoff() ||
      activationSuccessDialogOpen ||
      screen === "admin"
    ) {
      stopPendingActivationWatch();
      return;
    }
    if (activationPendingWatchTimer || activationPendingWatchBusy) return;
    schedulePendingActivationWatch();
  }

  async function checkPendingActivationWatch() {
    if (activationPendingWatchBusy) return;
    if (
      mode !== "app" ||
      !hasPendingActivationHandoff() ||
      activationSuccessDialogOpen ||
      screen === "admin"
    ) {
      stopPendingActivationWatch();
      return;
    }
    if (activationPendingWatchAttempts >= ACTIVATION_PENDING_WATCH_MAX_ATTEMPTS) {
      stopPendingActivationWatch();
      return;
    }

    const state = activationHandoff.read();
    const pending = state.pending;
    activationPendingWatchAttempts += 1;
    activationPendingWatchBusy = true;
    try {
      let shouldRefreshProfile = !pending?.paymentId;
      if (pending?.paymentId && billing.fetchPaymentStatus) {
        const paymentStatus = await billing.fetchPaymentStatus(pending.paymentId);
        if (paymentStatus?.paid || paymentStatus?.status === "succeeded") {
          shouldRefreshProfile = true;
        } else if (activationPaymentFailed(paymentStatus)) {
          clearPendingActivationHandoff();
          stopPendingActivationWatch();
          return;
        }
      }
      if (shouldRefreshProfile) {
        await loadData({ fresh: true });
        const shown = await maybeShowActivationSuccessDialog({
          source: "watch",
          paymentId: pending?.paymentId,
        });
        if (shown || !hasPendingActivationHandoff()) {
          stopPendingActivationWatch();
          return;
        }
      }
    } catch (_error) {
      void _error;
    } finally {
      activationPendingWatchBusy = false;
    }
    schedulePendingActivationWatch();
  }

  function canRefreshPendingActivationOnResume() {
    return Boolean(
      mode === "app" &&
      screen !== "admin" &&
      !activationSuccessDialogOpen &&
      !paymentModalOpen &&
      !topupModalOpen &&
      !deviceTopupModalOpen &&
      !changeModalOpen &&
      !changeConfirmOpen &&
      hasPendingActivationHandoff()
    );
  }

  async function refreshPendingActivationOnResume() {
    if (!canRefreshPendingActivationOnResume()) return;
    const now = Date.now();
    if (
      activationResumeRefreshBusy ||
      now - activationResumeLastCheckAt < ACTIVATION_RESUME_CHECK_COOLDOWN_MS
    ) {
      return;
    }
    activationResumeLastCheckAt = now;
    activationResumeRefreshBusy = true;
    try {
      await loadData({ fresh: true });
      const shown = await maybeShowActivationSuccessDialog({ source: "resume" });
      if (!shown) startPendingActivationWatch();
    } catch (_error) {
      void _error;
    } finally {
      activationResumeRefreshBusy = false;
    }
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

  function refreshAppLaunchTarget() {
    appLaunchTarget = readExternalAppLaunchTarget();
    return appLaunchTarget;
  }

  function openAppLaunchTarget(nextTarget = "") {
    const target = String(nextTarget || refreshAppLaunchTarget() || "").trim();
    if (!target) return false;
    appLaunchTarget = target;
    openUrlWithHiddenAnchor(target);
    return true;
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
      const shareToken = publicInstallTokenFromPath(window.location.pathname);
      if (shareToken) {
        void loadPublicInstall(shareToken);
        return;
      }
      if (mode === "publicInstall") {
        void boot();
        return;
      }
      const currentQuery = currentSearchParams();
      const section =
        isDocsDemo && currentQuery.get("screen")
          ? normalizeSection(currentQuery.get("screen"))
          : sectionFromPath(routePathnameFromLocation(), routePrefix);
      if (mode === "login") {
        setPasswordLoginMode(isPasswordLoginPath(), true);
        screen = "login";
        return;
      }
      if (mode === "app") {
        if (section === "admin" && isAdmin) {
          adminActiveSection = isDocsDemo
            ? initialAdminSectionFromLocation()
            : adminSectionFromPath(routePathnameFromLocation(), routePrefix);
          const pathAtStart = window.location.pathname;
          void Promise.all([ensureI18nScope("admin"), ensureAdminBundle()])
            .then(() => {
              if (sectionFromPath(routePathnameFromLocation(), routePrefix) !== "admin") return;
              if (window.location.pathname !== pathAtStart) return;
              activeTab = "settings";
              screen = "admin";
            })
            .catch(() => {
              showToast(t("wa_unavailable"));
            });
          return;
        }
        const nextSection =
          section === "devices" && !devicesEnabled
            ? "home"
            : section === "support" && !supportEnabled
              ? "home"
              : section === "install" && !canUseInstallGuides()
                ? "home"
                : section;
        activeTab = nextSection === "install" || nextSection === "trial" ? "home" : nextSection;
        screen = nextSection;
        if (nextSection === "devices") devicesStore.loadDevices(devicesEnabled);
        if (nextSection === "support") {
          supportStore.loadList();
          supportStore.startPolling({ includeList: true });
        }
        if (nextSection === "install") installGuidesStore.load(true);
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
      syncBodyScrollLock(false);
      destroyAdminMount();
    };
  });

  function syncBodyScrollLock(locked) {
    if (typeof document === "undefined") return;
    if (locked && !scrollLockApplied) {
      document.body.style.overflow = "hidden";
      scrollLockApplied = true;
      return;
    }
    if (!locked && scrollLockApplied) {
      document.body.style.overflow = "";
      scrollLockApplied = false;
    }
  }

  function clearLanguageClickGuard() {
    if (languageClickGuardTimer) {
      window.clearTimeout(languageClickGuardTimer);
      languageClickGuardTimer = null;
    }
    if (languageClickGuardArmTimer) {
      window.clearTimeout(languageClickGuardArmTimer);
      languageClickGuardArmTimer = null;
    }
    languageClickGuard = false;
    languageClickGuardArmed = false;
  }

  function setLanguageMenuOpen(open) {
    languageMenuOpen = Boolean(open);
    clearLanguageClickGuard();
    if (languageMenuOpen) {
      languageClickGuard = true;
      languageClickGuardArmTimer = window.setTimeout(() => {
        languageClickGuardArmed = true;
        languageClickGuardArmTimer = null;
      }, 220);
      return;
    }
    languageClickGuard = true;
    languageClickGuardArmed = false;
    languageClickGuardTimer = window.setTimeout(() => {
      languageClickGuard = false;
      languageClickGuardTimer = null;
    }, 260);
  }

  function updateGuestLanguage(nextValue) {
    const language = normalizeLangCode(nextValue);
    setLanguageMenuOpen(false);
    if (!language || language === currentLang) return;
    guestLanguage = language;
  }

  function readTelegramMiniAppInitDataFromLocation() {
    return telegramSdk.readInitDataFromLocation();
  }

  function hasTelegramLaunchParams() {
    return telegramSdk.hasLaunchParams();
  }

  function loadTelegramSdk(timeoutMs = TELEGRAM_SDK_BOOT_TIMEOUT_MS) {
    return telegramSdk.load(timeoutMs).then((value) => {
      tg = value;
      telegramMiniAppInitData = telegramSdk.initData;
      return value;
    });
  }

  async function ensureI18nScope(scope) {
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

  function resolveWebappAssetPath(configValue, fallbackName) {
    const raw = String(configValue || "").trim() || fallbackName;
    if (/^(?:https?:)?\/\//i.test(raw) || raw.startsWith("data:")) return fallbackName;
    if (window.location.protocol === "file:" && raw.startsWith("/")) return raw.slice(1);
    return raw.startsWith("/") ? raw : `/${raw}`;
  }

  function appendStylesheetOnce(id, href) {
    if (!href || document.getElementById(id)) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const link = document.createElement("link");
      link.id = id;
      link.rel = "stylesheet";
      link.href = href;
      link.onload = () => resolve();
      link.onerror = () => {
        link.remove();
        reject(new Error(`stylesheet_load_failed:${href}`));
      };
      document.head.appendChild(link);
    });
  }

  function appendScriptOnce(id, src) {
    if (!src || document.getElementById(id)) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.id = id;
      script.src = src;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        script.remove();
        reject(new Error(`script_load_failed:${src}`));
      };
      document.head.appendChild(script);
    });
  }

  async function appendStylesheetWithFallback(id, href, fallbackName) {
    const fallbackHref = resolveWebappAssetPath("", fallbackName);
    try {
      await appendStylesheetOnce(id, href);
    } catch (error) {
      if (!fallbackHref || href === fallbackHref) throw error;
      await appendStylesheetOnce(id, fallbackHref);
    }
  }

  async function appendScriptWithFallback(id, src, fallbackName) {
    const fallbackSrc = resolveWebappAssetPath("", fallbackName);
    try {
      await appendScriptOnce(id, src);
    } catch (error) {
      if (!fallbackSrc || src === fallbackSrc) throw error;
      await appendScriptOnce(id, fallbackSrc);
    }
  }

  function readAdminBundleApi() {
    const bundle = window.SubscriptionWebAppAdmin;
    return bundle?.mount ? bundle : null;
  }

  async function ensureAdminBundle() {
    if (adminBundleApi) return true;
    if (adminBundlePromise) return adminBundlePromise;

    const existing = readAdminBundleApi();
    if (existing) {
      adminBundleApi = existing;
      return true;
    }

    adminBundleError = "";
    adminBundlePromise = (async () => {
      const cssHref = resolveWebappAssetPath(CFG.adminCssAsset, "subscription_webapp_admin.css");
      const jsSrc = resolveWebappAssetPath(CFG.adminJsAsset, "subscription_webapp_admin.js");
      await appendStylesheetWithFallback(
        "subscription-webapp-admin-css",
        cssHref,
        "subscription_webapp_admin.css"
      );
      await appendScriptWithFallback(
        "subscription-webapp-admin-js",
        jsSrc,
        "subscription_webapp_admin.js"
      );
      const loaded = readAdminBundleApi();
      if (!loaded) throw new Error("admin_bundle_missing_mount");
      adminBundleApi = loaded;
      return true;
    })()
      .catch((error) => {
        adminBundleError = error?.message || "admin_bundle_load_failed";
        throw error;
      })
      .finally(() => {
        adminBundlePromise = null;
      });

    return adminBundlePromise;
  }

  function destroyAdminMount() {
    if (!adminMountHandle) return;
    adminMountHandle.destroy?.();
    adminMountHandle = null;
    adminMountedTarget = null;
  }

  function currentMockMode() {
    if (!MOCK) return "";
    const currentMock = currentSearchParams().get("mock");
    if (currentMock) return String(currentMock).trim().toLowerCase();
    const parentMock = docsDemoParentSearchParams()?.get("mock");
    return String(parentMock || "")
      .trim()
      .toLowerCase();
  }

  function isDemoAuthMock() {
    return ["auth", "login", "register"].includes(currentMockMode());
  }

  function prepareDemoAuthState() {
    const authDemo = MOCK_SOURCE.data?.auth_demo || {};
    const email = String(authDemo.email || "3252a8@proton.me").trim();
    authStore.update((s) => ({
      ...s,
      authStatus: "",
      authIsError: false,
      authBusy: false,
      authResendCooldown: 0,
      email,
      emailPassword: String(authDemo.password || ""),
      pendingEmail: "",
      emailCode: "",
      passwordLoginMode: false,
      passwordLoginFallback: false,
      loginEmailFieldError: "",
      loginEmailTooltipOpen: false,
      telegramLoginBusy: false,
    }));
  }

  async function openLoginTelegram() {
    if (demoAuthLogin) {
      const authDemo = MOCK_SOURCE.data?.auth_demo || {};
      await authStore.finalizeTelegramAuth(
        {
          id: Number(authDemo.telegram_id || 7410865527),
          username: authDemo.telegram_username || "u3252a8",
          first_name: authDemo.telegram_first_name || "3252a8",
          last_name: authDemo.telegram_last_name || "",
        },
        "auth_data"
      );
      return;
    }
    await authStore.openTelegramLogin(telegramOAuthClientId, () => telegramMiniAppInitData);
  }

  function demoTelegramAuthPayload() {
    const authDemo = MOCK_SOURCE.data?.auth_demo || {};
    return {
      id: Number(authDemo.telegram_id || 7410865527),
      username: authDemo.telegram_username || "u3252a8",
      first_name: authDemo.telegram_first_name || "3252a8",
      last_name: authDemo.telegram_last_name || "",
    };
  }

  function openSettingsLinkEmailDialog() {
    const authDemo = MOCK_SOURCE.data?.auth_demo || {};
    accountStore.openLinkEmailDialog(demoAuthLogin ? authDemo.email || "3252a8@proton.me" : "");
  }

  async function linkTelegramFromSettings() {
    if (!demoAuthLogin) {
      await accountStore.linkTelegramAccount(() => telegramMiniAppInitData);
      return;
    }
    accountStore.update((s) => ({ ...s, linkTelegramBusy: true }));
    try {
      const response = await api("/account/telegram/link", {
        method: "POST",
        body: JSON.stringify({ auth_data: demoTelegramAuthPayload() }),
      });
      if (!response?.ok) throw response;
      if (response?.csrf_token) setToken("", response.csrf_token);
      await loadData({ fresh: true, preserveView: true });
      showToast(t("wa_settings_linked"));
    } catch (error) {
      showToast(error?.message || t("wa_auth_telegram_not_confirmed"));
    } finally {
      accountStore.update((s) => ({ ...s, linkTelegramBusy: false }));
    }
  }

  function openTelegramNotificationsBot() {
    const link = telegramNotificationsStartLink;
    telegramNotificationsBotOpenedAt = Date.now();
    if (!link) {
      showToast(t("wa_telegram_notifications_link_unavailable"));
      return;
    }
    const currentTg = tg || telegramSdk.refresh();
    if (currentTg?.openTelegramLink && /^https:\/\/t\.me\//i.test(link)) {
      try {
        tg = currentTg;
        currentTg.openTelegramLink(link);
        return;
      } catch {
        // Fall back to generic external opening below.
      }
    }
    openExternalLink(link);
  }

  function currentSearchParams() {
    return new URLSearchParams(window.location.search);
  }

  function readEmailCodeLoginDeeplink() {
    const params = currentSearchParams();
    if (params.get("login") !== "email_code") return null;
    const emailHint = normalizedEmail(params.get("login_email") || "");
    if (!emailHint || !emailHint.includes("@")) return null;
    return emailHint;
  }

  function hasEmailCodeLoginDeeplink() {
    return Boolean(readEmailCodeLoginDeeplink());
  }

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

  function readRenewalDeeplink() {
    const params = currentSearchParams();
    const shouldRenew = params.get("after_login") === "renew" || params.get("renew") === "1";
    if (!shouldRenew) return null;
    return {
      tariffKey: String(params.get("renew_tariff") || "").trim(),
    };
  }

  function stripRenewalLoginQueryFromUrl() {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const keys = ["login", "login_email", "after_login", "renew", "renew_tariff"];
    const changed = keys.some((key) => url.searchParams.has(key));
    if (!changed) return;
    for (const key of keys) url.searchParams.delete(key);
    const search = url.searchParams.toString();
    window.history.replaceState(
      null,
      "",
      `${url.pathname}${search ? `?${search}` : ""}${url.hash}`
    );
  }

  function docsDemoParentSearchParams() {
    if (!isDocsDemo) return null;
    try {
      if (window.parent === window) return null;
      return new URLSearchParams(window.parent.location.search);
    } catch (_error) {
      return null;
    }
  }

  function normalizeDemoRoutePath(value) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    const withSlash = raw.startsWith("/") ? raw : `/${raw}`;
    return withSlash.replace(/\/{2,}/g, "/").replace(/\/+$/, "") || "/";
  }

  function docsDemoRouteParams() {
    if (!isDocsDemo) return null;
    const currentQuery = currentSearchParams();
    const currentParams = {
      path: currentQuery.get("path") || "",
      screen: currentQuery.get("screen") || "",
      adminSection: currentQuery.get("admin_section") || "",
    };
    if (currentParams.path || currentParams.screen || currentParams.adminSection) {
      return currentParams;
    }
    if (docsDemoParentRouteConsumed) return currentParams;
    const parentQuery = docsDemoParentSearchParams();
    return {
      path: parentQuery?.get("path") || "",
      screen: parentQuery?.get("screen") || "",
      adminSection: parentQuery?.get("admin_section") || "",
    };
  }

  function docsDemoRoutePathFromParams() {
    const params = docsDemoRouteParams();
    if (!params) return "";
    const explicitPath = normalizeDemoRoutePath(params.path);
    if (explicitPath) return explicitPath;
    const section = normalizeSection(params.screen);
    if (section === "admin") {
      return `/admin/${normalizeAdminSection(params.adminSection || "stats")}`;
    }
    return params.screen ? `/${section}` : "";
  }

  function routePathnameFromLocation() {
    return docsDemoRoutePathFromParams() || window.location.pathname;
  }

  function cleanDocsDemoRouteQuery() {
    if (!isDocsDemo || window.location.protocol === "file:") return;
    const url = new URL(window.location.href);
    const routeKeys = ["path", "screen", "admin_section"];
    const changed = routeKeys.some((key) => url.searchParams.has(key));
    if (!changed) return;
    for (const key of routeKeys) url.searchParams.delete(key);
    const search = url.searchParams.toString();
    window.history.replaceState(
      null,
      "",
      `${url.pathname}${search ? `?${search}` : ""}${url.hash}`
    );
  }

  function initialAdminSectionFromLocation() {
    const currentQuery = currentSearchParams();
    if (MOCK && currentQuery.get("admin_section")) {
      return normalizeAdminSection(currentQuery.get("admin_section"));
    }
    const demoRouteParams = docsDemoRouteParams();
    if (MOCK && demoRouteParams?.adminSection) {
      return normalizeAdminSection(demoRouteParams.adminSection);
    }
    return adminSectionFromPath(routePathnameFromLocation(), routePrefix);
  }

  function syncDocsDemoSection(section, replace = false, adminSection = null, adminUserId = null) {
    if (!isDocsDemo || window.location.protocol === "file:") return false;
    syncSectionPath(section, replace, adminSection, adminUserId, routePrefix);
    cleanDocsDemoRouteQuery();
    return true;
  }

  function syncAppSectionPath(section, replace = false, adminSection = null, adminUserId = null) {
    if (syncDocsDemoSection(section, replace, adminSection, adminUserId)) return;
    syncSectionPath(section, replace, adminSection, adminUserId);
  }

  $: adminPanelProps = {
    api,
    onClose: closeAdminPanel,
    onToast: (text) => showToast(text),
    initialSection: screen === "admin" ? adminActiveSection : initialAdminSectionFromLocation(),
    initialPaymentId: adminPaymentIdFromPath(routePathnameFromLocation(), routePrefix),
    initialPaymentUserId: adminPaymentsUserIdFromPath(routePathnameFromLocation(), routePrefix),
    initialUserId: adminUserIdFromPath(routePathnameFromLocation(), routePrefix),
    onSectionChange: handleAdminSectionChange,
    onSettingsSaved: handleAdminPersistedSaved,
    onTariffsSaved: handleAdminPersistedSaved,
    onThemesSaved: handleAdminPersistedSaved,
    onTranslationsSaved: handleAdminTranslationsSaved,
    routePrefix,
    brandTitle,
    brand,
    appFaviconUrl: CFG.faviconUrl,
    appFaviconUseCustom: CFG.faviconUseCustom,
    appVersion: CFG.appVersion,
    appRepositoryUrl: CFG.appRepositoryUrl,
    currentLang,
    languageOptions,
    languageBusy,
    onLanguageChange: accountStore.updateAccountLanguage,
    t,
  };

  $: {
    const shouldMountAdmin = screen === "admin" && isAdmin && adminBundleApi && adminMountTarget;
    const props = adminPanelProps;

    if (shouldMountAdmin) {
      try {
        if (adminMountHandle && adminMountedTarget === adminMountTarget) {
          adminMountHandle.update?.(props);
        } else {
          destroyAdminMount();
          adminMountTarget.replaceChildren();
          adminMountHandle = adminBundleApi.mount(adminMountTarget, props);
          adminMountedTarget = adminMountTarget;
        }
      } catch (error) {
        adminBundleError = error?.message || "admin_bundle_mount_failed";
        adminBundleApi = null;
        destroyAdminMount();
      }
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
    if (MOCK && isDemoAuthMock()) {
      prepareDemoAuthState();
      showLogin();
      return;
    }
    await runWebappBoot({
      MOCK,
      setMode: (next) => {
        mode = next;
      },
      hasTelegramLaunchParams,
      loadTelegramSdk,
      prepareTelegramMiniApp: () => {
        if (!tg) return;
        try {
          tg.ready();
          tg.expand();
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
      finalizeMagicLogin: (loginToken) => authStore.finalizeMagicLogin(loginToken),
      finalizeTelegramAuth: (authData, source) => authStore.finalizeTelegramAuth(authData, source),
      setAuthStatus: (message, isError) => authStore.setAuthStatus(message, isError),
      t,
      getInitDataForBoot: () =>
        telegramMiniAppInitData || tg?.initData || readTelegramMiniAppInitDataFromLocation(),
      getToken: () => token,
      getCsrfToken: () => csrfToken,
    });
    if (mode === "app" && screen !== "admin") {
      if (hasPendingActivationHandoff()) await loadData({ fresh: true });
      const shown = await maybeShowActivationSuccessDialog({ source: "boot" });
      if (!shown) startPendingActivationWatch();
    }
  }

  function stripTopupQueryFromUrl() {
    if (typeof window === "undefined") return;
    const u = new URL(window.location.href);
    if (!u.searchParams.has("topup")) return;
    u.searchParams.delete("topup");
    const search = u.searchParams.toString();
    const qs = search ? `?${search}` : "";
    window.history.replaceState(null, "", `${u.pathname}${qs}${u.hash}`);
  }

  function isPasswordLoginPath(pathname = routePathnameFromLocation()) {
    return (
      String(pathname || "")
        .replace(/\/+$/, "")
        .toLowerCase() === "/login/password"
    );
  }

  function syncPasswordLoginPath(enabled, replace = false) {
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    const targetPath = enabled ? "/login/password" : isDocsDemo ? "/login" : "/";
    if (isDocsDemo) {
      const targetRuntimePath = withRoutePrefix(targetPath, routePrefix);
      if (window.location.pathname === targetRuntimePath) return;
      const nextUrl = `${targetRuntimePath}${window.location.search}${window.location.hash}`;
      window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
      cleanDocsDemoRouteQuery();
      return;
    }
    if (window.location.pathname === targetPath) return;
    const nextUrl = `${targetPath}${window.location.search}${window.location.hash}`;
    window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
  }

  function setPasswordLoginMode(enabled, replace = false) {
    const nextEnabled = Boolean(enabled);
    authStore.update((s) => ({
      ...s,
      passwordLoginMode: nextEnabled,
      passwordLoginFallback: false,
      authStatus: "",
      authIsError: false,
    }));
    syncPasswordLoginPath(nextEnabled, replace);
  }

  async function loadData(options = {}) {
    const preserveView = options?.preserveView === true;
    const preservedSection = preserveView
      ? normalizeSection(options?.section || screen || activeTab)
      : null;
    const preservedAdminSection =
      preserveView && preservedSection === "admin"
        ? normalizeAdminSection(
            options?.adminSection || adminActiveSection || initialAdminSectionFromLocation()
          )
        : null;
    const payload = await api(options?.fresh ? "/me?fresh=1" : "/me");
    if (!payload.ok) throw new Error(payload.error || "load_failed");
    data = payload;
    billingStore.update((s) => ({
      ...s,
      selectedPlan: null,
      selectedTariffKey: "",
      paymentStep: "tariff",
      selectedMethod: payload.payment_methods?.[0]?.id || "",
    }));
    const currentQuery = currentSearchParams();
    let section = preserveView
      ? preservedSection
      : MOCK && currentQuery.get("screen")
        ? normalizeSection(currentQuery.get("screen"))
        : sectionFromPath(routePathnameFromLocation(), routePrefix);
    if (section === "admin" && !payload.user?.is_admin) section = "settings";
    if (section === "devices" && !payload.settings?.my_devices_enabled) section = "home";
    if (section === "support" && payload.settings?.support_tickets_enabled === false) {
      section = "home";
    }
    if (
      section === "install" &&
      !(payload.settings?.subscription_guides_enabled && payload.subscription?.active)
    ) {
      section = "home";
    }
    const initialAdminSection =
      section === "admin" ? preservedAdminSection || initialAdminSectionFromLocation() : null;
    if (section === "admin" && payload.user?.is_admin) {
      try {
        await ensureI18nScope("admin");
        await ensureAdminBundle();
        adminActiveSection = initialAdminSection || "stats";
      } catch (_error) {
        void _error;
        section = "settings";
        activeTab = "settings";
        showToast(t("wa_unavailable"));
      }
    }
    const initialSupportTicketId =
      section === "support"
        ? supportTicketIdFromPath(routePathnameFromLocation(), routePrefix)
        : null;
    if (isDocsDemo) docsDemoParentRouteConsumed = true;
    activeTab =
      section === "admin"
        ? "settings"
        : section === "install" || section === "trial"
          ? "home"
          : section;
    screen = section;
    mode = "app";
    if (payload.settings?.support_tickets_enabled !== false) {
      if (typeof payload.support_unread_count !== "undefined") {
        supportStore.hydrateUnread(payload.support_unread_count);
      } else {
        void supportStore.refreshUnread();
      }
      supportStore.startPolling({ includeList: false });
    }
    if (section === "support" && initialSupportTicketId) {
      const targetPath = withRoutePrefix(`/support/${initialSupportTicketId}`, routePrefix);
      if (window.location.protocol !== "file:" && window.location.pathname !== targetPath) {
        window.history.replaceState(
          null,
          "",
          `${targetPath}${window.location.search}${window.location.hash}`
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
      await installGuidesStore.load(true);
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

    const topupDeep = new URLSearchParams(window.location.search).get("topup");
    if (topupDeep === "regular" || topupDeep === "premium") {
      const plansList = payload.plans?.length ? payload.plans : [];
      const tariffCatalogLocal = buildTariffCatalog(plansList);
      const sub = payload.subscription || {};
      const tariffModeLocal = plansList.some((plan) => plan?.tariff_key);
      const hasTariffSub = Boolean(
        tariffModeLocal &&
        sub?.active &&
        sub?.tariff_key &&
        tariffCatalogLocal.some((t) => t.key === sub.tariff_key)
      );
      const canRegular =
        hasTariffSub &&
        (sub?.can_topup_regular_traffic ?? sub?.can_topup_traffic) &&
        Number(sub?.traffic_limit_bytes || 0) > 0;
      const canPremium =
        hasTariffSub &&
        (sub?.can_topup_premium_traffic ?? sub?.can_topup_traffic) &&
        Number(sub?.premium_limit_bytes || 0) > 0;
      if (topupDeep === "regular" && canRegular) {
        billingStore.openTopupModal("regular", payload.payment_methods?.[0]?.id || "");
        stripTopupQueryFromUrl();
      } else if (topupDeep === "premium" && canPremium) {
        billingStore.openTopupModal("premium", payload.payment_methods?.[0]?.id || "");
        stripTopupQueryFromUrl();
      }
    }

    const renewalDeep = readRenewalDeeplink();
    if (renewalDeep) {
      const plansList = payload.plans?.length ? payload.plans : [];
      const tariffCatalogLocal = buildTariffCatalog(plansList);
      const tariffModeLocal = plansList.some((plan) => plan?.tariff_key);
      activeTab = "home";
      screen = "home";
      syncAppSectionPath("home", true);
      billingStore.openPaymentModal(
        tariffModeLocal,
        tariffModeLocal && tariffCatalogLocal.length === 1,
        tariffCatalogLocal,
        payload.subscription || {},
        plansList,
        payload.payment_methods?.[0]?.id || "",
        {
          preferredTariffKey: renewalDeep.tariffKey,
          selectDefaultTariff: true,
          preferCheckout: true,
        }
      );
      stripRenewalLoginQueryFromUrl();
    }
    return payload;
  }

  async function loadPublicInstall(shareToken) {
    mode = "publicInstall";
    screen = "install";
    activeTab = "home";
    publicInstallToken = shareToken;
    publicInstallSubscription = {
      install_share_token: shareToken,
      share_url: typeof window !== "undefined" ? `${window.location.origin}/s/${shareToken}` : "",
    };
    const response = await installGuidesStore.loadPublic(shareToken, true);
    publicInstallSubscription = response?.subscription || publicInstallSubscription;
  }

  function showLogin() {
    mode = "login";
    screen = "login";
    activeTab = "home";
    setPasswordLoginMode(isPasswordLoginPath(), true);
    authStore.restorePendingEmailCode((nextScreen) => {
      screen = nextScreen;
    });
    void startEmailCodeLoginFromDeeplink();
  }

  async function api(path, options = {}) {
    return apiClient.api(path, options);
  }

  async function publicApi(path, payload = {}, options = {}) {
    return apiClient.publicApi(path, payload, options);
  }

  function setToken(nextToken, nextCsrf = "") {
    clearManualLogoutFlag();
    token = nextToken || "";
    csrfToken = nextCsrf || readCookie(CSRF_COOKIE_NAME) || "";
    if (!MOCK) clearStoredToken();
  }

  function clearToken() {
    token = "";
    csrfToken = "";
    clearStoredToken();
  }

  function markManualLogout() {
    markManualLogoutInStorage(MANUAL_LOGOUT_FLAG_KEY);
  }

  function clearManualLogoutFlag() {
    clearManualLogoutFlagInStorage(MANUAL_LOGOUT_FLAG_KEY);
  }

  function isManuallyLoggedOut() {
    return readManualLogoutFlag(MANUAL_LOGOUT_FLAG_KEY);
  }

  function submitEmailOnEnter(event) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    authStore.requestEmailCode((s) => (screen = s));
  }

  function openExternalLink(url) {
    if (!url) return;
    if (tg?.openLink) {
      tg.openLink(url, { try_instant_view: false });
      return;
    }
    window.location.assign(url);
  }

  function openAppLink(url) {
    const raw = String(url || "").trim();
    if (!raw || hasControlChars(raw) || /^(javascript|data|vbscript):/i.test(raw)) {
      return;
    }
    if (isHttpUrl(raw)) {
      openExternalLink(raw);
      return;
    }

    const isTelegramMiniApp = hasTelegramLaunchParams();
    const currentTg = tg || telegramSdk.refresh();
    const gatewayUrl = isTelegramMiniApp ? buildExternalAppLaunchUrl(raw, null, currentLang) : "";
    if (gatewayUrl) {
      if (currentTg?.openLink) {
        try {
          tg = currentTg;
          currentTg.openLink(gatewayUrl);
          return;
        } catch {
          // Fall back to regular browser navigation below.
        }
      }
      window.location.assign(gatewayUrl);
      return;
    }

    if (/^tg:\/\//i.test(raw) && currentTg?.openTelegramLink) {
      try {
        tg = currentTg;
        currentTg.openTelegramLink(raw);
        return;
      } catch {
        // Fall back to the generic deeplink path below.
      }
    }
    openUrlWithHiddenAnchor(raw);
  }

  function openConnectLink() {
    const url = subscription?.connect_url || subscription?.config_link;
    if (!url) {
      showToast(t("wa_connect_link_unavailable"));
      return;
    }
    openExternalLink(url);
  }

  function openPublicConnectLink() {
    const url = publicInstallSubscription?.connect_url || publicInstallSubscription?.config_link;
    if (!url) {
      showToast(t("wa_connect_link_unavailable"));
      return;
    }
    openExternalLink(url);
  }

  function openInstallOrConnect() {
    if (canUseInstallGuides()) {
      goInstall();
      return;
    }
    openConnectLink();
  }

  function openTrialInstallOrConnect() {
    if (canUseInstallGuides()) {
      goInstall();
      return;
    }
    const url = trialActivationResult?.connect_url || trialActivationResult?.config_link;
    if (url) {
      openExternalLink(url);
      return;
    }
    openConnectLink();
  }

  function openActivationConnectLink() {
    const url =
      subscription?.connect_url ||
      subscription?.config_link ||
      trialActivationResult?.connect_url ||
      trialActivationResult?.config_link;
    if (!url) {
      showToast(t("wa_connect_link_unavailable"));
      return;
    }
    openExternalLink(url);
  }

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

  async function copyText(value, success = t("wa_copied")) {
    if (!value) {
      showToast(t("wa_unavailable"));
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const area = document.createElement("textarea");
      area.value = value;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    showToast(success);
  }

  async function applyPromo() {
    const code = promoCode.trim();
    if (!code) {
      promoFieldError = t("wa_promo_enter");
      return;
    }
    promoFieldError = "";
    promoBusy = true;
    promoStatus = "";
    try {
      const response = await api("/promo/apply", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      if (!response.ok) throw response;
      promoCode = "";
      promoStatus = response.end_date_text
        ? t("wa_promo_activated_until", { date: response.end_date_text })
        : t("wa_promo_activated");
      promoIsError = false;
      await loadData({ fresh: true });
    } catch (error) {
      promoStatus = error?.message || t("wa_promo_activation_failed");
      promoIsError = true;
      promoFieldError = promoStatus;
    } finally {
      promoBusy = false;
    }
  }

  async function activateTrial() {
    if (trialBusy) return;
    trialBusy = true;
    trialActivationResult = null;
    trialActivationError = "";
    try {
      const response = await api("/trial/activate", {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!response.ok) throw response;
      trialActivationResult = response;
      showToast(t("wa_trial_activated"));
      await loadData({ fresh: true });
      await maybeShowActivationSuccessDialog({ source: "trial", force: true });
    } catch (error) {
      const message = error?.message || t("wa_trial_activation_failed");
      trialActivationError = message;
      showToast(message);
    } finally {
      trialBusy = false;
    }
  }

  function showToast(message) {
    toastText = message;
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      toastText = "";
    }, 2400);
  }

  function goHome() {
    billingStore.closePaymentModal();
    activeTab = "home";
    screen = "home";
    syncAppSectionPath("home");
  }

  function goInstall() {
    if (!canUseInstallGuides()) {
      openConnectLink();
      return;
    }
    billingStore.closePaymentModal();
    activeTab = "home";
    screen = "install";
    syncAppSectionPath("install");
    installGuidesStore.load(true);
  }

  function goInvite() {
    billingStore.closePaymentModal();
    activeTab = "invite";
    screen = "invite";
    syncAppSectionPath("invite");
  }

  function goDevices() {
    if (!devicesEnabled) return;
    billingStore.closePaymentModal();
    activeTab = "devices";
    screen = "devices";
    syncAppSectionPath("devices");
    devicesStore.loadDevices(devicesEnabled);
  }

  function goSupport() {
    if (!supportEnabled) return;
    billingStore.closePaymentModal();
    activeTab = "support";
    screen = "support";
    syncAppSectionPath("support");
    supportStore.loadList();
    supportStore.startPolling({ includeList: true });
  }

  function defaultPaymentMethod() {
    return methods[0]?.id || "";
  }

  function openPaymentModal() {
    billingStore.openPaymentModal(
      tariffMode,
      singleTariffMode,
      tariffCatalog,
      subscription,
      plans,
      defaultPaymentMethod()
    );
  }

  function openTopupModal(kind) {
    billingStore.openTopupModal(kind, defaultPaymentMethod());
  }

  function openRegularTopupModal() {
    openTopupModal("regular");
  }

  function openPremiumTopupModal() {
    openTopupModal("premium");
  }

  function openTariffChangeModal() {
    billingStore.openTariffChangeModal(defaultPaymentMethod());
  }

  function openDeviceTopupModal() {
    billingStore.openDeviceTopupModal(defaultPaymentMethod());
  }

  function closeDeviceTopupModal() {
    billingStore.closeDeviceTopupModal();
  }

  function loadDevices(force = false) {
    return devicesStore.loadDevices(devicesEnabled, force);
  }

  function disconnectDevice() {
    return devicesStore.disconnectDevice(devicesEnabled);
  }

  function goSettings() {
    billingStore.closePaymentModal();
    activeTab = "settings";
    screen = "settings";
    syncAppSectionPath("settings");
  }

  async function openAdminPanel() {
    if (!isAdmin) return;
    clearLanguageClickGuard();
    billingStore.closePaymentModal();
    const nextAdminSection = normalizeAdminSection(
      adminActiveSection || adminSectionFromPath(routePathnameFromLocation(), routePrefix)
    );
    try {
      await ensureI18nScope("admin");
      await ensureAdminBundle();
    } catch (_error) {
      void _error;
      showToast(t("wa_unavailable"));
      return;
    }
    activeTab = "settings";
    screen = "admin";
    adminActiveSection = nextAdminSection;
    syncAppSectionPath("admin", false, adminActiveSection);
  }

  function closeAdminPanel() {
    screen = "settings";
    activeTab = "settings";
    syncAppSectionPath("settings");
  }

  function handleAdminSectionChange(adminSection, adminUserId = null) {
    if (screen !== "admin") return;
    const nextAdminSection = normalizeAdminSection(adminSection);
    adminActiveSection = nextAdminSection;
    if (window.location.protocol === "file:") return;
    syncAppSectionPath("admin", false, nextAdminSection, adminUserId);
  }

  function adminPayloadHasLogoChange(options = {}) {
    const keys = new Set([
      ...Object.keys(options.updates || {}),
      ...(Array.isArray(options.deletes) ? options.deletes : []),
    ]);
    return [
      "WEBAPP_LOGO_URL",
      "WEBAPP_LOGO_USE_EMOJI",
      "WEBAPP_LOGO_EMOJI",
      "WEBAPP_LOGO_EMOJI_FONT",
      "WEBAPP_FAVICON_URL",
      "WEBAPP_FAVICON_USE_CUSTOM",
      "WEBAPP_LOGO_FAVICON_URL",
    ].some((key) => keys.has(key));
  }

  async function handleAdminPersistedSaved(options = {}) {
    invalidateWebappTariffOptionCaches(billingStore);
    installGuidesStore.reset();
    try {
      await loadData();
    } catch {
      // Admin save already succeeded; a later full refresh will pick up new settings or catalog.
    }
    const shouldReloadFrontend =
      options?.reloadFrontend === true ||
      (!options?.deferFrontendReload && adminPayloadHasLogoChange(options));
    if (shouldReloadFrontend && typeof window !== "undefined") {
      window.location.reload();
    }
  }

  async function refreshI18nScope(scope) {
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

  function selectTariff(tariff) {
    billingStore.selectTariff(tariff, plans);
  }

  function continueWithSelectedTariff() {
    billingStore.continueWithSelectedTariff(selectedTariffPlans);
  }

  function backToTariffList() {
    billingStore.backToTariffList(subscription, tariffCatalog);
  }

  function primaryPayActionLabel() {
    if (!subscription.active && appSettings?.trial_enabled && appSettings?.trial_available) {
      return t("wa_pay_full_subscription", {}, "Оплатить полную подписку");
    }
    if (trafficMode || selectedPlan?.sale_mode === "traffic_package") return t("wa_buy_traffic");
    return subscription.active
      ? t("wa_renew_subscription", {}, "Продлить подписку")
      : t("wa_pay_subscription");
  }
</script>

<svelte:head>
  <title>{brandTitle}</title>
  {#if shellThemeCssHref}
    <link rel="stylesheet" href={shellThemeCssHref} data-theme-css={resolvedThemeKey} />
  {/if}
</svelte:head>

<Tooltip.Provider>
  {#key currentLang}
    {#if isPreviewBoard}
      <svelte:component this={previewBoardComponent} config={CFG} mockData={MOCK_SOURCE.data} />
    {:else}
      <div class="app-shell {shellToneClass} {shellThemeClass}" style={shellStyle}>
        {#if mode === "loading"}
          <div class="loader">
            <BrandMark {brand} size="md" />
            <div>{t("wa_loading")}</div>
          </div>
        {:else if mode === "appLaunch"}
          <AppLaunchScreen
            {brand}
            {appLaunchTarget}
            {refreshAppLaunchTarget}
            {openAppLaunchTarget}
            {t}
          />
        {:else if mode === "publicInstall"}
          <div class="public-install-shell">
            <a class="public-install-brand" href="/" aria-label={brandTitle}>
              <BrandMark {brand} />
              <strong>{brandTitle}</strong>
            </a>
            <InstallGuideScreen
              {currentLang}
              telegramPlatform={tg?.platform || ""}
              user={{}}
              subscription={publicInstallSubscription || {
                install_share_token: publicInstallToken,
              }}
              {goHome}
              openConnectLink={openPublicConnectLink}
              {openExternalLink}
              {openAppLink}
              {copyText}
              {t}
              publicMode
            />
          </div>
        {:else if mode === "login"}
          <AuthScreen
            {screen}
            {CFG}
            {brandTitle}
            {brand}
            bind:email={$authStore.email}
            bind:emailPassword={$authStore.emailPassword}
            bind:emailCode={$authStore.emailCode}
            {pendingEmail}
            {authStatus}
            {authIsError}
            {authBusy}
            {authResendCooldown}
            {loginEmailFieldError}
            {loginEmailTooltipOpen}
            {passwordLoginFallback}
            {passwordLoginMode}
            {telegramLoginBusy}
            {telegramLoginUnavailable}
            {telegramLoginChecking}
            {telegramLoginLabel}
            {telegramLoginUnavailableMessage}
            {privacyPolicyUrl}
            {userAgreementUrl}
            {currentLang}
            {currentLanguageOption}
            {languageOptions}
            {languageMenuOpen}
            {languageClickGuard}
            {languageClickGuardArmed}
            {t}
            {setLanguageMenuOpen}
            updateLoginLanguage={updateGuestLanguage}
            requestEmailCode={() => authStore.requestEmailCode((s) => (screen = s))}
            loginWithEmailPassword={authStore.loginWithEmailPassword}
            verifyEmailCode={authStore.verifyEmailCode}
            openTelegramLogin={openLoginTelegram}
            {openExternalLink}
            {submitEmailOnEnter}
            onBackToLogin={() => (screen = "login")}
            clearLoginEmailError={() => {
              loginEmailFieldError = "";
              loginEmailTooltipOpen = false;
            }}
            setPasswordLoginMode={(enabled) => setPasswordLoginMode(enabled)}
          />
        {:else if screen === "admin" && isAdmin}
          {#if adminBundleApi}
            <div class="admin-mount" bind:this={adminMountTarget}></div>
          {:else}
            <div class="loader">
              <BrandMark {brand} size="md" />
              <div>{adminBundleError ? t("wa_unavailable") : t("wa_loading")}</div>
            </div>
          {/if}
        {:else}
          <WebAppShell
            {screen}
            {activeTab}
            {brandTitle}
            {brand}
            {devicesEnabled}
            {supportEnabled}
            {supportUnreadCount}
            {supportUnreadLoading}
            {supportUnreadLoaded}
            {hasUnlinkedIdentity}
            {isAdmin}
            {openAdminPanel}
            {goDevices}
            {goHome}
            {goInvite}
            {goSupport}
            {goSettings}
            {t}
          >
            {#if screen === "home"}
              <HomeScreen
                {appSettings}
                {brand}
                {brandTitle}
                {canChangeTariff}
                {currentTariffName}
                {hasActiveTariffSubscription}
                {hasMultipleTariffs}
                {premiumTrafficTopupBarClickable}
                {premiumTrafficTopupUnlocked}
                {regularTrafficTopupBarClickable}
                {regularTrafficTopupUnlocked}
                {subscription}
                {telegramNotificationsNeedPrompt}
                {telegramNotificationsStartLink}
                {telegramNotificationsStatus}
                {termUnitLabel}
                {trafficMode}
                {trialBusy}
                {activateTrial}
                {openTelegramNotificationsBot}
                openConnectLink={openInstallOrConnect}
                {openPaymentModal}
                {openRegularTopupModal}
                {openPremiumTopupModal}
                {openTariffChangeModal}
                {primaryPayActionLabel}
                {t}
              />
            {:else if screen === "install"}
              <InstallGuideScreen
                {currentLang}
                telegramPlatform={tg?.platform || ""}
                {user}
                {subscription}
                {goHome}
                {openConnectLink}
                {openExternalLink}
                {openAppLink}
                {copyText}
                {t}
              />
            {:else if screen === "trial"}
              <TrialActivationScreen
                {appSettings}
                {brand}
                {brandTitle}
                {subscription}
                {trialBusy}
                trialResult={trialActivationResult}
                trialError={trialActivationError}
                {activateTrial}
                openInstallOrConnect={openTrialInstallOrConnect}
                {goHome}
                {t}
              />
            {:else if screen === "invite"}
              <InviteScreen
                {referral}
                {referralBonusDetails}
                {referralOneBonusPerReferee}
                {referralWelcomeBonusDays}
                bind:promoCode
                bind:promoFieldError
                {promoBusy}
                {promoIsError}
                {promoStatus}
                {applyPromo}
                clearPromoFieldError={() => (promoFieldError = "")}
                {copyText}
                {t}
              />
            {:else if screen === "devices"}
              <DevicesScreen
                {devicesBusy}
                {devicesData}
                {devicesIsError}
                {devicesLoaded}
                {devicesErrorCode}
                {devicesStatus}
                {subscription}
                {loadDevices}
                openDeviceDisconnectDialog={devicesStore.openDeviceDisconnectDialog}
                {openDeviceTopupModal}
                {t}
              />
            {:else if screen === "support"}
              {#if $supportStore.openedTicketId}
                <SupportTicketScreen
                  maxBodyLength={appSettings?.support_ticket_max_body_length || 4000}
                  {brand}
                  {user}
                  userAvatarUrl={profileAvatarUrl}
                  userInitials={telegramProfileName
                    ? telegramProfileName.slice(0, 2).toUpperCase()
                    : "U"}
                  {t}
                />
              {:else}
                <SupportScreen
                  maxSubjectLength={appSettings?.support_ticket_max_subject_length || 160}
                  maxBodyLength={appSettings?.support_ticket_max_body_length || 4000}
                  {user}
                  {t}
                />
              {/if}
            {:else if screen === "settings"}
              <SettingsScreen
                {currentLang}
                {currentLanguageOption}
                {emailLinkStatus}
                {isAdmin}
                {languageBusy}
                {languageClickGuard}
                {languageClickGuardArmed}
                bind:languageMenuOpen
                {languageOptions}
                {linkEmailBusy}
                {linkTelegramBusy}
                {privacyPolicyUrl}
                {profileAvatarUrl}
                {profileEmail}
                {profileTelegramId}
                {supportUrl}
                {telegramNotificationsNeedPrompt}
                {telegramNotificationsStartLink}
                {telegramNotificationsStatus}
                {telegramProfileName}
                {user}
                {userAgreementUrl}
                {userLanguage}
                showLogout={!telegramMiniAppContext}
                linkTelegramAccount={linkTelegramFromSettings}
                {openTelegramNotificationsBot}
                logout={accountStore.logout}
                {openAdminPanel}
                {openExternalLink}
                openLinkEmailDialog={openSettingsLinkEmailDialog}
                openSetPasswordDialog={accountStore.openSetPasswordDialog}
                {setLanguageMenuOpen}
                {t}
                updateAccountLanguage={accountStore.updateAccountLanguage}
              />
            {/if}
          </WebAppShell>

          <PaymentDialogs
            bind:linkEmailCode={$accountStore.linkEmailCode}
            bind:linkEmailFieldError={$accountStore.linkEmailFieldError}
            bind:linkEmailValue={$accountStore.linkEmailValue}
            bind:paymentModalOpen={$billingStore.paymentModalOpen}
            bind:paymentStep={$billingStore.paymentStep}
            bind:selectedMethod={$billingStore.selectedMethod}
            bind:selectedPlan={$billingStore.selectedPlan}
            bind:selectedTariffKey={$billingStore.selectedTariffKey}
            bind:setPasswordCode={$accountStore.setPasswordCode}
            bind:setPasswordConfirm={$accountStore.setPasswordConfirm}
            bind:setPasswordValue={$accountStore.setPasswordValue}
            setPasswordEmail={user?.email || ""}
            createPayment={billingStore.createPayment}
            {deviceConfirmOpen}
            {deviceDisconnectBusy}
            {deviceToDisconnect}
            {disconnectDevice}
            {linkEmailBusy}
            {linkEmailIsError}
            {linkEmailOpen}
            {linkEmailPending}
            {linkEmailResendCooldown}
            {linkEmailStatus}
            {setPasswordBusy}
            {setPasswordIsError}
            {setPasswordOpen}
            {setPasswordPending}
            {setPasswordResendCooldown}
            {setPasswordStatus}
            {hasMultipleTariffs}
            {methods}
            {payBusy}
            {plans}
            {selectedTariff}
            {selectedTariffPlans}
            {singleTariffMode}
            {subscription}
            {subscriptionPurchaseDescription}
            {tariffCatalog}
            {tariffMode}
            closeDeviceDisconnectDialog={devicesStore.closeDeviceDisconnectDialog}
            closeLinkEmailDialog={accountStore.closeLinkEmailDialog}
            closePaymentModal={billingStore.closePaymentModal}
            closeSetPasswordDialog={accountStore.closeSetPasswordDialog}
            {backToTariffList}
            {continueWithSelectedTariff}
            requestLinkEmailCode={accountStore.requestLinkEmailCode}
            requestSetPasswordCode={accountStore.requestSetPasswordCode}
            {selectTariff}
            {t}
            {termUnitLabel}
            verifyLinkEmailCode={accountStore.verifyLinkEmailCode}
            confirmSetPassword={accountStore.confirmSetPassword}
          />

          <TariffDialogs
            bind:changeConfirmOpen={$billingStore.changeConfirmOpen}
            bind:changeModalOpen={$billingStore.changeModalOpen}
            bind:deviceTopupModalOpen={$billingStore.deviceTopupModalOpen}
            bind:selectedChangeAction={$billingStore.selectedChangeAction}
            bind:selectedChangeTarget={$billingStore.selectedChangeTarget}
            bind:selectedDeviceTopupPlan={$billingStore.selectedDeviceTopupPlan}
            bind:selectedMethod={$billingStore.selectedMethod}
            bind:selectedTopupPlan={$billingStore.selectedTopupPlan}
            bind:topupModalOpen={$billingStore.topupModalOpen}
            applyTariffChange={billingStore.applyTariffChange}
            {changeOptions}
            {closeDeviceTopupModal}
            closeTariffChangeConfirm={billingStore.closeTariffChangeConfirm}
            closeTariffChangeModal={billingStore.closeTariffChangeModal}
            closeTopupModal={billingStore.closeTopupModal}
            createDeviceTopupPayment={billingStore.createDeviceTopupPayment}
            createTopupPayment={billingStore.createTopupPayment}
            {deviceTopupOptions}
            {methods}
            openTariffChangeConfirm={billingStore.openTariffChangeConfirm}
            {payBusy}
            {singleTariffMode}
            {subscription}
            {tariffActionBusy}
            {topupKind}
            {topupOptions}
            {trafficMode}
            {t}
          />

          <Dialog
            open={activationSuccessDialogOpen}
            title={t("wa_activation_success_title", {}, "Everything is successfully activated")}
            description={activationSuccessUseInstallGuides
              ? t(
                  "wa_activation_success_install_hint",
                  {},
                  "Press OK and follow the setup instructions for your device."
                )
              : t(
                  "wa_activation_success_connect_hint",
                  {},
                  "Press OK and we will open the Remnawave subscription page for setup."
                )}
            closeLabel={t("wa_close")}
            onclose={closeActivationSuccessDialog}
            class="activation-success-dialog"
          >
            <CheckCircle2 slot="titleIcon" size={23} />
            <div class="activation-success-dialog-body">
              <Button class="wide" onclick={closeActivationSuccessDialog}>
                {t("wa_ok", {}, "OK")}
              </Button>
            </div>
          </Dialog>
        {/if}

        {#if toastText}
          <div class="toast" role="status">{toastText}</div>
        {/if}
      </div>
    {/if}
  {/key}
</Tooltip.Provider>
