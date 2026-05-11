<script>
  import { Bitcoin, CreditCard } from "lucide-svelte";
  import { onMount } from "svelte";
  import { Tooltip } from "bits-ui";

  import BrandMark from "./BrandMark.svelte";
  import PreviewBoard from "./PreviewBoard.svelte";
  import AdminPanel from "./admin/AdminPanel.svelte";
  import WebAppShell from "./webapp/WebAppShell.svelte";
  import AuthScreen from "./webapp/auth/AuthScreen.svelte";
  import PaymentDialogs from "./webapp/PaymentDialogs.svelte";
  import TariffDialogs from "./webapp/TariffDialogs.svelte";
  import DevicesScreen from "./webapp/screens/DevicesScreen.svelte";
  import HomeScreen from "./webapp/screens/HomeScreen.svelte";
  import InviteScreen from "./webapp/screens/InviteScreen.svelte";
  import SettingsScreen from "./webapp/screens/SettingsScreen.svelte";

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
  import { applyFavicon, readJsonScript, structuredCloneSafe } from "./lib/webapp/browser.js";
  import { createApiClient } from "./lib/webapp/publicApi.js";
  import { createI18n } from "./lib/webapp/i18n.js";
  import {
    formatMoney as fmtMoney,
    formatTrafficGb as fmtTrafficGb,
    formatTrafficBytes as fmtTrafficBytes,
    formatCompactNumber as fmtCompactNumber,
    normalizedEmail as fmtNormalizedEmail,
    telegramName as fmtTelegramName,
  } from "./lib/webapp/formatters.js";
  import {
    buildTariffCatalog as buildTariffCatalogFn,
    activeTariffName as activeTariffNameFn,
    planKey as planKeyFn,
    planDisplayTitle as planDisplayTitleFn,
    planSubtitle as planSubtitleFn,
    planUnitHint as planUnitHintFn,
    tariffLimitLabel as tariffLimitLabelFn,
    actionKey as actionKeyFn,
    priceLabel as priceLabelFn,
  } from "./lib/webapp/tariffs.js";
  import {
    trafficPercent as trafficPercentFn,
    trafficLabel as trafficLabelFn,
    trafficResetLabel as trafficResetLabelFn,
    premiumTrafficPercent as premiumTrafficPercentFn,
    premiumTrafficLabel as premiumTrafficLabelFn,
    premiumTitle as premiumTitleFn,
    premiumTrafficLeftLabel as premiumTrafficLeftLabelFn,
    premiumTopupBalanceLabel as premiumTopupBalanceLabelFn,
    premiumServerLabels as premiumServerLabelsFn,
    isForeverSubscription as isForeverSubscriptionFn,
    activeSubscriptionTermLabel as activeSubscriptionTermLabelFn,
  } from "./lib/webapp/traffic.js";
  import { buildGravatarUrl } from "./lib/webapp/gravatar.js";
  import { createBillingActions } from "./lib/webapp/billingActions.js";
  import {
    readReferralParam as readReferralParamHelper,
    readTelegramAuthStatus,
    readMagicLoginToken,
    readTelegramLoginWidgetAuthData,
    clearAuthQuery,
    buildTelegramOAuthStartUrl as buildTelegramOAuthStartUrlHelper,
    emailError as emailErrorHelper,
  } from "./lib/webapp/authHelpers.js";
  import {
    clearManualLogoutFlag as clearManualLogoutFlagInStorage,
    clearStoredToken,
    CSRF_COOKIE_NAME,
    isManuallyLoggedOut as readManualLogoutFlag,
    markManualLogout as markManualLogoutInStorage,
    persistToken,
    readCookie,
    readStoredToken,
  } from "./lib/webapp/session.js";
  import { createTelegramSdk } from "./lib/webapp/telegramSdk.js";
  import { mockApi as runMockApi } from "./lib/webapp/mockApi.js";
  import { DEV_MOCK, applyPreviewMock } from "./lib/webapp/previewMock.js";
  import {
    adminSectionFromPath,
    adminUserIdFromPath,
    normalizeSection,
    sectionFromPath,
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
  const I18N = injectedI18n || {};
  let telegramSdkStatus = "idle";
  let telegramMiniAppInitData = "";

  let mode = isPreviewBoard ? "preview" : "loading";
  let activeTab = "home";
  let screen = "home";
  let data = isPreviewBoard ? structuredCloneSafe(DEV_MOCK.data) : null;
  let selectedPlan = null;
  let selectedMethod = "";
  let paymentModalOpen = query.get("payment") === "1";
  let paymentStep = "tariff";
  let selectedTariffKey = "";
  let topupModalOpen = query.get("topup") === "1";
  let topupKind = "regular";
  let deviceTopupModalOpen = query.get("device_topup") === "1";
  let changeModalOpen = query.get("change") === "1";
  let topupOptions = null;
  let topupOptionsRequestId = 0;
  let deviceTopupOptions = null;
  let changeOptions = null;
  let selectedTopupPlan = null;
  let selectedDeviceTopupPlan = null;
  let selectedChangeTarget = null;
  let selectedChangeAction = null;
  let changeConfirmOpen = false;
  let tariffActionBusy = false;
  let payBusy = false;
  let trialBusy = false;
  let linkEmailOpen = false;
  let linkEmailBusy = false;
  let linkTelegramBusy = false;
  let linkEmailValue = "";
  let linkEmailPending = "";
  let linkEmailCode = "";
  let linkEmailStatus = "";
  let linkEmailIsError = false;
  let linkEmailFieldError = "";
  let promoCode = "";
  let promoBusy = false;
  let promoStatus = "";
  let promoIsError = false;
  let promoFieldError = "";
  let devicesData = DEV_MOCK.data.devices;
  let devicesLoaded = false;
  let devicesBusy = false;
  let devicesStatus = "";
  let devicesIsError = false;
  let deviceConfirmOpen = false;
  let deviceToDisconnect = null;
  let deviceDisconnectBusy = false;
  let toastText = "";
  let toastTimer = null;
  let authStatus = "";
  let authIsError = false;
  let authBusy = false;
  let telegramLoginBusy = false;
  let telegramLoginWatchdogTimer = null;
  let telegramLoginAttemptId = 0;
  let loginEmailFieldError = "";
  let loginEmailTooltipOpen = false;
  let authResendCooldown = 0;
  let authResendTimer = null;
  let languageBusy = false;
  let languageMenuOpen = false;
  let languageClickGuard = false;
  let languageClickGuardArmed = false;
  let languageClickGuardTimer = null;
  let languageClickGuardArmTimer = null;
  let email = "";
  let pendingEmail = "";
  let emailCode = "";
  let emailAvatarUrl = "";
  let avatarHashToken = "";
  let token = MOCK ? "local-preview" : readStoredToken();
  let csrfToken = MOCK ? "" : readCookie(CSRF_COOKIE_NAME) || "";
  let linkEmailResendCooldown = 0;
  let linkEmailResendTimer = null;
  let scrollLockApplied = false;
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
  const apiClient = createApiClient({
    apiBase: CFG.apiBase,
    csrfCookieName: CSRF_COOKIE_NAME,
    getToken: () => token,
    getCsrfToken: () => csrfToken,
    onUnauthorized: () => {
      clearToken();
      showLogin();
    },
    mockApi: MOCK
      ? (path, options, context) => runMockApi(path, options, context)
      : null,
    getMockContext: () => ({ currentLang, normalizeLangCode, clone: structuredCloneSafe }),
  });
  const billing = createBillingActions({ api: (path, options) => apiClient.api(path, options), t: (...args) => t(...args) });


  $: brandTitle = CFG.title || "/minishop";
  $: brandEmoji = CFG.logoEmoji || "🫥";
  $: accent = CFG.primaryColor || "#00fe7a";
  $: plans = data?.plans?.length ? data.plans : DEV_MOCK.data.plans;
  $: methods = data?.payment_methods?.length ? data.payment_methods : [];
  $: appSettings = data?.settings || DEV_MOCK.data.settings;
  $: trafficMode = Boolean(appSettings?.traffic_mode);
  $: tariffMode = plans.some((plan) => plan?.tariff_key);
  $: tariffCatalog = buildTariffCatalog(plans);
  $: singleTariffMode = tariffMode && tariffCatalog.length === 1;
  $: hasMultipleTariffs = tariffCatalog.length > 1;
  $: selectedTariff = tariffCatalog.find((tariff) => tariff.key === selectedTariffKey) || null;
  $: selectedTariffPlans = tariffMode ? (selectedTariffKey ? plans.filter((plan) => plan?.tariff_key === selectedTariffKey) : []) : plans;
  $: devicesEnabled = Boolean(appSettings?.my_devices_enabled);
  $: subscription = data?.subscription || DEV_MOCK.data.subscription;
  $: hasActiveTariffSubscription = Boolean(tariffMode && subscription?.active && subscription?.tariff_key);
  $: canChangeTariff = Boolean(hasActiveTariffSubscription && hasMultipleTariffs);
  $: currentTariffName = activeTariffName(subscription, plans);
  $: canOpenRegularTopupModal = Boolean(
    hasActiveTariffSubscription &&
      (subscription?.can_topup_regular_traffic ?? subscription?.can_topup_traffic) &&
      Number(subscription?.traffic_limit_bytes || 0) > 0,
  );
  $: canOpenPremiumTopupModal = Boolean(
    hasActiveTariffSubscription &&
      (subscription?.can_topup_premium_traffic ?? subscription?.can_topup_traffic) &&
      Number(subscription?.premium_limit_bytes || 0) > 0,
  );
  $: canOpenTopupModal = Boolean(canOpenRegularTopupModal || canOpenPremiumTopupModal);
  $: canShowTopupButton = Boolean(
    canOpenTopupModal &&
      (trafficPercent(subscription) >= 85 || premiumTrafficPercent(subscription) >= 85),
  );
  $: user = data?.user || {};
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
  $: currentLanguageOption = languageOptions.find((option) => option.value === currentLang) || languageOptions[0];
  $: userLanguage = languageName(currentLang);
  $: telegramLinkStatus = user?.telegram_linked ? t("wa_settings_linked") : t("wa_settings_not_linked");
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
    (!telegramMiniAppAuthAvailable && !telegramOAuthClientId && telegramSdkStatus !== "loading");
  $: telegramLoginChecking = telegramLoginBusy || (authBusy && authStatus === t("wa_auth_checking_telegram"));
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
  $: applyFavicon(CFG.logoUrl, brandEmoji);
  $: syncBodyScrollLock(paymentModalOpen || changeModalOpen || changeConfirmOpen || topupModalOpen || deviceTopupModalOpen || linkEmailOpen);
  $: if (!tariffMode && !selectedPlan && plans.length) selectedPlan = plans[Math.min(1, plans.length - 1)];
  $: if (singleTariffMode && tariffCatalog[0]?.key && selectedTariffKey !== tariffCatalog[0].key) {
    selectedTariffKey = tariffCatalog[0].key;
    selectedPlan = plans.find((plan) => plan?.tariff_key === selectedTariffKey) || null;
    if (paymentStep === "tariff") paymentStep = "checkout";
  }
  $: if (tariffMode && selectedTariffKey && !tariffCatalog.some((tariff) => tariff.key === selectedTariffKey)) {
    selectedTariffKey = "";
    selectedPlan = null;
    paymentStep = singleTariffMode ? "checkout" : "tariff";
  }
  $: if (tariffMode && selectedTariffKey && (!selectedPlan || selectedPlan.tariff_key !== selectedTariffKey)) {
    selectedPlan = selectedTariffPlans[0] || null;
  }
  $: if (!selectedMethod && methods.length) selectedMethod = methods[0].id;
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
      if (mode === "app") {
        if (section === "admin" && isAdmin) {
          screen = "admin";
          return;
        }
        const nextSection = section === "devices" && !devicesEnabled ? "home" : section;
        activeTab = nextSection;
        screen = nextSection;
        if (nextSection === "devices") loadDevices();
      }
    };
    window.addEventListener("popstate", onPopState);
    window.addEventListener("pointerdown", onAnyPointerDown);
    boot();
    return () => {
      window.removeEventListener("popstate", onPopState);
      window.removeEventListener("pointerdown", onAnyPointerDown);
      stopTelegramLoginWatchdog();
      clearCooldownTimer("auth");
      clearCooldownTimer("link_email");
      clearLanguageClickGuard();
      syncBodyScrollLock(false);
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
    languageClickGuardTimer = window.setTimeout(() => {
      languageClickGuard = false;
      languageClickGuardTimer = null;
    }, 260);
  }


  const i18n = createI18n({
    messages: I18N,
    defaultLang: "ru",
    getLang: () => user?.language_code || CFG.language || "ru",
  });
  const normalizeLangCode = i18n.normalizeLangCode;
  const t = i18n.t;
  const termUnitLabel = i18n.termUnitLabel;
  const languageName = i18n.languageName;


  function resolveTelegramWebApp() {
    return telegramSdk.tg;
  }

  function refreshTelegramWebApp() {
    tg = telegramSdk.refresh();
    telegramMiniAppInitData = telegramSdk.initData;
    return tg;
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

  async function ensureTelegramSdkForAction() {
    tg = await telegramSdk.ensureForAction();
    telegramMiniAppInitData = telegramSdk.initData;
    return tg;
  }

  function createTelegramMiniAppAuthTimeout() {
    return telegramSdk.createMiniAppAuthTimeout();
  }

  function shouldWaitForTelegramSdkBeforeOAuth() {
    return hasTelegramLaunchParams() || !telegramOAuthClientId;
  }

  async function boot() {
    mode = "loading";
    if (hasTelegramLaunchParams()) await loadTelegramSdk(TELEGRAM_SDK_BOOT_TIMEOUT_MS);

    if (tg) {
      try {
        tg.ready();
        tg.expand();
      } catch {}
    }

    if (MOCK) {
      await loadData();
      return;
    }

    const magicToken = readMagicLoginToken();
    if (magicToken && (await finalizeMagicLogin(magicToken))) return;

    const telegramAuthStatus = readTelegramAuthStatus();
    if (telegramAuthStatus === "success") {
      clearManualLogoutFlag();
      clearAuthQuery();
      try {
        await loadData();
        return;
      } catch {
        clearToken();
      }
    } else if (telegramAuthStatus) {
      clearAuthQuery();
      setAuthStatus(
        telegramAuthStatus === "cancelled" ? t("wa_auth_telegram_cancelled") : t("wa_auth_telegram_not_confirmed"),
        true,
      );
    }

    if (isManuallyLoggedOut()) {
      showLogin();
      return;
    }

    const widgetAuthData = readTelegramLoginWidgetAuthData();
    if (widgetAuthData && (await finalizeTelegramAuth(widgetAuthData, "auth_data"))) return;

    const initData = telegramMiniAppInitData || tg?.initData || readTelegramMiniAppInitDataFromLocation();
    if (initData) {
      try {
        if (await finalizeTelegramAuth(initData, "init_data")) return;
      } catch {}
    }

    if (token || csrfToken) {
      try {
        await loadData();
        return;
      } catch {
        clearToken();
      }
    }

    showLogin();
  }

  async function loadData() {
    const payload = await api("/me");
    if (!payload.ok) throw new Error(payload.error || "load_failed");
    data = payload;
    selectedPlan = null;
    selectedTariffKey = "";
    paymentStep = "tariff";
    selectedMethod = payload.payment_methods?.[0]?.id || "";
    let section = MOCK && query.get("screen") ? normalizeSection(query.get("screen")) : sectionFromPath(window.location.pathname);
    if (section === "admin" && !payload.user?.is_admin) section = "settings";
    if (section === "devices" && !payload.settings?.my_devices_enabled) section = "home";
    activeTab = section === "admin" ? "settings" : section;
    screen = section;
    mode = "app";
    syncSectionPath(
      section,
      true,
      section === "admin" ? adminSectionFromPath(window.location.pathname) : null,
    );
    if (section === "devices" && payload.settings?.my_devices_enabled) {
      await loadDevices();
    }
    if (topupModalOpen) await loadTopupOptions();
    if (deviceTopupModalOpen) await loadDeviceTopupOptions();
    if (changeModalOpen) await loadTariffChangeOptions();
  }

  function showLogin() {
    mode = "login";
    screen = "login";
    activeTab = "home";
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
    if (token && !MOCK) persistToken(token);
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

  function readReferralParam() {
    return readReferralParamHelper(tg);
  }

  function buildTelegramOAuthStartUrl(purpose = "login") {
    return buildTelegramOAuthStartUrlHelper(purpose, tg);
  }

  function emailError(error, fallback) {
    return emailErrorHelper(error, fallback, t);
  }

  async function finalizeMagicLogin(loginToken) {
    if (authBusy) return false;
    authBusy = true;
    setAuthStatus(t("wa_auth_checking_login"));
    try {
      const payload = { token: loginToken };
      const referralParam = readReferralParam();
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/magic", payload);
      if (response.ok && response.token) {
        setToken(response.token, response.csrf_token);
        clearAuthQuery();
        await loadData();
        return true;
      }
      setAuthStatus(t("wa_auth_login_confirm_failed"), true);
    } catch {
      setAuthStatus(t("wa_auth_login_confirm_failed"), true);
    } finally {
      authBusy = false;
    }
    return false;
  }

  async function finalizeTelegramAuth(authData, source = "auth_data", options = {}) {
    if (authBusy) return false;
    authBusy = true;
    setAuthStatus(t("wa_auth_checking_telegram"));
    try {
      const payload =
        source === "init_data"
          ? { init_data: authData }
          : source === "id_token"
            ? { id_token: authData.id_token, nonce: authData.nonce }
            : { auth_data: authData };
      const referralParam = readReferralParam();
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/token", payload, { signal: options.signal });
      if (response.ok && response.token) {
        setToken(response.token, response.csrf_token);
        clearAuthQuery();
        setAuthStatus("");
        await loadData();
        return true;
      }
      setAuthStatus(response.error === "banned" ? t("wa_auth_access_denied") : t("wa_auth_telegram_not_confirmed"), true);
    } catch (error) {
      setAuthStatus(
        error?.name === "AbortError" ? t("wa_auth_telegram_timeout") : t("wa_auth_telegram_unavailable"),
        true,
      );
    } finally {
      authBusy = false;
    }
    return false;
  }

  async function requestEmailCode() {
    if (screen === "code" && authResendCooldown > 0) return;
    const normalized = email.trim().toLowerCase();
    if (!normalized || !normalized.includes("@")) {
      loginEmailFieldError = t("wa_auth_invalid_email");
      loginEmailTooltipOpen = true;
      return;
    }
    loginEmailFieldError = "";
    loginEmailTooltipOpen = false;
    authBusy = true;
    setAuthStatus(t("wa_auth_sending_code"));
    try {
      const payload = { email: normalized, language: currentLang };
      const referralParam = readReferralParam();
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/request", payload);
      if (!response.ok) throw response;
      pendingEmail = normalized;
      emailCode = "";
      screen = "code";
      mode = "login";
      setAuthStatus("");
      startCooldownTimer("auth", 60);
    } catch (error) {
      setAuthStatus(emailError(error, t("wa_auth_send_code_failed")), true);
    } finally {
      authBusy = false;
    }
  }

  async function verifyEmailCode() {
    const code = emailCode.replace(/\D/g, "").slice(0, 6);
    if (code.length !== 6) {
      setAuthStatus(t("wa_auth_enter_code_6digits"), true);
      return;
    }
    authBusy = true;
    setAuthStatus(t("wa_auth_checking_code"));
    try {
      const payload = { email: pendingEmail, code };
      const referralParam = readReferralParam();
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/verify", payload);
      if (!response.ok || !response.token) throw response;
      setToken(response.token, response.csrf_token);
      await loadData();
      setAuthStatus("");
    } catch (error) {
      setAuthStatus(emailError(error, t("wa_auth_invalid_code")), true);
    } finally {
      authBusy = false;
    }
  }

  function setAuthStatus(message, isError = false) {
    authStatus = message;
    authIsError = isError;
  }

  function clearCooldownTimer(kind) {
    if (kind === "auth") {
      if (authResendTimer) {
        window.clearInterval(authResendTimer);
        authResendTimer = null;
      }
      return;
    }
    if (linkEmailResendTimer) {
      window.clearInterval(linkEmailResendTimer);
      linkEmailResendTimer = null;
    }
  }

  function submitEmailOnEnter(event) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    requestEmailCode();
  }

  function startCooldownTimer(kind, seconds = 60) {
    if (kind === "auth") {
      clearCooldownTimer("auth");
      authResendCooldown = Math.max(0, Number(seconds || 60));
      authResendTimer = window.setInterval(() => {
        if (authResendCooldown <= 1) {
          authResendCooldown = 0;
          clearCooldownTimer("auth");
          return;
        }
        authResendCooldown -= 1;
      }, 1000);
      return;
    }
    clearCooldownTimer("link_email");
    linkEmailResendCooldown = Math.max(0, Number(seconds || 60));
    linkEmailResendTimer = window.setInterval(() => {
      if (linkEmailResendCooldown <= 1) {
        linkEmailResendCooldown = 0;
        clearCooldownTimer("link_email");
        return;
      }
      linkEmailResendCooldown -= 1;
    }, 1000);
  }

  function startTelegramLoginWatchdog() {
    stopTelegramLoginWatchdog();
    telegramLoginAttemptId += 1;
    const attemptId = telegramLoginAttemptId;
    telegramLoginWatchdogTimer = window.setTimeout(() => {
      if (attemptId !== telegramLoginAttemptId) return;
      telegramLoginWatchdogTimer = null;
      telegramSdkStatus = "unavailable";
      telegramLoginBusy = false;
      authBusy = false;
      setAuthStatus(t("wa_auth_telegram_timeout"), true);
    }, TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS);
    return attemptId;
  }

  function stopTelegramLoginWatchdog(attemptId = null) {
    if (attemptId !== null && attemptId !== telegramLoginAttemptId) return;
    if (telegramLoginWatchdogTimer) {
      window.clearTimeout(telegramLoginWatchdogTimer);
      telegramLoginWatchdogTimer = null;
    }
  }

  function isActiveTelegramLoginAttempt(attemptId) {
    return attemptId === telegramLoginAttemptId && telegramLoginBusy;
  }

  async function openTelegramLogin() {
    if (authBusy || telegramLoginBusy || telegramLoginUnavailable) return;
    setAuthStatus("");

    const isTelegramMiniAppAttempt = hasTelegramLaunchParams();
    if (!isTelegramMiniAppAttempt && telegramOAuthClientId) {
      telegramLoginBusy = true;
      window.location.assign(buildTelegramOAuthStartUrl("login"));
      window.setTimeout(() => {
        telegramLoginBusy = false;
      }, 1500);
      return;
    }

    telegramLoginBusy = true;
    const attemptId = startTelegramLoginWatchdog();
    const loginTimeout = createTelegramMiniAppAuthTimeout();
    try {
      await Promise.race([
        (async () => {
          await ensureTelegramSdkForAction();
          if (!isActiveTelegramLoginAttempt(attemptId)) return;
          const initData = telegramMiniAppInitData || tg?.initData || readTelegramMiniAppInitDataFromLocation();
          if (initData) {
            await finalizeTelegramAuth(initData, "init_data", { signal: loginTimeout.signal });
            return;
          }

          if (!telegramOAuthClientId) {
            setAuthStatus(
              telegramSdkStatus === "unavailable"
                ? t("wa_auth_telegram_unavailable")
                : t("wa_auth_telegram_not_configured"),
              true,
            );
            return;
          }

          window.location.assign(buildTelegramOAuthStartUrl("login"));
        })(),
        loginTimeout.promise,
      ]);
    } catch (error) {
      if (!isActiveTelegramLoginAttempt(attemptId)) return;
      if (error?.name === "AbortError") {
        telegramSdkStatus = "unavailable";
        setAuthStatus(t("wa_auth_telegram_timeout"), true);
      } else {
        setAuthStatus(t("wa_auth_telegram_unavailable"), true);
      }
    } finally {
      loginTimeout.clear();
      if (loginTimeout.timedOut) {
        telegramSdkStatus = "unavailable";
        setAuthStatus(t("wa_auth_telegram_timeout"), true);
        authBusy = false;
      }
      if (isActiveTelegramLoginAttempt(attemptId)) {
        stopTelegramLoginWatchdog(attemptId);
        telegramLoginBusy = false;
      }
    }
  }

  function setLinkEmailStatus(message, isError = false) {
    linkEmailStatus = message;
    linkEmailIsError = isError;
  }

  function openLinkEmailDialog() {
    linkEmailOpen = true;
    linkEmailBusy = false;
    linkEmailCode = "";
    linkEmailPending = "";
    linkEmailStatus = "";
    linkEmailIsError = false;
    linkEmailFieldError = "";
    linkEmailValue = user?.email || "";
    linkEmailResendCooldown = 0;
    clearCooldownTimer("link_email");
  }

  function closeLinkEmailDialog() {
    linkEmailOpen = false;
    linkEmailBusy = false;
    linkEmailCode = "";
    linkEmailPending = "";
    linkEmailStatus = "";
    linkEmailIsError = false;
    linkEmailFieldError = "";
    linkEmailResendCooldown = 0;
    clearCooldownTimer("link_email");
  }

  async function requestLinkEmailCode() {
    if (linkEmailPending && linkEmailResendCooldown > 0) return;
    const normalized = String(linkEmailValue || "").trim().toLowerCase();
    if (!normalized || !normalized.includes("@")) {
      linkEmailFieldError = t("wa_auth_invalid_email");
      return;
    }
    linkEmailFieldError = "";
    linkEmailBusy = true;
    setLinkEmailStatus(t("wa_auth_sending_code"));
    try {
      const response = await api("/account/email/request", {
        method: "POST",
        body: JSON.stringify({ email: normalized }),
      });
      if (!response?.ok) throw response;
      linkEmailPending = normalized;
      linkEmailCode = "";
      setLinkEmailStatus("");
      startCooldownTimer("link_email", 60);
    } catch (error) {
      setLinkEmailStatus(emailError(error, t("wa_auth_send_code_failed")), true);
    } finally {
      linkEmailBusy = false;
    }
  }

  async function verifyLinkEmailCode() {
    const code = String(linkEmailCode || "").replace(/\D/g, "").slice(0, 6);
    if (!linkEmailPending) {
      setLinkEmailStatus(t("wa_auth_send_code_failed"), true);
      return;
    }
    if (code.length !== 6) {
      setLinkEmailStatus(t("wa_auth_enter_code_6digits"), true);
      return;
    }
    linkEmailBusy = true;
    setLinkEmailStatus(t("wa_auth_checking_code"));
    try {
      const response = await api("/account/email/verify", {
        method: "POST",
        body: JSON.stringify({ email: linkEmailPending, code }),
      });
      if (!response?.ok) throw response;
      if (response?.token) setToken(response.token, response.csrf_token);
      await loadData();
      closeLinkEmailDialog();
      showToast(t("wa_settings_linked"));
    } catch (error) {
      setLinkEmailStatus(emailError(error, t("wa_auth_invalid_code")), true);
    } finally {
      linkEmailBusy = false;
    }
  }

  async function linkTelegramAccountWithPayload(payload) {
    linkTelegramBusy = true;
    try {
      const response = await api("/account/telegram/link", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      if (response?.token) setToken(response.token, response.csrf_token);
      await loadData();
      showToast(t("wa_settings_linked"));
    } catch (error) {
      showToast(error?.message || t("wa_auth_telegram_not_confirmed"));
    } finally {
      linkTelegramBusy = false;
    }
  }

  async function linkTelegramAccount() {
    if (linkTelegramBusy) return;
    if (shouldWaitForTelegramSdkBeforeOAuth()) await ensureTelegramSdkForAction();
    const initData = telegramMiniAppInitData || tg?.initData || readTelegramMiniAppInitDataFromLocation();
    if (initData) {
      await linkTelegramAccountWithPayload({ init_data: initData });
      return;
    }
    if (!telegramOAuthClientId) {
      showToast(
        telegramSdkStatus === "unavailable" ? t("wa_auth_telegram_unavailable") : t("wa_auth_telegram_not_configured"),
      );
      return;
    }
    linkTelegramBusy = true;
    window.location.assign(buildTelegramOAuthStartUrl("link"));
  }

  async function updateAccountLanguage(nextValue) {
    const language = normalizeLangCode(nextValue);
    if (!language || languageBusy || language === currentLang) return;
    languageBusy = true;
    try {
      const response = await api("/account/language", {
        method: "POST",
        body: JSON.stringify({ language }),
      });
      if (!response?.ok) throw response;
      if (data?.user) {
        const updatedLanguage = normalizeLangCode(response.language || language);
        data = {
          ...data,
          user: {
            ...data.user,
            language_code: updatedLanguage,
          },
        };
      }
      const previousScreen = screen;
      const previousTab = activeTab;
      const payload = await api("/me");
      if (payload?.ok) {
        data = payload;
        selectedPlan = null;
        selectedTariffKey = "";
        paymentStep = "tariff";
        selectedMethod = payload.payment_methods?.[0]?.id || "";
        mode = "app";
        screen = previousScreen;
        activeTab = previousTab;
      }
    } catch {
      showToast(t("wa_settings_language_update_failed"));
    } finally {
      languageBusy = false;
    }
  }

  async function createPayment() {
    if (!selectedPlan || !selectedMethod || payBusy) return;
    payBusy = true;
    try {
      const response = await billing.postPayment(billing.planPaymentBody(selectedPlan, selectedMethod));
      if (!response.ok) throw response;
      showToast(t("wa_payment_created"));
      if (response.action === "open_invoice") {
        if (!response.payment_url) throw response;
        openTelegramInvoice(response.payment_url);
      } else if (response.action === "invoice_sent") {
        paymentModalOpen = false;
        return;
      } else {
        if (!response.payment_url) throw response;
        openExternalLink(response.payment_url);
      }
      paymentModalOpen = false;
    } catch (error) {
      showToast(error?.message || t("wa_payment_create_failed"));
    } finally {
      payBusy = false;
    }
  }

  async function loadTopupOptions(kind = topupKind) {
    if (topupOptions?.topup_kind === kind) return;
    const requestId = ++topupOptionsRequestId;
    tariffActionBusy = true;
    try {
      topupOptions = null;
      selectedTopupPlan = null;
      const response = await billing.fetchTopupOptions(kind);
      if (requestId !== topupOptionsRequestId || kind !== topupKind) return;
      if (!response?.ok) throw response;
      topupOptions = response;
      selectedTopupPlan = response.plans?.[0] || null;
    } catch (error) {
      if (requestId !== topupOptionsRequestId || kind !== topupKind) return;
      showToast(error?.message || t("wa_tariff_options_failed"));
      topupModalOpen = false;
    } finally {
      if (requestId === topupOptionsRequestId) tariffActionBusy = false;
    }
  }

  async function loadTariffChangeOptions() {
    if (changeOptions || tariffActionBusy) return;
    tariffActionBusy = true;
    try {
      const response = await billing.fetchTariffChangeOptions();
      if (!response?.ok) throw response;
      changeOptions = response;
      selectedChangeTarget = response.targets?.[0] || null;
      selectedChangeAction = selectedChangeTarget?.actions?.[0] || null;
    } catch (error) {
      showToast(error?.message || t("wa_tariff_options_failed"));
      changeModalOpen = false;
    } finally {
      tariffActionBusy = false;
    }
  }

  async function createTopupPayment() {
    if (!selectedTopupPlan || !selectedMethod || payBusy) return;
    payBusy = true;
    try {
      const response = await billing.postPayment(
        billing.topupPaymentBody(selectedTopupPlan, selectedMethod, topupOptions?.tariff_key),
      );
      if (!response.ok || !response.payment_url) throw response;
      showToast(t("wa_payment_created"));
      openExternalLink(response.payment_url);
      topupModalOpen = false;
    } catch (error) {
      showToast(error?.message || t("wa_payment_create_failed"));
    } finally {
      payBusy = false;
    }
  }

  async function loadDeviceTopupOptions() {
    if (deviceTopupOptions || tariffActionBusy) return;
    tariffActionBusy = true;
    try {
      const response = await billing.fetchDeviceTopupOptions();
      if (!response?.ok) throw response;
      deviceTopupOptions = response;
      selectedDeviceTopupPlan = response.plans?.[0] || null;
    } catch (error) {
      showToast(error?.message || t("wa_device_topup_options_failed"));
      deviceTopupModalOpen = false;
    } finally {
      tariffActionBusy = false;
    }
  }

  async function createDeviceTopupPayment() {
    if (!selectedDeviceTopupPlan || !selectedMethod || payBusy) return;
    payBusy = true;
    try {
      const response = await billing.postPayment(
        billing.deviceTopupPaymentBody(selectedDeviceTopupPlan, selectedMethod, deviceTopupOptions?.tariff_key),
      );
      if (!response.ok || !response.payment_url) throw response;
      showToast(t("wa_payment_created"));
      openExternalLink(response.payment_url);
      deviceTopupModalOpen = false;
    } catch (error) {
      showToast(error?.message || t("wa_payment_create_failed"));
    } finally {
      payBusy = false;
    }
  }

  async function applyTariffChange() {
    if (!selectedChangeTarget || !selectedChangeAction || tariffActionBusy) return;
    if (selectedChangeAction.kind === "payment") {
      await createTariffChangePayment();
      return;
    }
    tariffActionBusy = true;
    try {
      const response = await billing.postTariffChange({
        tariff_key: selectedChangeTarget.tariff_key,
        mode: selectedChangeAction.mode,
      });
      if (!response?.ok) throw response;
      showToast(t("wa_tariff_change_applied"));
      changeConfirmOpen = false;
      changeModalOpen = false;
      changeOptions = null;
      await loadData();
    } catch (error) {
      showToast(error?.message || t("wa_tariff_change_failed"));
    } finally {
      tariffActionBusy = false;
    }
  }

  async function createTariffChangePayment() {
    if (!selectedChangeTarget || !selectedChangeAction || !selectedMethod || payBusy) return;
    payBusy = true;
    try {
      const body = billing.changePaymentBody(selectedChangeAction, selectedChangeTarget, selectedMethod);
      const response =
        selectedChangeAction.mode === "buy_package" || selectedChangeAction.mode === "buy_period"
          ? await billing.postPayment(body)
          : await billing.postTariffChangePayment(body);
      if (!response.ok || !response.payment_url) throw response;
      showToast(t("wa_payment_created"));
      openExternalLink(response.payment_url);
      changeConfirmOpen = false;
      changeModalOpen = false;
    } catch (error) {
      showToast(error?.message || t("wa_payment_create_failed"));
    } finally {
      payBusy = false;
    }
  }

  function openExternalLink(url) {
    if (!url) return;
    if (tg?.openLink) {
      tg.openLink(url);
      return;
    }
    window.location.assign(url);
  }

  function openTelegramInvoice(url) {
    if (!url) return;
    if (tg?.openInvoice) {
      tg.openInvoice(url, (status) => {
        if (status === "paid") {
          showToast(t("wa_payment_success", {}, "Payment successful"));
          loadData();
        } else if (status === "failed") {
          showToast(t("wa_payment_create_failed"));
        }
      });
      return;
    }
    openExternalLink(url);
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

  async function loadDevices(force = false) {
    if (!devicesEnabled || devicesBusy || (devicesLoaded && !force)) return;
    devicesBusy = true;
    devicesStatus = "";
    devicesIsError = false;
    try {
      const response = await api("/devices");
      if (!response?.ok) throw response;
      devicesData = response;
      devicesLoaded = true;
    } catch (error) {
      devicesStatus = error?.message || t("wa_devices_load_failed");
      devicesIsError = true;
      devicesLoaded = true;
    } finally {
      devicesBusy = false;
    }
  }

  function openDeviceDisconnectDialog(device) {
    deviceToDisconnect = device;
    deviceConfirmOpen = true;
  }

  function closeDeviceDisconnectDialog() {
    if (deviceDisconnectBusy) return;
    deviceConfirmOpen = false;
    deviceToDisconnect = null;
  }

  async function disconnectDevice() {
    const token = String(deviceToDisconnect?.token || "").trim();
    if (!token || deviceDisconnectBusy) return;
    deviceDisconnectBusy = true;
    try {
      const response = await api("/devices/disconnect", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      if (!response?.ok) throw response;
      showToast(t("wa_device_disconnected"));
      deviceConfirmOpen = false;
      deviceToDisconnect = null;
      devicesLoaded = false;
      await loadDevices(true);
    } catch (error) {
      showToast(error?.message || t("wa_device_disconnect_failed"));
    } finally {
      deviceDisconnectBusy = false;
    }
  }

  async function logout() {
    markManualLogout();
    clearToken();
    try {
      await publicApi("/auth/logout", { keepalive: true });
    } catch {}
    showLogin();
  }

  function showToast(message) {
    toastText = message;
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      toastText = "";
    }, 2400);
  }

  function goHome() {
    paymentModalOpen = false;
    activeTab = "home";
    screen = "home";
    syncSectionPath("home");
  }

  function goInvite() {
    paymentModalOpen = false;
    activeTab = "invite";
    screen = "invite";
    syncSectionPath("invite");
  }

  function goDevices() {
    if (!devicesEnabled) return;
    paymentModalOpen = false;
    activeTab = "devices";
    screen = "devices";
    syncSectionPath("devices");
    loadDevices();
  }

  function openDeviceTopupModal() {
    selectedMethod = methods[0]?.id || "";
    deviceTopupModalOpen = true;
    loadDeviceTopupOptions();
  }

  function closeDeviceTopupModal() {
    deviceTopupModalOpen = false;
  }

  function goSettings() {
    paymentModalOpen = false;
    activeTab = "settings";
    screen = "settings";
    syncSectionPath("settings");
  }

  function openAdminPanel() {
    if (!isAdmin) return;
    paymentModalOpen = false;
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
    const targetPath = adminSection === "users" && adminUserId
      ? `/admin/users/${adminUserId}`
      : `/admin/${adminSection}`;
    if (window.location.pathname === targetPath) return;
    window.history.pushState(null, "", `${targetPath}${window.location.search}${window.location.hash}`);
  }

  async function handleTariffsSaved() {
    topupOptions = null;
    deviceTopupOptions = null;
    changeOptions = null;
    try {
      await loadData();
    } catch {
      // The admin save already succeeded; a later app refresh will pick up the new catalog.
    }
  }

  async function handleSettingsSaved() {
    topupOptions = null;
    deviceTopupOptions = null;
    changeOptions = null;
    try {
      await loadData();
    } catch {
      // Settings were saved; the next app refresh will pick up the runtime values.
    }
  }

  function openPaymentModal() {
    if (tariffMode) {
      if (singleTariffMode && tariffCatalog[0]?.key) {
        selectedTariffKey = tariffCatalog[0].key;
        selectedPlan = plans.find((plan) => plan?.tariff_key === selectedTariffKey) || null;
        paymentStep = "checkout";
      } else if (subscription?.active && subscription?.tariff_key && tariffCatalog.some((t) => t.key === subscription.tariff_key)) {
        selectedTariffKey = subscription.tariff_key;
        selectedPlan = plans.find((plan) => plan?.tariff_key === selectedTariffKey) || null;
        paymentStep = "checkout";
      } else {
        paymentStep = "tariff";
        selectedTariffKey = "";
        selectedPlan = null;
      }
    } else {
      paymentStep = "checkout";
    }
    paymentModalOpen = true;
  }

  function closePaymentModal() {
    paymentModalOpen = false;
  }

  function openTopupModal(kind = "regular") {
    if (kind === "premium" ? !canOpenPremiumTopupModal : !canOpenRegularTopupModal) return;
    if (topupKind !== kind) {
      topupOptions = null;
      selectedTopupPlan = null;
    }
    topupKind = kind;
    topupModalOpen = true;
    loadTopupOptions(kind);
  }

  function closeTopupModal() {
    if (payBusy || tariffActionBusy) return;
    topupModalOpen = false;
  }

  function openTariffChangeModal() {
    changeModalOpen = true;
    loadTariffChangeOptions();
  }

  function closeTariffChangeModal() {
    if (payBusy || tariffActionBusy) return;
    changeModalOpen = false;
    changeConfirmOpen = false;
  }

  function openTariffChangeConfirm() {
    if (!selectedChangeTarget || !selectedChangeAction || tariffActionBusy || payBusy) return;
    changeConfirmOpen = true;
  }

  function closeTariffChangeConfirm() {
    if (payBusy || tariffActionBusy) return;
    changeConfirmOpen = false;
  }

  function formatMoney(value, currency = CFG.currency || "RUB") {
    return fmtMoney(value, currency);
  }
  function priceLabel(plan, methodId = selectedMethod) {
    return priceLabelFn(plan, methodId);
  }
  function formatTrafficGb(value) {
    return fmtTrafficGb(value);
  }
  function formatTrafficBytes(value) {
    return fmtTrafficBytes(value);
  }
  function formatCompactNumber(value) {
    return fmtCompactNumber(value);
  }
  function normalizedEmail(value) {
    return fmtNormalizedEmail(value);
  }
  function telegramName(profile) {
    return fmtTelegramName(profile, t("wa_telegram_not_linked"));
  }
  function planKey(plan) {
    return planKeyFn(plan);
  }
  function buildTariffCatalog(planList) {
    return buildTariffCatalogFn(planList);
  }
  function activeTariffName(sub, planList) {
    return activeTariffNameFn(sub, planList);
  }
  function planDisplayTitle(plan) {
    return planDisplayTitleFn(plan, { trafficMode, t });
  }
  function planSubtitle(plan) {
    return planSubtitleFn(plan, { lang: currentLang });
  }
  function planUnitHint(plan) {
    return planUnitHintFn(plan, { trafficMode, selectedMethod, t });
  }
  function tariffLimitLabel(tariff) {
    return tariffLimitLabelFn(tariff, { t });
  }
  function actionKey(action) {
    return actionKeyFn(action);
  }
  function trafficPercent(sub) {
    return trafficPercentFn(sub);
  }
  function trafficLabel(sub) {
    return trafficLabelFn(sub, t);
  }
  function trafficResetLabel(sub) {
    return trafficResetLabelFn(sub, t);
  }
  function premiumTrafficPercent(sub) {
    return premiumTrafficPercentFn(sub);
  }
  function premiumTrafficLabel(sub) {
    return premiumTrafficLabelFn(sub, t);
  }
  function premiumTitle(sub = subscription) {
    return premiumTitleFn(sub, t);
  }
  function premiumTrafficLeftLabel(sub) {
    return premiumTrafficLeftLabelFn(sub);
  }
  function premiumTopupBalanceLabel(sub) {
    return premiumTopupBalanceLabelFn(sub);
  }
  function premiumServerLabels(sub) {
    return premiumServerLabelsFn(sub);
  }
  function isForeverSubscription(sub) {
    return isForeverSubscriptionFn(sub);
  }
  function activeSubscriptionTermLabel(sub) {
    return activeSubscriptionTermLabelFn(sub, { t, termUnitLabel });
  }

  function methodMeta(method) {
    const id = String(method?.id || "").toLowerCase();
    if (id.includes("platega_sbp")) {
      return { title: t("wa_method_platega_sbp_card"), icon: CreditCard };
    }
    if (id.includes("platega_crypto")) {
      return { title: t("wa_method_platega_crypto"), icon: Bitcoin };
    }
    if (id.includes("yookassa") || id.includes("card")) {
      return { title: t("pay_with_yookassa_button"), icon: null };
    }
    if (id.includes("severpay")) {
      return { title: t("pay_with_severpay_button"), icon: null };
    }
    if (id.includes("freekassa")) {
      return { title: t("pay_with_sbp_button"), icon: null };
    }
    if (id.includes("cryptopay")) {
      return { title: t("pay_with_cryptopay_button"), icon: null };
    }
    if (id.includes("stars")) {
      return { title: t("pay_with_stars_button"), icon: null };
    }
    if (id.includes("sbp")) {
      return { title: t("pay_with_sbp_button"), icon: null };
    }
    if (id.includes("crypto")) {
      return { title: t("pay_with_cryptopay_button"), icon: null };
    }
    return { title: t("wa_method_other_title"), icon: null };
  }

  function selectTariff(tariff) {
    const key = String(tariff?.key || "").trim();
    if (!key) return;
    selectedTariffKey = key;
    selectedPlan = plans.find((plan) => plan?.tariff_key === key) || null;
  }

  function continueWithSelectedTariff() {
    if (!selectedTariffKey) return;
    if (!selectedPlan) {
      selectedPlan = selectedTariffPlans[0] || null;
    }
    paymentStep = "checkout";
  }

  function backToTariffList() {
    if (subscription?.active && subscription?.tariff_key && tariffCatalog.some((t) => t.key === subscription.tariff_key)) {
      return;
    }
    paymentStep = "tariff";
  }

  function paymentTitle() {
    if (singleTariffMode) {
      return selectedTariff?.billing_model === "traffic" ? t("wa_traffic_packages_title") : t("wa_subscription_title");
    }
    if (tariffMode) return t("wa_tariffs_title");
    return trafficMode ? t("wa_traffic_packages_title") : t("wa_subscription_title");
  }

  function paymentDescription() {
    if (tariffMode) {
      if (singleTariffMode) {
        return selectedTariff?.billing_model === "traffic" ? t("wa_traffic_packages_choose") : t("wa_subscription_choose_period");
      }
      return paymentStep === "checkout" && selectedTariff
        ? t("wa_tariff_choose_period_payment", { tariff: selectedTariff.title })
        : t("wa_tariffs_choose");
    }
    return trafficMode ? t("wa_traffic_packages_choose") : t("wa_subscription_choose_period");
  }

  function primaryPayActionLabel() {
    if (trafficMode || selectedPlan?.sale_mode === "traffic_package") return t("wa_buy_traffic");
    return subscription.active ? t("wa_renew") : t("wa_pay_subscription");
  }

  function changeActionTitle(action) {
    const mode = String(action?.mode || "");
    if (mode === "recalc_days") {
      return t("wa_tariff_change_recalc_days", { days: Number(action?.days_after || 0) });
    }
    if (mode === "convert_days_to_gb") {
      return t("wa_tariff_change_convert_gb", { gb: formatCompactNumber(action?.converted_gb || 0) });
    }
    if (mode === "paid_diff") {
      return t("wa_tariff_change_pay_diff", { price: priceLabel(action) });
    }
    if (mode === "buy_package") {
      return t("wa_tariff_change_buy_package", { gb: formatCompactNumber(action?.traffic_gb || 0), price: priceLabel(action) });
    }
    if (mode === "buy_period") {
      return `${action?.title || ""} · ${priceLabel(action)}`;
    }
    return action?.title || mode;
  }

  function tariffChangeSummary() {
    if (!selectedChangeTarget || !selectedChangeAction) return [];
    const rows = [
      t("wa_tariff_change_confirm_target", { tariff: selectedChangeTarget.title }),
      t("wa_tariff_change_confirm_action", { action: changeActionTitle(selectedChangeAction) }),
    ];
    const mode = String(selectedChangeAction.mode || "");
    if (mode === "recalc_days") {
      rows.push(t("wa_tariff_change_confirm_recalc", { days: Number(selectedChangeAction.days_after || 0) }));
    } else if (mode === "convert_days_to_gb") {
      rows.push(t("wa_tariff_change_confirm_convert", { gb: formatCompactNumber(selectedChangeAction.converted_gb || 0) }));
    } else if (selectedChangeAction.kind === "payment") {
      rows.push(t("wa_tariff_change_confirm_payment", { price: priceLabel(selectedChangeAction) }));
    }
    return rows;
  }

  function topupWarningText() {
    const percent = Number(topupOptions?.traffic_percent || trafficPercent(subscription));
    const levels = topupOptions?.warning_levels?.length ? topupOptions.warning_levels.join(" / ") : "85 / 90 / 95";
    if (percent >= 95) return t("wa_topup_warning_critical", { percent, levels });
    if (percent >= 90) return t("wa_topup_warning_high", { percent, levels });
    if (percent >= 85) return t("wa_topup_warning_medium", { percent, levels });
    return t("wa_topup_warning_levels", { levels });
  }

  function topupModalDescription() {
    if (!topupOptions) return "";
    if (isPremiumTopupContext()) return topupOptions?.tariff_name ? t("wa_topup_for_tariff", { tariff: topupOptions.tariff_name }) : "";
    if (singleTariffMode) return "";
    return topupOptions?.tariff_name ? t("wa_topup_for_tariff", { tariff: topupOptions.tariff_name }) : "";
  }

  function isPremiumTopupContext() {
    if (selectedTopupPlan?.sale_mode === "premium_topup") return true;
    if (topupOptions?.topup_kind) return topupOptions.topup_kind === "premium";
    return topupKind === "premium";
  }

  function topupModalTitle() {
    if (isPremiumTopupContext()) return premiumTitle(topupOptions || subscription);
    return t("wa_topup_traffic");
  }

  function topupCarryoverNotes() {
    const plans = topupOptions?.plans || [];
    if (!plans.length) return [];
    return [
      t(
        "wa_topup_carryover",
        {},
        "Докупленный трафик не сгорает: сначала расходуется месячный лимит, затем докупленный остаток."
      ),
    ];
  }

  function deviceTopupModalDescription() {
    if (!deviceTopupOptions) return "";
    return deviceTopupOptions?.tariff_name ? t("wa_device_topup_for_tariff", { tariff: deviceTopupOptions.tariff_name }) : "";
  }

  function tariffChangeModalDescription() {
    if (!changeOptions) return "";
    return changeOptions?.current ? t("wa_current_tariff", { tariff: changeOptions.current.title }) : "";
  }

  function trialTrafficLabel() {
    const limit = Number(appSettings?.trial_traffic_limit_gb || 0);
    return limit > 0 ? formatTrafficGb(limit) : t("wa_unlimited_traffic");
  }

  function devicesLimitLabel(value = devicesData?.max_devices) {
    const numeric = Number(value ?? 0);
    if (!Number.isFinite(numeric) || numeric <= 0) return t("wa_devices_unlimited");
    return String(Math.trunc(numeric));
  }

  function devicesCountLabel() {
    const current = Number(devicesData?.current_devices ?? devicesData?.devices?.length ?? 0);
    return t("wa_devices_count", { current, max: devicesLimitLabel() });
  }

  function devicesPercent() {
    const current = Number(devicesData?.current_devices ?? devicesData?.devices?.length ?? 0);
    const max = Number(devicesData?.max_devices || 0);
    if (!max || max <= 0) return 100;
    return Math.max(0, Math.min(100, Math.round((current / max) * 100)));
  }

</script>

<svelte:head>
  <title>{brandTitle}</title>
</svelte:head>

<Tooltip.Provider>
  {#key currentLang}
    {#if isPreviewBoard}
      <PreviewBoard config={CFG} mockData={DEV_MOCK.data} />
    {:else}
      <div class="app-shell" style={`--accent: ${accent};`}>
      {#if mode === "loading"}
        <div class="loader">
          <BrandMark class="brand-mark-lg" logoUrl={CFG.logoUrl} emoji={brandEmoji} />
          <div>{t("wa_loading")}</div>
        </div>
      {:else if mode === "login"}
        <AuthScreen
          {screen}
          {CFG}
          {brandTitle}
          {brandEmoji}
          bind:email
          bind:emailCode
          {pendingEmail}
          {authStatus}
          {authIsError}
          {authBusy}
          {authResendCooldown}
          {loginEmailFieldError}
          {loginEmailTooltipOpen}
          {telegramLoginBusy}
          {telegramLoginUnavailable}
          {telegramLoginChecking}
          {telegramLoginLabel}
          {telegramLoginUnavailableMessage}
          {privacyPolicyUrl}
          {userAgreementUrl}
          {t}
          {requestEmailCode}
          {verifyEmailCode}
          {openTelegramLogin}
          {openExternalLink}
          {submitEmailOnEnter}
          onBackToLogin={() => (screen = "login")}
          clearLoginEmailError={() => {
            loginEmailFieldError = "";
            loginEmailTooltipOpen = false;
          }}
        />
    {:else if screen === "admin" && isAdmin}
      <AdminPanel
        api={api}
        onClose={closeAdminPanel}
        onToast={(text) => showToast(text)}
        initialSection={adminSectionFromPath(window.location.pathname)}
        initialUserId={adminUserIdFromPath(window.location.pathname)}
        onSectionChange={handleAdminSectionChange}
        onSettingsSaved={handleSettingsSaved}
        onTariffsSaved={handleTariffsSaved}
        brandTitle={brandTitle}
        logoUrl={CFG.logoUrl}
        logoEmoji={brandEmoji}
        appVersion={CFG.appVersion}
        appRepositoryUrl={CFG.appRepositoryUrl}
        currentLang={currentLang}
        languageOptions={languageOptions}
        languageBusy={languageBusy}
        onLanguageChange={updateAccountLanguage}
        t={t}
      />
    {:else}
      <WebAppShell
        {screen}
        {activeTab}
        {CFG}
        {brandTitle}
        {brandEmoji}
        {devicesEnabled}
        {hasUnlinkedIdentity}
        {isAdmin}
        {openAdminPanel}
        {goDevices}
        {goHome}
        {goInvite}
        {goSettings}
        {t}
      >
        {#if screen === "home"}
          <HomeScreen
            {CFG}
            {appSettings}
            {brandEmoji}
            {brandTitle}
            {canChangeTariff}
            {canOpenPremiumTopupModal}
            {canOpenRegularTopupModal}
            {canShowTopupButton}
            {currentTariffName}
            {hasActiveTariffSubscription}
            {hasMultipleTariffs}
            {subscription}
            {trafficMode}
            {trialBusy}
            {activeSubscriptionTermLabel}
            {activateTrial}
            {openConnectLink}
            {openPaymentModal}
            {openTariffChangeModal}
            {openTopupModal}
            {premiumServerLabels}
            {premiumTitle}
            {premiumTrafficLabel}
            {premiumTrafficPercent}
            {primaryPayActionLabel}
            {t}
            {trafficLabel}
            {trafficPercent}
            {trafficResetLabel}
            {trialTrafficLabel}
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
            {devicesCountLabel}
            {devicesLimitLabel}
            {devicesPercent}
            {loadDevices}
            {openDeviceDisconnectDialog}
            {openDeviceTopupModal}
            {t}
          />
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
            {linkTelegramAccount}
            {logout}
            {openAdminPanel}
            {openExternalLink}
            {openLinkEmailDialog}
            {setLanguageMenuOpen}
            {t}
            {updateAccountLanguage}
          />
        {/if}
      </WebAppShell>

      <PaymentDialogs
        bind:linkEmailCode
        bind:linkEmailFieldError
        bind:linkEmailValue
        bind:paymentModalOpen
        bind:paymentStep
        bind:selectedMethod
        bind:selectedPlan
        bind:selectedTariffKey
        {createPayment}
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
        {methods}
        {payBusy}
        {plans}
        {selectedTariff}
        {selectedTariffPlans}
        {singleTariffMode}
        {subscription}
        {tariffCatalog}
        {tariffMode}
        {closeDeviceDisconnectDialog}
        {closeLinkEmailDialog}
        {closePaymentModal}
        {continueWithSelectedTariff}
        {methodMeta}
        {paymentDescription}
        {paymentTitle}
        {planKey}
        {planSubtitle}
        {planUnitHint}
        {priceLabel}
        {requestLinkEmailCode}
        {selectTariff}
        {t}
        {verifyLinkEmailCode}
      />

      <TariffDialogs
        bind:changeConfirmOpen
        bind:changeModalOpen
        bind:deviceTopupModalOpen
        bind:selectedChangeAction
        bind:selectedChangeTarget
        bind:selectedDeviceTopupPlan
        bind:selectedMethod
        bind:selectedTopupPlan
        bind:topupModalOpen
        {actionKey}
        {applyTariffChange}
        {changeActionTitle}
        {changeOptions}
        {closeDeviceTopupModal}
        {closeTariffChangeConfirm}
        {closeTariffChangeModal}
        {closeTopupModal}
        {createDeviceTopupPayment}
        {createTopupPayment}
        {deviceTopupModalDescription}
        {deviceTopupOptions}
        {methods}
        {methodMeta}
        {openTariffChangeConfirm}
        {payBusy}
        {planKey}
        {planUnitHint}
        {priceLabel}
        {singleTariffMode}
        {tariffActionBusy}
        {tariffChangeModalDescription}
        {tariffChangeSummary}
        {topupCarryoverNotes}
        {topupModalDescription}
        {topupModalTitle}
        {topupOptions}
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
