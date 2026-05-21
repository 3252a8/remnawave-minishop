<script>
  import { onMount, setContext } from "svelte";
  import { createAuthStore } from "./lib/webapp/stores/authStore.js";
  import { createBillingStore } from "./lib/webapp/stores/billingStore.js";
  import { createDevicesStore } from "./lib/webapp/stores/devicesStore.js";
  import { createSupportStore } from "./lib/webapp/stores/supportStore.js";
  import { createAccountStore } from "./lib/webapp/stores/accountStore.js";
  import { Tooltip } from "$components/ui/primitives.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import PreviewBoard from "./PreviewBoard.svelte";
  import WebAppShell from "./webapp/WebAppShell.svelte";
  import AuthScreen from "./webapp/auth/AuthScreen.svelte";
  import PaymentDialogs from "./webapp/PaymentDialogs.svelte";
  import TariffDialogs from "./webapp/TariffDialogs.svelte";
  import DevicesScreen from "./webapp/screens/DevicesScreen.svelte";
  import HomeScreen from "./webapp/screens/HomeScreen.svelte";
  import InviteScreen from "./webapp/screens/InviteScreen.svelte";
  import SettingsScreen from "./webapp/screens/SettingsScreen.svelte";
  import SupportScreen from "./webapp/screens/SupportScreen.svelte";
  import SupportTicketScreen from "./webapp/screens/SupportTicketScreen.svelte";

  import {
    LANGUAGE_FLAGS,
    LANGUAGE_LABELS,
    MANUAL_LOGOUT_FLAG_KEY,
    TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS,
    TELEGRAM_SDK_ACTION_TIMEOUT_MS,
    TELEGRAM_SDK_BOOT_TIMEOUT_MS,
    TELEGRAM_WEBAPP_SCRIPT_URL,
    WEBAPP_LANGUAGE_ORDER,
  } from "./lib/webapp/constants.js";

  import {
    applyFavicon,
    normalizeBrand,
    readJsonScript,
    structuredCloneSafe,
  } from "./lib/webapp/browser.js";
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
  import { mockApi as runMockApi } from "./lib/webapp/mockApi.js";
  import { DEV_MOCK, applyPreviewMock } from "./lib/webapp/previewMock.js";
  import {
    adminSectionFromPath,
    adminUserIdFromPath,
    normalizeSection,
    sectionFromPath,
    supportTicketIdFromPath,
    syncSectionPath,
  } from "./lib/webapp/routes.js";

  const query = new URLSearchParams(window.location.search);
  applyPreviewMock(query.get("mock"));
  const isPreviewBoard = query.get("preview") === "all";
  const injectedConfig = readJsonScript("webapp-config");
  const injectedI18n = readJsonScript("i18n");
  const isLocalShell =
    window.location.protocol === "file:" ||
    ["", "localhost", "127.0.0.1"].includes(window.location.hostname);
  const MOCK = !injectedConfig && isLocalShell ? DEV_MOCK : null;
  const CFG = {
    ...DEV_MOCK.config,
    ...(MOCK ? MOCK.config : {}),
    ...(injectedConfig || {}),
  };
  const themePreviewKey = String(CFG.themePreviewKey || query.get("theme_preview") || "").trim();
  const I18N = injectedI18n || {};
  let telegramSdkStatus = "idle";
  let telegramMiniAppInitData = "";

  let mode = isPreviewBoard ? "preview" : "loading";
  let activeTab = "home";
  let screen = "home";
  let data = isPreviewBoard ? structuredCloneSafe(DEV_MOCK.data) : null;
  let trialBusy = false;
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
  let adminPanelProps = {};
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
    getLang: () => user?.language_code || CFG.language || "ru",
  });
  const normalizeLangCode = i18n.normalizeLangCode;
  const t = i18n.t;
  const termUnitLabel = i18n.termUnitLabel;
  const languageName = i18n.languageName;
  const apiClient = createApiClient({
    apiBase: CFG.apiBase,
    csrfCookieName: CSRF_COOKIE_NAME,
    getCsrfToken: () => csrfToken,
    onUnauthorized: () => {
      clearToken();
      showLogin();
    },
    mockApi: MOCK ? (path, options, context) => runMockApi(path, options, context) : null,
    getMockContext: () => ({ currentLang, normalizeLangCode, clone: structuredCloneSafe }),
  });
  const billing = createBillingActions({
    api: (path, options) => apiClient.api(path, options),
    t: (...args) => t(...args),
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
    tg,
  });
  const devicesStore = createDevicesStore({ api, t, showToast });
  const supportStore = createSupportStore({ api, t, showToast });
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
    telegramOAuthClientId,
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
  $: plans = data?.plans?.length ? data.plans : DEV_MOCK.data.plans;
  $: methods = data?.payment_methods?.length ? data.payment_methods : [];
  $: appSettings = data?.settings || DEV_MOCK.data.settings;
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
  $: supportStore.setActive(Boolean(mode === "app" && screen === "support" && supportEnabled));
  $: subscription = data?.subscription || DEV_MOCK.data.subscription;
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
  $: referral = data?.referral || DEV_MOCK.data.referral;
  $: currentLang = normalizeLangCode(user?.language_code || CFG.language || "ru");
  $: languageOptions = WEBAPP_LANGUAGE_ORDER.map((code) => ({
    value: code,
    label: LANGUAGE_LABELS[code] || code.toUpperCase(),
    flag: LANGUAGE_FLAGS[code] || "🏳️",
  }));
  $: currentLanguageOption =
    languageOptions.find((option) => option.value === currentLang) || languageOptions[0];
  $: userLanguage = languageName(currentLang);
  $: emailLinkStatus = user?.email ? t("wa_settings_linked") : t("wa_settings_email_not_linked");
  $: hasUnlinkedIdentity = !user?.telegram_linked || !user?.email;
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
  $: telegramLoginUnavailable =
    !telegramMiniAppAuthAvailable && !telegramOAuthClientId && telegramSdkStatus !== "loading";
  $: telegramLoginChecking =
    telegramLoginBusy || (authBusy && authStatus === t("wa_auth_checking_telegram"));
  $: telegramLoginLabel = telegramLoginUnavailable
    ? t("wa_login_telegram_unavailable_button")
    : telegramLoginChecking
      ? t("wa_auth_checking_telegram")
      : t("wa_login_telegram_button");
  $: telegramLoginUnavailableMessage =
    telegramLoginUnavailable && telegramSdkStatus === "unavailable"
      ? t("wa_auth_telegram_unavailable")
      : telegramLoginUnavailable
        ? t("wa_auth_telegram_not_configured")
        : "";
  $: applyFavicon(faviconBrand);
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

  onMount(() => {
    if (isPreviewBoard) return;
    const onAnyPointerDown = () => {
      if (mode === "login") loginEmailTooltipOpen = false;
    };
    const onPopState = () => {
      const section = sectionFromPath(window.location.pathname);
      if (mode === "login") {
        setPasswordLoginMode(isPasswordLoginPath(), true);
        screen = "login";
        return;
      }
      if (mode === "app") {
        if (section === "admin" && isAdmin) {
          const pathAtStart = window.location.pathname;
          void Promise.all([ensureI18nScope("admin"), ensureAdminBundle()])
            .then(() => {
              if (sectionFromPath(window.location.pathname) !== "admin") return;
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
              : section;
        activeTab = nextSection;
        screen = nextSection;
        if (nextSection === "devices") devicesStore.loadDevices(devicesEnabled);
        if (nextSection === "support") {
          supportStore.loadList();
          supportStore.startPolling({ includeList: true });
        }
      }
    };
    window.addEventListener("popstate", onPopState);
    window.addEventListener("pointerdown", onAnyPointerDown);
    boot();
    return () => {
      window.removeEventListener("popstate", onPopState);
      window.removeEventListener("pointerdown", onAnyPointerDown);
      authStore.stopTelegramLoginWatchdog();
      authStore.clearCooldownTimer();
      accountStore.clearLinkEmailResendTimer();
      accountStore.clearSetPasswordResendTimer();
      supportStore.closePolling();
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
      link.onerror = () => reject(new Error(`stylesheet_load_failed:${href}`));
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
      script.onerror = () => reject(new Error(`script_load_failed:${src}`));
      document.head.appendChild(script);
    });
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
      await appendStylesheetOnce("subscription-webapp-admin-css", cssHref);
      await appendScriptOnce("subscription-webapp-admin-js", jsSrc);
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
  }

  $: adminPanelProps = {
    api,
    onClose: closeAdminPanel,
    onToast: (text) => showToast(text),
    initialSection: adminSectionFromPath(window.location.pathname),
    initialUserId: adminUserIdFromPath(window.location.pathname),
    onSectionChange: handleAdminSectionChange,
    onSettingsSaved: handleAdminPersistedSaved,
    onTariffsSaved: handleAdminPersistedSaved,
    onThemesSaved: handleAdminPersistedSaved,
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
        if (adminMountHandle) {
          adminMountHandle.update?.(props);
        } else {
          adminMountTarget.replaceChildren();
          adminMountHandle = adminBundleApi.mount(adminMountTarget, props);
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
      finalizeMagicLogin: (loginToken) => authStore.finalizeMagicLogin(loginToken),
      finalizeTelegramAuth: (authData, source) => authStore.finalizeTelegramAuth(authData, source),
      setAuthStatus: (message, isError) => authStore.setAuthStatus(message, isError),
      t,
      getInitDataForBoot: () =>
        telegramMiniAppInitData || tg?.initData || readTelegramMiniAppInitDataFromLocation(),
      getToken: () => token,
      getCsrfToken: () => csrfToken,
    });
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

  function isPasswordLoginPath(pathname = window.location.pathname) {
    return (
      String(pathname || "")
        .replace(/\/+$/, "")
        .toLowerCase() === "/login/password"
    );
  }

  function syncPasswordLoginPath(enabled, replace = false) {
    if (typeof window === "undefined" || window.location.protocol === "file:") return;
    const targetPath = enabled ? "/login/password" : "/";
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

  async function loadData() {
    const payload = await api("/me");
    if (!payload.ok) throw new Error(payload.error || "load_failed");
    data = payload;
    billingStore.update((s) => ({
      ...s,
      selectedPlan: null,
      selectedTariffKey: "",
      paymentStep: "tariff",
      selectedMethod: payload.payment_methods?.[0]?.id || "",
    }));
    let section =
      MOCK && query.get("screen")
        ? normalizeSection(query.get("screen"))
        : sectionFromPath(window.location.pathname);
    if (section === "admin" && !payload.user?.is_admin) section = "settings";
    if (section === "devices" && !payload.settings?.my_devices_enabled) section = "home";
    if (section === "support" && payload.settings?.support_tickets_enabled === false) {
      section = "home";
    }
    const initialAdminSection =
      section === "admin" ? adminSectionFromPath(window.location.pathname) : null;
    if (section === "admin" && payload.user?.is_admin) {
      try {
        await ensureI18nScope("admin");
        await ensureAdminBundle();
      } catch (_error) {
        void _error;
        section = "settings";
        activeTab = "settings";
        showToast(t("wa_unavailable"));
      }
    }
    const initialSupportTicketId =
      section === "support" ? supportTicketIdFromPath(window.location.pathname) : null;
    activeTab = section === "admin" ? "settings" : section;
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
      const targetPath = `/support/${initialSupportTicketId}`;
      if (window.location.protocol !== "file:" && window.location.pathname !== targetPath) {
        window.history.replaceState(
          null,
          "",
          `${targetPath}${window.location.search}${window.location.hash}`
        );
      }
    } else {
      syncSectionPath(section, true, initialAdminSection);
    }
    if (section === "devices" && payload.settings?.my_devices_enabled) {
      await devicesStore.loadDevices(true);
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
  }

  function showLogin() {
    mode = "login";
    screen = "login";
    activeTab = "home";
    setPasswordLoginMode(isPasswordLoginPath(), true);
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
      tg.openLink(url);
      return;
    }
    window.location.assign(url);
  }

  function openConnectLink() {
    const url = subscription?.connect_url || subscription?.config_link;
    if (!url) {
      showToast(t("wa_connect_link_unavailable"));
      return;
    }
    openExternalLink(url);
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
      await loadData();
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
    try {
      const response = await api("/trial/activate", {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!response.ok) throw response;
      showToast(t("wa_trial_activated"));
      await loadData();
    } catch (error) {
      showToast(error?.message || t("wa_trial_activation_failed"));
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
    syncSectionPath("home");
  }

  function goInvite() {
    billingStore.closePaymentModal();
    activeTab = "invite";
    screen = "invite";
    syncSectionPath("invite");
  }

  function goDevices() {
    if (!devicesEnabled) return;
    billingStore.closePaymentModal();
    activeTab = "devices";
    screen = "devices";
    syncSectionPath("devices");
    devicesStore.loadDevices(devicesEnabled);
  }

  function goSupport() {
    if (!supportEnabled) return;
    billingStore.closePaymentModal();
    activeTab = "support";
    screen = "support";
    syncSectionPath("support");
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
    syncSectionPath("settings");
  }

  async function openAdminPanel() {
    if (!isAdmin) return;
    clearLanguageClickGuard();
    billingStore.closePaymentModal();
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
    syncSectionPath("admin", false, adminSectionFromPath(window.location.pathname));
  }

  function closeAdminPanel() {
    screen = "settings";
    activeTab = "settings";
    syncSectionPath("settings");
  }

  function handleAdminSectionChange(adminSection, adminUserId = null) {
    if (screen !== "admin") return;
    if (window.location.protocol === "file:") return;
    const targetPath =
      adminSection === "users" && adminUserId
        ? `/admin/users/${adminUserId}`
        : `/admin/${adminSection}`;
    if (window.location.pathname === targetPath) return;
    window.history.pushState(
      null,
      "",
      `${targetPath}${window.location.search}${window.location.hash}`
    );
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
    if (trafficMode || selectedPlan?.sale_mode === "traffic_package") return t("wa_buy_traffic");
    return subscription.active ? t("wa_renew") : t("wa_pay_subscription");
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
      <PreviewBoard config={CFG} mockData={DEV_MOCK.data} />
    {:else}
      <div class="app-shell {shellToneClass} {shellThemeClass}" style={shellStyle}>
        {#if mode === "loading"}
          <div class="loader">
            <BrandMark {brand} size="md" />
            <div>{t("wa_loading")}</div>
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
            {t}
            requestEmailCode={() => authStore.requestEmailCode((s) => (screen = s))}
            loginWithEmailPassword={authStore.loginWithEmailPassword}
            verifyEmailCode={authStore.verifyEmailCode}
            openTelegramLogin={() =>
              authStore.openTelegramLogin(telegramOAuthClientId, () => telegramMiniAppInitData)}
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
                {termUnitLabel}
                {trafficMode}
                {trialBusy}
                {activateTrial}
                {openConnectLink}
                {openPaymentModal}
                {openRegularTopupModal}
                {openPremiumTopupModal}
                {openTariffChangeModal}
                {primaryPayActionLabel}
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
                {telegramProfileName}
                {user}
                {userAgreementUrl}
                {userLanguage}
                linkTelegramAccount={accountStore.linkTelegramAccount}
                logout={accountStore.logout}
                {openAdminPanel}
                {openExternalLink}
                openLinkEmailDialog={accountStore.openLinkEmailDialog}
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
        {/if}

        {#if toastText}
          <div class="toast" role="status">{toastText}</div>
        {/if}
      </div>
    {/if}
  {/key}
</Tooltip.Provider>
