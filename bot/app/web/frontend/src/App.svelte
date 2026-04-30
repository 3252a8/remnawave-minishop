<script>
  import {
    ArrowLeft,
    ArrowRight,
    Check,
    CheckCircle2,
    ChevronsUpDown,
    Bitcoin,
    CircleX,
    Copy,
    CreditCard,
    Database,
    FileText,
    Gift,
    Globe2,
    Home,
    LockKeyhole,
    Mail,
    RefreshCw,
    Send,
    Smartphone,
    TriangleAlert,
    Settings as SettingsIcon,
    Shield,
    Ticket,
    UserRound,
  } from "lucide-svelte";
  import { onMount } from "svelte";
  import { Select, Tooltip } from "bits-ui";

  import Button from "./lib/components/ui/button.svelte";
  import Card from "./lib/components/ui/card.svelte";
  import Dialog from "./lib/components/ui/dialog.svelte";
  import Input from "./lib/components/ui/input.svelte";
  import PreviewBoard from "./PreviewBoard.svelte";

  const MANUAL_LOGOUT_FLAG_KEY = "rw_webapp_manual_logout";
  const LANGUAGE_LABELS = {
    ru: "Русский",
    en: "English",
    de: "Deutsch",
    es: "Español",
    fr: "Français",
    tr: "Türkçe",
    uk: "Українська",
  };
  const LANGUAGE_FLAGS = {
    ru: "🇷🇺",
    en: "🇬🇧",
    de: "🇩🇪",
    es: "🇪🇸",
    fr: "🇫🇷",
    tr: "🇹🇷",
    uk: "🇺🇦",
  };
  const WEBAPP_LANGUAGE_ORDER = ["ru", "en"];
  const APP_SECTION_PATHS = {
    home: "/home",
    invite: "/invite",
    devices: "/devices",
    settings: "/settings",
  };

  const DEV_MOCK = {
    config: {
      title: "/minishop",
      primaryColor: "#00fe7a",
      logoUrl: "",
      logoEmoji: "🫥",
      apiBase: "/api",
      supportUrl: "https://t.me/support",
      privacyPolicyUrl: "https://example.com/privacy",
      userAgreementUrl: "https://example.com/agreement",
      currency: "RUB",
      language: "ru",
      emailAuthEnabled: true,
      telegramLoginBotUsername: "preview_bot",
      telegramLoginBotId: 1234567890,
      telegramOAuthClientId: 1234567890,
      telegramOAuthRequestAccess: ["write"],
    },
    data: {
      ok: true,
      user: {
        id: 100200300,
        username: "username",
        email: "user@example.com",
        email_verified: true,
        telegram_id: 100200300,
        telegram_linked: true,
        telegram_photo_url: "",
        first_name: "Preview",
        language_code: "ru",
      },
      subscription: {
        active: true,
        status: "ACTIVE",
        remaining_text: "25 д. 8 ч.",
        end_date_text: "24.05.2026",
        days_left: 25,
        config_link: "https://sub.example.com/sub/preview-token",
        connect_url: "https://sub.example.com/connect/preview-token",
        traffic_used: "18.4 GB",
        traffic_limit: "100 GB",
        traffic_used_bytes: 19756849561,
        traffic_limit_bytes: 107374182400,
        max_devices: 5,
      },
      devices: {
        ok: true,
        enabled: true,
        current_devices: 3,
        max_devices: 5,
        max_devices_label: "5",
        devices: [
          {
            index: 1,
            display_name: "iPhone 15 Pro",
            platform_label: "iOS 18.4",
            user_agent: "Streisand/1.6 CFNetwork",
            created_at_text: "28.04.2026 16:12",
            hwid_short: "A1B2C3D4...98FA01",
            token: "preview-device-1",
            can_disconnect: true,
          },
          {
            index: 2,
            display_name: "MacBook Air",
            platform_label: "macOS 15.4",
            user_agent: "Happ/3.1.0",
            created_at_text: "29.04.2026 09:40",
            hwid_short: "F0E1D2C3...44AB22",
            token: "preview-device-2",
            can_disconnect: true,
          },
          {
            index: 3,
            display_name: "Android Phone",
            platform_label: "Android 15",
            user_agent: "v2rayNG/1.9.35",
            created_at_text: "30.04.2026 07:55",
            hwid_short: "778899AA...BCDD10",
            token: "preview-device-3",
            can_disconnect: true,
          },
        ],
      },
      plans: [
        { months: 1, price: 290, currency: "RUB", title: "1 месяц" },
        { months: 3, price: 790, currency: "RUB", title: "3 месяца" },
        { months: 6, price: 1490, currency: "RUB", title: "6 месяцев" },
        { months: 12, price: 2690, currency: "RUB", title: "12 месяцев" },
      ],
      payment_methods: [
        { id: "yookassa", name: "Карта" },
        { id: "platega_sbp", name: "Telegram Pay" },
        { id: "cryptopay", name: "Криптовалюта" },
        { id: "freekassa", name: "Другие способы" },
      ],
      referral: {
        code: "ABCD1234",
        bot_link: "https://t.me/preview_bot?start=ref_uABCD1234",
        webapp_link: "https://minishop.app/ref/ABCD1234",
        invited_count: 4,
        purchased_count: 2,
        welcome_bonus_days: 3,
        one_bonus_per_referee: false,
        bonus_details: [
          { months: 1, title: "1 месяц", inviter_days: 14, friend_days: 7 },
          { months: 3, title: "3 месяца", inviter_days: 21, friend_days: 14 },
          { months: 6, title: "6 месяцев", inviter_days: 31, friend_days: 21 },
          { months: 12, title: "12 месяцев", inviter_days: 62, friend_days: 31 },
        ],
      },
      settings: {
        support_url: "https://t.me/support",
        traffic_mode: false,
        my_devices_enabled: false,
        user_hwid_device_limit: 5,
        trial_enabled: true,
        trial_available: true,
        trial_duration_days: 5,
        trial_traffic_limit_gb: 10,
        trial_traffic_strategy: "NO_RESET",
        email_auth_enabled: true,
      },
    },
  };

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
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  let mode = isPreviewBoard ? "preview" : "loading";
  let activeTab = "home";
  let screen = "home";
  let data = isPreviewBoard ? structuredCloneSafe(DEV_MOCK.data) : null;
  let selectedPlan = null;
  let selectedMethod = "";
  let paymentModalOpen = false;
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
  let loginEmailFieldError = "";
  let loginEmailTooltipOpen = false;
  let authResendCooldown = 0;
  let authResendTimer = null;
  let languageBusy = false;
  let languageMenuOpen = false;
  let languageClickGuard = false;
  let languageClickGuardTimer = null;
  let email = "";
  let pendingEmail = "";
  let emailCode = "";
  let emailAvatarUrl = "";
  let avatarHashToken = "";
  let token = MOCK ? "local-preview" : localStorage.getItem("rw_webapp_token") || "";
  let csrfToken = MOCK ? "" : readCookie("rw_webapp_csrf") || "";
  let linkEmailResendCooldown = 0;
  let linkEmailResendTimer = null;
  let scrollLockApplied = false;

  function applyPreviewMock(kind) {
    const mode = String(kind || "").trim().toLowerCase();
    if (mode === "traffic") {
      DEV_MOCK.data.settings.traffic_mode = true;
      DEV_MOCK.data.settings.trial_available = false;
      DEV_MOCK.data.subscription = {
        ...DEV_MOCK.data.subscription,
        active: true,
        status: "ACTIVE",
        remaining_text: "Навсегда",
        end_date_text: "01.01.2099 00:00",
        days_left: 26000,
        traffic_used: "18.4 GB",
        traffic_limit: "100 GB",
        traffic_used_bytes: 19756849561,
        traffic_limit_bytes: 107374182400,
        traffic_limit_strategy: "NO_RESET",
      };
      DEV_MOCK.data.plans = [
        { months: 10, traffic_gb: 10, price: 199, currency: "RUB", title: "10 GB", sale_mode: "traffic" },
        { months: 50, traffic_gb: 50, price: 799, currency: "RUB", title: "50 GB", sale_mode: "traffic" },
        { months: 100, traffic_gb: 100, price: 1390, currency: "RUB", title: "100 GB", sale_mode: "traffic" },
        { months: 300, traffic_gb: 300, price: 3490, currency: "RUB", title: "300 GB", sale_mode: "traffic" },
      ];
    } else if (mode === "devices") {
      DEV_MOCK.data.settings.my_devices_enabled = true;
      DEV_MOCK.data.subscription = {
        ...DEV_MOCK.data.subscription,
        active: true,
        max_devices: 5,
      };
    } else if (mode === "trial") {
      DEV_MOCK.data.settings.traffic_mode = false;
      DEV_MOCK.data.settings.trial_enabled = true;
      DEV_MOCK.data.settings.trial_available = true;
      DEV_MOCK.data.settings.trial_duration_days = 5;
      DEV_MOCK.data.settings.trial_traffic_limit_gb = 10;
      DEV_MOCK.data.subscription = {
        active: false,
        status: "INACTIVE",
        remaining_text: "Подписка не активна",
        end_date_text: "",
        days_left: 0,
        config_link: null,
        connect_url: null,
        traffic_used: "0 B",
        traffic_limit: "10 GB",
        traffic_used_bytes: 0,
        traffic_limit_bytes: 10737418240,
      };
    }
  }

  $: brandTitle = CFG.title || "/minishop";
  $: brandEmoji = CFG.logoEmoji || "🫥";
  $: accent = CFG.primaryColor || "#00fe7a";
  $: plans = data?.plans?.length ? data.plans : DEV_MOCK.data.plans;
  $: methods = data?.payment_methods?.length ? data.payment_methods : [];
  $: appSettings = data?.settings || DEV_MOCK.data.settings;
  $: trafficMode = Boolean(appSettings?.traffic_mode);
  $: devicesEnabled = Boolean(appSettings?.my_devices_enabled);
  $: subscription = data?.subscription || DEV_MOCK.data.subscription;
  $: user = data?.user || {};
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
  $: applyFavicon(CFG.logoUrl, brandEmoji);
  $: syncBodyScrollLock(paymentModalOpen || linkEmailOpen);
  $: if (!selectedPlan && plans.length) selectedPlan = plans[Math.min(1, plans.length - 1)];
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
      clearCooldownTimer("auth");
      clearCooldownTimer("link_email");
      clearLanguageClickGuard();
      syncBodyScrollLock(false);
    };
  });

  function readJsonScript(id) {
    const node = document.getElementById(id);
    if (!node || !node.textContent) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      console.warn(`Failed to parse JSON config from #${id}`, error);
      return null;
    }
  }

  function structuredCloneSafe(value) {
    try {
      return structuredClone(value);
    } catch {
      return JSON.parse(JSON.stringify(value));
    }
  }

  function applyFavicon(logoUrl, emoji) {
    if (typeof document === "undefined") return;
    const favicon = document.getElementById("app-favicon");
    if (!favicon) return;

    const normalizedLogoUrl = String(logoUrl || "").trim();
    if (normalizedLogoUrl) {
      favicon.setAttribute("href", normalizedLogoUrl);
      return;
    }

    const normalizedEmoji = String(emoji || "🫥").trim() || "🫥";
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-size="52">${escapeHtml(
      normalizedEmoji,
    )}</text></svg>`;
    const encoded = encodeURIComponent(svg);
    favicon.setAttribute("href", `data:image/svg+xml,${encoded}`);
  }

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
  }

  function setLanguageMenuOpen(open) {
    languageMenuOpen = Boolean(open);
    clearLanguageClickGuard();
    if (languageMenuOpen) {
      languageClickGuard = true;
      return;
    }
    languageClickGuardTimer = window.setTimeout(() => {
      languageClickGuard = false;
      languageClickGuardTimer = null;
    }, 260);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function normalizeLangCode(lang) {
    const key = String(lang || "").trim().toLowerCase();
    if (!key) return "ru";
    const base = key.split("-")[0];
    if (LANGUAGE_LABELS[base]) return base;
    if (I18N[base]) return base;
    if (I18N[key]) return key;
    return "ru";
  }

  function formatTemplate(template, params = {}) {
    const text = String(template ?? "");
    return text.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? `{${key}}`));
  }

  function t(key, params = {}, fallback = "") {
    const lang = normalizeLangCode(user?.language_code || CFG.language || "ru");
    const variants = [
      I18N?.[lang]?.[key],
      I18N?.en?.[key],
      I18N?.ru?.[key],
      fallback,
      key,
    ];
    const raw = variants.find((value) => typeof value === "string" && value.length);
    return formatTemplate(raw, params);
  }

  function normalizeSection(value) {
    const section = String(value || "").trim().toLowerCase();
    return section === "invite" || section === "devices" || section === "settings" ? section : "home";
  }

  function sectionFromPath(pathname) {
    const normalizedPath = String(pathname || "")
      .trim()
      .toLowerCase()
      .replace(/\/+$/, "");
    if (!normalizedPath || normalizedPath === "/") return "home";
    const section = normalizedPath.startsWith("/") ? normalizedPath.slice(1) : normalizedPath;
    return normalizeSection(section);
  }

  function syncSectionPath(section, replace = false) {
    if (window.location.protocol === "file:") return;
    const normalized = normalizeSection(section);
    const targetPath = APP_SECTION_PATHS[normalized] || APP_SECTION_PATHS.home;
    if (window.location.pathname === targetPath) return;
    const nextUrl = `${targetPath}${window.location.search}${window.location.hash}`;
    window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
  }

  async function boot() {
    mode = "loading";
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

    if (tg?.initData) {
      try {
        if (await finalizeTelegramAuth(tg.initData, "init_data")) return;
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
    selectedPlan = payload.plans?.[Math.min(1, payload.plans.length - 1)] || payload.plans?.[0] || null;
    selectedMethod = payload.payment_methods?.[0]?.id || "";
    let section = MOCK && query.get("screen") ? normalizeSection(query.get("screen")) : sectionFromPath(window.location.pathname);
    if (section === "devices" && !payload.settings?.my_devices_enabled) section = "home";
    activeTab = section;
    screen = section;
    mode = "app";
    syncSectionPath(section, true);
    if (section === "devices" && payload.settings?.my_devices_enabled) {
      await loadDevices();
    }
  }

  function showLogin() {
    mode = "login";
    screen = "login";
    activeTab = "home";
  }

  async function api(path, options = {}) {
    if (MOCK) return mockApi(path, options);
    const method = String(options.method || "GET").toUpperCase();
    const headers = { ...(options.headers || {}) };
    if (token) headers.Authorization = `Bearer ${token}`;
    const csrf = csrfToken || readCookie("rw_webapp_csrf") || "";
    if (csrf && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      headers["X-CSRF-Token"] = csrf;
    }
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const response = await fetch(`${CFG.apiBase}${path}`, { ...options, headers });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      clearToken();
      showLogin();
    }
    return payload;
  }

  async function publicApi(path, payload = {}) {
    if (MOCK) {
      return mockApi(path, { method: "POST", body: JSON.stringify(payload) });
    }
    const response = await fetch(`${CFG.apiBase}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.json();
  }

  async function mockApi(path, options = {}) {
    await new Promise((resolve) => window.setTimeout(resolve, 120));
    if (path === "/me") return structuredCloneSafe(DEV_MOCK.data);
    if (path === "/auth/email/request") return { ok: true };
    if (path === "/auth/email/verify" || path === "/auth/email/magic") {
      return { ok: true, token: "local-preview", csrf_token: "local-preview-csrf" };
    }
    if (path === "/auth/token") {
      return { ok: true, token: "local-preview", csrf_token: "local-preview-csrf" };
    }
    if (path === "/promo/apply") return { ok: true, end_date_text: "31.05.2026" };
    if (path === "/devices") return structuredCloneSafe(DEV_MOCK.data.devices);
    if (path === "/devices/disconnect" && String(options.method || "").toUpperCase() === "POST") {
      let payload = {};
      try {
        payload = options?.body ? JSON.parse(String(options.body)) : {};
      } catch {}
      DEV_MOCK.data.devices.devices = DEV_MOCK.data.devices.devices.filter((device) => device.token !== payload.token);
      DEV_MOCK.data.devices.current_devices = DEV_MOCK.data.devices.devices.length;
      return { ok: true };
    }
    if (path === "/trial/activate" && String(options.method || "").toUpperCase() === "POST") {
      DEV_MOCK.data.subscription = {
        ...DEV_MOCK.data.subscription,
        active: true,
        status: "TRIAL",
        remaining_text: "5 д. 0 ч.",
        end_date_text: "05.05.2026 12:00",
        days_left: 5,
        traffic_limit: "10 GB",
        traffic_limit_bytes: 10737418240,
        traffic_used: "0 B",
        traffic_used_bytes: 0,
      };
      DEV_MOCK.data.settings.trial_available = false;
      return { ok: true, activated: true, end_date_text: "05.05.2026 12:00" };
    }
    if (path === "/auth/logout") return { ok: true };
    if (path === "/account/language" && String(options.method || "").toUpperCase() === "POST") {
      let payload = {};
      try {
        payload = options?.body ? JSON.parse(String(options.body)) : {};
      } catch {}
      const language = normalizeLangCode(payload?.language || currentLang);
      DEV_MOCK.data.user.language_code = language;
      return { ok: true, language };
    }
    if (path === "/account/email/request" && String(options.method || "").toUpperCase() === "POST") {
      return { ok: true };
    }
    if (path === "/account/email/verify" && String(options.method || "").toUpperCase() === "POST") {
      return { ok: true, token: "local-preview", csrf_token: "local-preview-csrf" };
    }
    if (path === "/account/telegram/link" && String(options.method || "").toUpperCase() === "POST") {
      return { ok: true, token: "local-preview", csrf_token: "local-preview-csrf" };
    }
    if (path === "/payments" && String(options.method || "").toUpperCase() === "POST") {
      return {
        ok: true,
        action: "open_link",
        payment_url: "https://example.com/payment-preview",
        payment_id: 10001,
      };
    }
    return { ok: false, error: "not_found" };
  }

  function readCookie(name) {
    const prefix = `${name}=`;
    const cookie = document.cookie.split("; ").find((part) => part.startsWith(prefix));
    return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
  }

  function setToken(nextToken, nextCsrf = "") {
    clearManualLogoutFlag();
    token = nextToken || "";
    csrfToken = nextCsrf || readCookie("rw_webapp_csrf") || "";
    if (token && !MOCK) localStorage.setItem("rw_webapp_token", token);
  }

  function clearToken() {
    token = "";
    csrfToken = "";
    localStorage.removeItem("rw_webapp_token");
  }

  function markManualLogout() {
    try {
      localStorage.setItem(MANUAL_LOGOUT_FLAG_KEY, "1");
    } catch {}
  }

  function clearManualLogoutFlag() {
    try {
      localStorage.removeItem(MANUAL_LOGOUT_FLAG_KEY);
    } catch {}
  }

  function isManuallyLoggedOut() {
    try {
      return localStorage.getItem(MANUAL_LOGOUT_FLAG_KEY) === "1";
    } catch {
      return false;
    }
  }

  function readReferralParam() {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get("ref") || params.get("start") || params.get("start_param") || "";
    const fromTelegram = tg?.initDataUnsafe?.start_param || "";
    const value = String(fromTelegram || fromQuery || "").trim();
    if (value) {
      localStorage.setItem("rw_webapp_referral", value);
      return value;
    }
    return localStorage.getItem("rw_webapp_referral") || "";
  }

  function readTelegramAuthStatus() {
    const params = new URLSearchParams(window.location.search);
    return (params.get("telegram_auth") || "").trim().toLowerCase() || null;
  }

  function readMagicLoginToken() {
    const params = new URLSearchParams(window.location.search);
    return (params.get("login_token") || "").trim() || null;
  }

  function readTelegramLoginWidgetAuthData() {
    const params = new URLSearchParams(window.location.search);
    const keys = ["id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash"];
    const authData = {};
    let hasAuthValue = false;
    keys.forEach((key) => {
      if (!params.has(key)) return;
      authData[key] = params.get(key) || "";
      hasAuthValue = true;
    });
    if (!hasAuthValue || !authData.id || !authData.auth_date || !authData.hash) return null;
    return authData;
  }

  function clearAuthQuery() {
    const url = new URL(window.location.href);
    [
      "login_token",
      "login_purpose",
      "telegram_auth",
      "id",
      "first_name",
      "last_name",
      "username",
      "photo_url",
      "auth_date",
      "hash",
    ].forEach((key) =>
      url.searchParams.delete(key),
    );
    window.history?.replaceState?.({}, document.title, url.pathname + url.search + url.hash);
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

  async function finalizeTelegramAuth(authData, source = "auth_data") {
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
      const response = await publicApi("/auth/token", payload);
      if (response.ok && response.token) {
        setToken(response.token, response.csrf_token);
        clearAuthQuery();
        setAuthStatus("");
        await loadData();
        return true;
      }
      setAuthStatus(response.error === "banned" ? t("wa_auth_access_denied") : t("wa_auth_telegram_not_confirmed"), true);
    } catch {
      setAuthStatus(t("wa_auth_telegram_unavailable"), true);
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

  function emailError(error, fallback) {
    if (error?.error === "rate_limited") return t("wa_auth_resend_wait", { seconds: error.retry_after || 60 });
    if (error?.error === "invalid_email") return t("wa_auth_invalid_email");
    if (error?.error === "expired_code") return t("wa_auth_code_expired");
    if (error?.error === "invalid_code" || error?.error === "too_many_attempts") return t("wa_auth_invalid_code");
    return fallback;
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

  function buildTelegramOAuthStartUrl(purpose = "login") {
    const url = new URL("/auth/telegram/start", window.location.origin);
    url.searchParams.set("purpose", purpose);
    const referralParam = readReferralParam();
    if (referralParam) url.searchParams.set("referral_code", referralParam);
    return url.toString();
  }

  async function openTelegramLogin() {
    if (authBusy) return;
    if (tg?.initData) {
      await finalizeTelegramAuth(tg.initData, "init_data");
      return;
    }

    if (!telegramOAuthClientId) {
      setAuthStatus(t("wa_auth_telegram_not_configured"), true);
      return;
    }

    authBusy = true;
    setAuthStatus(t("wa_auth_checking_telegram"));
    window.location.assign(buildTelegramOAuthStartUrl("login"));
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
    if (tg?.initData) {
      await linkTelegramAccountWithPayload({ init_data: tg.initData });
      return;
    }
    if (!telegramOAuthClientId) {
      showToast(t("wa_auth_telegram_not_configured"));
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
        selectedPlan = payload.plans?.[Math.min(1, payload.plans.length - 1)] || payload.plans?.[0] || null;
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
      const response = await api("/payments", {
        method: "POST",
        body: JSON.stringify({
          months: selectedPlan.months,
          traffic_gb: selectedPlan.traffic_gb,
          method: selectedMethod,
        }),
      });
      if (!response.ok || !response.payment_url) throw response;
      showToast(t("wa_payment_created"));
      openExternalLink(response.payment_url);
      paymentModalOpen = false;
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

  function goSettings() {
    paymentModalOpen = false;
    activeTab = "settings";
    screen = "settings";
    syncSectionPath("settings");
  }

  function openPaymentModal() {
    paymentModalOpen = true;
  }

  function closePaymentModal() {
    paymentModalOpen = false;
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

  function formatMoney(value, currency = CFG.currency || "RUB") {
    const numeric = Number(value || 0);
    const formatted = Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
    const symbol = currency === "RUB" ? "₽" : currency;
    return `${formatted} ${symbol}`;
  }

  function priceLabel(plan, methodId = selectedMethod) {
    if (String(methodId || "").toLowerCase().includes("stars") && Number(plan?.stars_price || 0) > 0) {
      return `${Number(plan.stars_price)} ⭐`;
    }
    return formatMoney(plan?.price || 0, plan?.currency);
  }

  function formatTrafficGb(value) {
    const numeric = Number(value || 0);
    const formatted = Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    return `${formatted} GB`;
  }

  function trafficPercent(sub) {
    const used = Number(sub?.traffic_used_bytes || 0);
    const limit = Number(sub?.traffic_limit_bytes || 0);
    if (!limit || limit <= 0) return 100;
    return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
  }

  function trafficLabel(sub) {
    if (!sub?.traffic_limit_bytes || Number(sub.traffic_limit_bytes) <= 0) return t("wa_unlimited_traffic");
    return t("wa_traffic_of", { used: sub.traffic_used || "0 GB", limit: sub.traffic_limit || "0 GB" });
  }

  function trafficResetLabel(sub) {
    const strategy = String(sub?.traffic_limit_strategy || "").trim().toUpperCase();
    if (!strategy || strategy.includes("NO_RESET")) {
      return t("wa_traffic_reset_none");
    }
    if (strategy.includes("MONTH")) {
      return t("wa_traffic_reset_monthly");
    }
    if (strategy.includes("WEEK")) {
      return t("wa_traffic_reset_weekly");
    }
    if (strategy.includes("DAY")) {
      return t("wa_traffic_reset_daily");
    }
    if (strategy.includes("YEAR")) {
      return t("wa_traffic_reset_yearly");
    }
    return t("wa_traffic_reset_policy");
  }

  function planDisplayTitle(plan) {
    if (trafficMode || plan?.sale_mode === "traffic") {
      return plan?.title || formatTrafficGb(plan?.traffic_gb || plan?.months);
    }
    const months = Number(plan?.months || 0);
    if (months === 12) {
      return t("wa_plan_one_year");
    }
    return plan?.title || "";
  }

  function planUnitHint(plan) {
    if (trafficMode || plan?.sale_mode === "traffic") {
      const gb = Number(plan?.traffic_gb || plan?.months || 0);
      if (!gb) return "";
      if (String(selectedMethod || "").toLowerCase().includes("stars") && Number(plan?.stars_price || 0) > 0) {
        return `${Number(plan.stars_price / gb).toFixed(0)} ⭐${t("wa_per_gb_short")}`;
      }
      return `${formatMoney(Number(plan?.price || 0) / gb, plan?.currency)}${t("wa_per_gb_short")}`;
    }
    const months = Number(plan?.months || 0);
    if (!months || months <= 1) return "";
    if (String(selectedMethod || "").toLowerCase().includes("stars") && Number(plan?.stars_price || 0) > 0) {
      return `${Number(plan.stars_price / months).toFixed(0)} ⭐${t("wa_per_month_short")}`;
    }
    return `${formatMoney(Number(plan?.price || 0) / months, plan?.currency)}${t("wa_per_month_short")}`;
  }

  function paymentTitle() {
    return trafficMode ? t("wa_traffic_packages_title") : t("wa_subscription_title");
  }

  function paymentDescription() {
    return trafficMode ? t("wa_traffic_packages_choose") : t("wa_subscription_choose_period");
  }

  function primaryPayActionLabel() {
    if (trafficMode) return t("wa_buy_traffic");
    return subscription.active ? t("wa_renew") : t("wa_pay_subscription");
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

  function activeSubscriptionTermLabel(sub) {
    const forever = isForeverSubscription(sub);
    if (forever) return t("wa_sub_term_forever");

    const days = Math.max(0, Number(sub?.days_left || 0));
    if (!days) return t("wa_sub_term_value_unit", { value: "0", unit: termUnitLabel(0, "day") });

    if (days < 30) {
      return t("wa_sub_term_value_unit", { value: String(days), unit: termUnitLabel(days, "day") });
    }

    if (days < 365) {
      const months = roundToHalf(days / 30);
      return t("wa_sub_term_value_unit", {
        value: formatFraction(months),
        unit: termUnitLabel(months, "month"),
      });
    }

    const years = roundToHalf(days / 365);
    return t("wa_sub_term_value_unit", {
      value: formatFraction(years),
      unit: termUnitLabel(years, "year"),
    });
  }

  function isForeverSubscription(sub) {
    const raw = String(sub?.end_date_text || "").trim();
    if (!raw) return false;
    const year = extractYear(raw);
    return year >= 2099;
  }

  function extractYear(text) {
    const iso = text.match(/\b(\d{4})-\d{1,2}-\d{1,2}\b/);
    if (iso) return Number(iso[1] || 0);
    const dmy = text.match(/\b\d{1,2}\.\d{1,2}\.(\d{4})\b/);
    if (dmy) return Number(dmy[1] || 0);
    const any4 = text.match(/\b(\d{4})\b/);
    if (any4) return Number(any4[1] || 0);
    return 0;
  }

  function roundToHalf(value) {
    return Math.round(Number(value || 0) * 2) / 2;
  }

  function formatFraction(value) {
    const n = Number(value || 0);
    if (Number.isInteger(n)) return String(n);
    return n.toFixed(1);
  }

  function ruPlural(value, one, few, many) {
    const n = Math.abs(Number(value || 0));
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
  }

  function ruFractionAware(value, one, few, many) {
    const n = Number(value || 0);
    if (!Number.isInteger(n)) return few;
    return ruPlural(n, one, few, many);
  }

  function unitPluralBucket(value) {
    if (currentLang === "ru") {
      const n = Number(value || 0);
      if (!Number.isInteger(n)) {
        const base = Math.floor(Math.abs(n));
        const mod10 = base % 10;
        const mod100 = base % 100;
        return mod10 >= 1 && mod10 <= 4 && (mod100 < 11 || mod100 > 14) ? "few" : "many";
      }
      const abs = Math.abs(n);
      const mod10 = abs % 10;
      const mod100 = abs % 100;
      if (mod10 === 1 && mod100 !== 11) return "one";
      if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "few";
      return "many";
    }
    return Number(value) === 1 ? "one" : "many";
  }

  function termUnitLabel(value, unit) {
    const bucket = unitPluralBucket(value);
    return t(`wa_sub_term_${unit}_${bucket}`);
  }

  function normalizedEmail(value) {
    return String(value || "").trim().toLowerCase();
  }

  function languageName(code) {
    const key = String(code || "").trim().toLowerCase();
    if (!key) return t("wa_language_default");
    return LANGUAGE_LABELS[key] || key.toUpperCase();
  }

  function telegramName(profile) {
    const first = String(profile?.first_name || "").trim();
    const last = String(profile?.last_name || "").trim();
    if (first || last) return `${first} ${last}`.trim();
    const username = String(profile?.username || "").trim();
    if (username) return `@${username}`;
    return t("wa_telegram_not_linked");
  }

  function bytesToHex(buffer) {
    return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function sha256Hex(value) {
    const data = new TextEncoder().encode(value);
    const hashBuffer = await window.crypto.subtle.digest("SHA-256", data);
    return bytesToHex(hashBuffer);
  }

  async function buildGravatarUrl(emailValue) {
    if (!emailValue || !window.crypto?.subtle) return "";
    try {
      const hash = await sha256Hex(emailValue);
      return `https://www.gravatar.com/avatar/${hash}?d=mp&s=160`;
    } catch {
      return "";
    }
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
          <div class="brand-mark brand-mark-lg">
            {#if CFG.logoUrl}
              <img src={CFG.logoUrl} alt="" />
            {:else}
              <span>{brandEmoji}</span>
            {/if}
          </div>
          <div>{t("wa_loading")}</div>
        </div>
      {:else if mode === "login"}
      <div class="phone-screen auth-screen">
        {#if screen === "code"}
          <header class="screen-head center-title">
            <Button variant="icon" size="icon" onclick={() => (screen = "login")} aria-label={t("wa_back")}>
              <ArrowLeft size={19} />
            </Button>
            <div>
              <h1>{t("wa_email_verification_title")}</h1>
              <p>{t("wa_email_sent_to", { email: pendingEmail })}</p>
            </div>
            <span></span>
          </header>
          <div class="otp-wrap">
            <label class="otp-input-wrap">
              <input
                bind:value={emailCode}
                inputmode="numeric"
                autocomplete="one-time-code"
                maxlength="6"
                aria-label={t("wa_email_code_aria")}
              />
              <span class="otp-slots" aria-hidden="true">
                {#each Array.from({ length: 6 }) as _, index}
                  <span class:filled={emailCode[index]}>{emailCode[index] || ""}</span>
                {/each}
              </span>
            </label>
            <Button class="wide" onclick={verifyEmailCode} disabled={authBusy}>
              {t("wa_confirm")}
            </Button>
            {#if authStatus}
              <div class:error={authIsError} class="status-line">{authStatus}</div>
            {/if}
            <button
              class="link-button"
              type="button"
              on:click={requestEmailCode}
              disabled={authBusy || authResendCooldown > 0}
            >
              <RefreshCw size={15} />
              {authResendCooldown > 0 ? t("wa_auth_resend_wait", { seconds: authResendCooldown }) : t("wa_resend_code")}
            </button>
          </div>
        {:else}
          <div class="auth-card-wrap">
            <div class="login-brand login-brand-auth">
              <div class="brand-mark brand-mark-xl">
                {#if CFG.logoUrl}
                  <img src={CFG.logoUrl} alt="" />
                {:else}
                  <span>{brandEmoji}</span>
                {/if}
              </div>
              <h1>{brandTitle}</h1>
            </div>
            <Card class="auth-card">
              {#if CFG.emailAuthEnabled !== false}
                <div class="auth-pane">
                  <div class="auth-email-stack">
                    <div class="field-error-wrap">
                      <Tooltip.Root open={Boolean(loginEmailFieldError) && loginEmailTooltipOpen}>
                        <Input
                          bind:value={email}
                          type="email"
                          placeholder={t("wa_email_placeholder")}
                          autocomplete="email"
                          class={loginEmailFieldError ? "input-error" : ""}
                          on:keydown={submitEmailOnEnter}
                          on:input={() => {
                            loginEmailFieldError = "";
                            loginEmailTooltipOpen = false;
                          }}
                        />
                        {#if loginEmailFieldError}
                          <Tooltip.Trigger class="field-error-trigger" aria-label={loginEmailFieldError}>
                            <span class="field-error-icon" aria-hidden="true"><TriangleAlert size={18} /></span>
                          </Tooltip.Trigger>
                        {/if}
                        {#if loginEmailFieldError}
                          <Tooltip.Portal>
                            <Tooltip.Content class="field-error-tooltip">{loginEmailFieldError}</Tooltip.Content>
                          </Tooltip.Portal>
                        {/if}
                      </Tooltip.Root>
                    </div>
                    <Button class="wide" onclick={requestEmailCode} disabled={authBusy}>
                      <Mail size={18} />
                      {t("wa_send_code_email")}
                    </Button>
                  </div>
                </div>
              {/if}
              {#if CFG.emailAuthEnabled !== false}
                <div class="or-line"><span></span>{t("wa_or")}<span></span></div>
              {/if}
              <div class="auth-pane">
                <Button variant="telegram" class="wide telegram-login-button" onclick={openTelegramLogin} disabled={authBusy}>
                  <span class="telegram-login-text">
                    <Send size={17} />
                    {t("wa_login_telegram_button")}
                  </span>
                </Button>
              </div>
              {#if authStatus}
                <div class:error={authIsError} class="status-line auth-login-status">{authStatus}</div>
              {/if}
            </Card>
            {#if userAgreementUrl || privacyPolicyUrl}
              <div class="auth-legal">
                <span class="auth-legal-intro">{t("wa_auth_legal_intro")}</span>
                <div class="auth-legal-links">
                  {#if privacyPolicyUrl}
                    <a
                      href={privacyPolicyUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      on:click|preventDefault={() => openExternalLink(privacyPolicyUrl)}
                    >
                      {t("wa_auth_legal_privacy")}
                    </a>
                  {/if}
                  {#if privacyPolicyUrl && userAgreementUrl}
                    <span>{t("wa_auth_legal_and")}</span>
                  {/if}
                  {#if userAgreementUrl}
                    <a
                      href={userAgreementUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      on:click|preventDefault={() => openExternalLink(userAgreementUrl)}
                    >
                      {t("wa_auth_legal_agreement")}
                    </a>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {:else}
      <div class="phone-screen">
        {#if screen === "invite" || screen === "devices" || screen === "settings"}
          <header class="app-header accent-title">
            <div class="brand-row">
              <div class="brand-mark">
                {#if CFG.logoUrl}
                  <img src={CFG.logoUrl} alt="" />
                {:else}
                  <span>{brandEmoji}</span>
                {/if}
              </div>
              <strong>{brandTitle}</strong>
            </div>
          </header>
        {/if}

        {#if screen === "home"}
          <main class="home-layout">
            <div class="login-brand home-brand">
              <div class="brand-mark brand-mark-xl">
                {#if CFG.logoUrl}
                  <img src={CFG.logoUrl} alt="" />
                {:else}
                  <span>{brandEmoji}</span>
                {/if}
              </div>
              <h1>{brandTitle}</h1>
            </div>

            <div class="home-bottom">
              <Card class={`status-card${subscription.active ? "" : " status-card-inactive"}`}>
                {#if subscription.active}
                  <div class="sub-status">
                    <CheckCircle2 size={23} />
                    <div>
                      <h2>{trafficMode ? t("wa_home_access_active") : t("wa_home_subscription_active")} | {activeSubscriptionTermLabel(subscription)}</h2>
                      <p>{subscription.end_date_text ? t("wa_until_date", { date: subscription.end_date_text }) : subscription.remaining_text}</p>
                    </div>
                  </div>
                {:else}
                  <div class="sub-status sub-status-inactive">
                    <CircleX size={23} />
                    <h2>{t("wa_home_subscription_inactive")}</h2>
                  </div>
                {/if}
              </Card>

              {#if subscription.active}
                <Card>
                  <div class="traffic-top">
                    <span>{t("wa_home_traffic_used")}</span>
                    <strong>{trafficLabel(subscription)}</strong>
                  </div>
                  <div class="progress">
                    <span style={`width: ${trafficPercent(subscription)}%`}></span>
                  </div>
                  <div class="traffic-meta">
                    <span>{trafficResetLabel(subscription)}</span>
                    <span class="traffic-percent">{trafficPercent(subscription)}%</span>
                  </div>
                </Card>
              {:else if appSettings?.trial_enabled && appSettings?.trial_available}
                <Card class="trial-card">
                  <div class="trial-card-head">
                    <Gift size={22} />
                    <span>
                      <strong>{t("wa_trial_title")}</strong>
                      <small>{t("wa_trial_details", { days: Number(appSettings?.trial_duration_days || 0), traffic: trialTrafficLabel() })}</small>
                    </span>
                  </div>
                </Card>
              {/if}

              <div class="action-stack">
                <Button class="wide" onclick={openPaymentModal}>
                  {#if subscription.active}
                    <RefreshCw size={18} />
                  {:else if trafficMode}
                    <Database size={18} />
                  {/if}
                  {primaryPayActionLabel()}
                </Button>
                {#if !subscription.active && appSettings?.trial_enabled && appSettings?.trial_available}
                  <Button class="wide" variant="secondary" onclick={activateTrial} disabled={trialBusy}>
                    <Gift size={18} />
                    {t("wa_activate_trial")}
                  </Button>
                {/if}
              </div>
            </div>
          </main>
        {:else if screen === "invite"}
          <main class="content with-nav">
            <Card class="bonus-card">
              <div class="bonus-card-head">
                <Gift size={42} />
                <div>
                  <strong>{t("wa_referral_bonus_overview_title")}</strong>
                  {#if referralOneBonusPerReferee}
                    <p>{t("wa_referral_bonus_once_note")}</p>
                  {/if}
                </div>
              </div>
              <div>
                <h3 class="card-heading">{t("wa_referral_link_title")}</h3>
                <div class="copy-row referral-copy-row">
                  <code>{referral.webapp_link || referral.bot_link || t("wa_link_unavailable")}</code>
                  <Button class="referral-copy-button" onclick={() => copyText(referral.webapp_link || referral.bot_link, t("wa_link_copied"))}>
                    {t("wa_copy")}
                    <Copy size={17} />
                  </Button>
                </div>
              </div>
              {#if referralBonusDetails.length || referralWelcomeBonusDays > 0}
                <div class="referral-bonus-list">
                  {#if referralWelcomeBonusDays > 0}
                    <div class="referral-bonus-row">
                      <strong>{t("wa_referral_bonus_registration_title")}</strong>
                      <small>{t("wa_referral_bonus_friend_days", { days: referralWelcomeBonusDays })}</small>
                    </div>
                  {/if}
                  {#if referralBonusDetails.length}
                    <p class="referral-bonus-intro">{t("wa_referral_bonus_paid_intro")}</p>
                  {/if}
                  {#each referralBonusDetails as bonus, index (bonus.months || index)}
                    <div class="referral-bonus-row">
                      <strong>{bonus.title || `${bonus.months || "?"}`}</strong>
                      <small>{t("wa_referral_bonus_you_days", { days: Number(bonus.inviter_days || 0) })}</small>
                      <small>{t("wa_referral_bonus_friend_days", { days: Number(bonus.friend_days || 0) })}</small>
                    </div>
                  {/each}
                </div>
              {:else}
                <p class="status-line">{t("wa_referral_bonus_not_configured")}</p>
              {/if}
            </Card>
            <Card>
              <h3 class="card-heading card-heading-accent promo-heading">
                <Ticket size={18} />
                <span>{t("wa_activate_promo_title")}</span>
              </h3>
              <div class="copy-row">
                <div class="field-error-wrap">
                  <Tooltip.Root open={Boolean(promoFieldError)}>
                    <Input
                      bind:value={promoCode}
                      placeholder="PROMO2026"
                      class={promoFieldError ? "input-error" : ""}
                      on:input={() => (promoFieldError = "")}
                    />
                    {#if promoFieldError}
                      <Tooltip.Trigger class="field-error-trigger" aria-label={promoFieldError}>
                        <span class="field-error-icon" aria-hidden="true"><TriangleAlert size={18} /></span>
                      </Tooltip.Trigger>
                    {/if}
                    {#if promoFieldError}
                      <Tooltip.Portal>
                        <Tooltip.Content class="field-error-tooltip">{promoFieldError}</Tooltip.Content>
                      </Tooltip.Portal>
                    {/if}
                  </Tooltip.Root>
                </div>
                <Button variant="outline" onclick={applyPromo} disabled={promoBusy}>
                  {t("wa_activate")}
                </Button>
              </div>
              {#if promoStatus && !(promoIsError && promoFieldError)}
                <p class:error={promoIsError} class="status-line">{promoStatus}</p>
              {/if}
            </Card>
          </main>
        {:else if screen === "devices"}
          <main class="content with-nav">
            <Card class="devices-summary-card">
              <div class="devices-summary-head">
                <Smartphone size={28} />
                <span>
                  <strong>{t("wa_devices_title")}</strong>
                  <small>{devicesCountLabel()}</small>
                </span>
                <Button variant="icon" size="icon" onclick={() => loadDevices(true)} disabled={devicesBusy} aria-label={t("wa_devices_refresh")}>
                  <RefreshCw size={18} />
                </Button>
              </div>
              <div class="progress devices-progress">
                <span style={`width: ${devicesPercent()}%`}></span>
              </div>
            </Card>

            {#if devicesBusy && !devicesLoaded}
              <Card class="empty-card">{t("wa_devices_loading")}</Card>
            {:else if devicesStatus}
              <Card class="empty-card">
                <p class:error={devicesIsError} class="status-line">{devicesStatus}</p>
              </Card>
            {:else if !devicesData?.devices?.length}
              <Card class="empty-card devices-empty-card">
                <Smartphone size={28} />
                <span>{t("wa_devices_empty")}</span>
                <small>{t("wa_devices_empty_hint", { max: devicesLimitLabel() })}</small>
              </Card>
            {:else}
              <div class="devices-list">
                {#each devicesData.devices as device (device.token || device.index)}
                  <Card class="device-card">
                    <div class="device-card-head">
                      <div class="device-icon"><Smartphone size={20} /></div>
                      <span>
                        <strong>{device.display_name || t("wa_device_fallback_name", { index: device.index })}</strong>
                        <small>{device.platform_label || t("wa_devices_platform_unknown")}</small>
                      </span>
                    </div>
                    <div class="device-meta">
                      {#if device.created_at_text}
                        <div>
                          <span>{t("wa_devices_connected_at")}</span>
                          <strong>{device.created_at_text}</strong>
                        </div>
                      {/if}
                      {#if device.hwid_short}
                        <div>
                          <span>HWID</span>
                          <code>{device.hwid_short}</code>
                        </div>
                      {/if}
                      {#if device.user_agent}
                        <div class="device-user-agent">
                          <span>User Agent</span>
                          <small>{device.user_agent}</small>
                        </div>
                      {/if}
                    </div>
                    {#if device.can_disconnect}
                      <Button variant="outline" class="wide device-disconnect-button" onclick={() => openDeviceDisconnectDialog(device)}>
                        <CircleX size={17} />
                        {t("wa_devices_disconnect")}
                      </Button>
                    {/if}
                  </Card>
                {/each}
              </div>
            {/if}
          </main>
        {:else if screen === "settings"}
          <main class="content with-nav">
            <Card class="settings-profile">
              <div class="settings-avatar">
                {#if profileAvatarUrl}
                  <img src={profileAvatarUrl} alt={t("wa_settings_avatar_alt")} loading="lazy" referrerpolicy="no-referrer" />
                {:else}
                  <UserRound size={30} />
                {/if}
              </div>
              <div class="settings-profile-meta">
                <strong>{telegramProfileName}</strong>
                <small>{profileEmail}</small>
                <small>{profileTelegramId}</small>
              </div>
            </Card>
            <div class="settings-links-block">
              <div class="settings-divider" aria-hidden="true"></div>
              {#if user?.telegram_linked}
                <div class="settings-row settings-row-linked">
                  <CheckCircle2 size={21} />
                  <span>
                    <strong>{t("wa_settings_telegram_linked_title")}</strong>
                    <small>{profileTelegramId}</small>
                  </span>
                </div>
              {:else}
                <Button
                  variant="telegram"
                  class="wide settings-telegram-link-btn attention-wrap"
                  onclick={linkTelegramAccount}
                  disabled={linkTelegramBusy}
                >
                  <span class="attention-dot" aria-hidden="true"></span>
                  <Send size={18} />
                  {t("wa_settings_link_telegram_action")}
                </Button>
              {/if}
              {#if user?.email}
                <div class="settings-row settings-row-linked">
                  <CheckCircle2 size={21} />
                  <span>
                    <strong>{t("wa_settings_email_linked_title")}</strong>
                    <small>{user?.email}</small>
                  </span>
                </div>
              {:else}
                <button class="settings-row attention-wrap" type="button" on:click={openLinkEmailDialog} disabled={linkEmailBusy}>
                  <span class="attention-dot" aria-hidden="true"></span>
                  <Mail size={21} />
                  <span>
                    <strong>{t("wa_settings_link_email_action")}</strong>
                    <small>{emailLinkStatus}</small>
                  </span>
                  <ArrowRight size={17} />
                </button>
              {/if}
              <div class="settings-divider" aria-hidden="true"></div>
            </div>
            {#if languageMenuOpen || languageClickGuard}
              <button
                class="language-select-guard"
                type="button"
                aria-label={t("wa_close")}
                on:pointerdown|preventDefault|stopPropagation={() => setLanguageMenuOpen(false)}
                on:click|preventDefault|stopPropagation={() => setLanguageMenuOpen(false)}
              ></button>
            {/if}
            <div class="settings-list" class:settings-list--language-open={languageMenuOpen}>
              <div class="settings-row settings-row-language">
                <Globe2 size={21} />
                <Select.Root
                  type="single"
                  bind:open={languageMenuOpen}
                  value={currentLang}
                  items={languageOptions}
                  disabled={languageBusy}
                  onOpenChange={setLanguageMenuOpen}
                  onValueChange={updateAccountLanguage}
                >
                  <Select.Trigger class="language-select-trigger" aria-label={t("wa_settings_language")}>
                    <span class="language-select-copy">
                      <strong>{t("wa_settings_language")}</strong>
                      <small class="language-select-current">
                        <span class="emoji-flag" aria-hidden="true">{currentLanguageOption?.flag || "🏳️"}</span>
                        {currentLanguageOption?.label || userLanguage}
                      </small>
                    </span>
                    <ChevronsUpDown size={16} />
                  </Select.Trigger>
                  <Select.Content class="language-select-content" side="bottom" align="end" sideOffset={6}>
                    <Select.Viewport class="language-select-viewport">
                      {#each languageOptions as option (option.value)}
                        <Select.Item value={option.value} label={option.label} class="language-select-item">
                          <span class="language-select-item-main">
                            <span class="emoji-flag" aria-hidden="true">{option.flag}</span>
                            <span>{option.label}</span>
                          </span>
                          <Check size={15} class="language-select-item-check" />
                        </Select.Item>
                      {/each}
                    </Select.Viewport>
                  </Select.Content>
                </Select.Root>
              </div>
              {#if supportUrl}
                <button class="settings-row" type="button" on:click={() => openExternalLink(supportUrl)}>
                  <Send size={21} />
                  <span><strong>{t("menu_support_button")}</strong></span>
                  <ArrowRight size={17} />
                </button>
              {/if}
              {#if userAgreementUrl}
                <button class="settings-row" type="button" on:click={() => openExternalLink(userAgreementUrl)}>
                  <FileText size={21} />
                  <span><strong>{t("wa_settings_user_agreement")}</strong></span>
                  <ArrowRight size={17} />
                </button>
              {/if}
              {#if privacyPolicyUrl}
                <button class="settings-row" type="button" on:click={() => openExternalLink(privacyPolicyUrl)}>
                  <Shield size={21} />
                  <span><strong>{t("wa_settings_privacy_policy")}</strong></span>
                  <ArrowRight size={17} />
                </button>
              {/if}
              <button class="settings-row" type="button" on:click={logout}>
                <UserRound size={21} />
                <span><strong>{t("wa_logout")}</strong><small>{t("wa_end_session")}</small></span>
                <ArrowRight size={17} />
              </button>
            </div>
          </main>
        {/if}

        {#if screen === "home" || screen === "invite" || screen === "devices" || screen === "settings"}
          <nav class:bottom-nav-devices={devicesEnabled} class="bottom-nav" aria-label={t("wa_navigation")}>
            <button class:active={activeTab === "home"} type="button" on:click={goHome}>
              <Home size={21} />
              <span>{t("wa_nav_home")}</span>
            </button>
            <button class:active={activeTab === "invite"} type="button" on:click={goInvite}>
              <Gift size={21} />
              <span>{t("wa_nav_bonuses")}</span>
            </button>
            {#if devicesEnabled}
              <button class:active={activeTab === "devices"} type="button" on:click={goDevices}>
                <Smartphone size={21} />
                <span>{t("wa_nav_devices")}</span>
              </button>
            {/if}
            <button class:active={activeTab === "settings"} class="attention-wrap" type="button" on:click={goSettings}>
              {#if hasUnlinkedIdentity}
                <span class="attention-dot nav-attention-dot" aria-hidden="true"></span>
              {/if}
              <SettingsIcon size={21} />
              <span>{t("wa_nav_settings")}</span>
            </button>
          </nav>
        {/if}
      </div>

      <Dialog
        open={paymentModalOpen}
        title={paymentTitle()}
        description={paymentDescription()}
        closeLabel={t("wa_close")}
        onclose={closePaymentModal}
        class="payment-dialog-card"
      >
        <div class="payment-dialog-body">
          <div class="period-grid period-grid-two-columns">
            {#each plans as plan}
              <button
                class:active={selectedPlan?.months === plan.months}
                class="period-card"
                type="button"
                on:click={() => (selectedPlan = plan)}
              >
                <strong>{planDisplayTitle(plan)}</strong>
                <span>{priceLabel(plan)}</span>
                {#if planUnitHint(plan)}
                  <small>{planUnitHint(plan)}</small>
                {/if}
                {#if selectedPlan?.months === plan.months}
                  <CheckCircle2 size={18} />
                {/if}
              </button>
            {/each}
          </div>
          <div class="payment-divider" aria-hidden="true"></div>
          <div class="method-grid">
            {#if methods.length}
              {#each methods as method}
                {@const meta = methodMeta(method)}
                <button
                  class:active={selectedMethod === method.id}
                  class="method-card"
                  type="button"
                  on:click={() => (selectedMethod = method.id)}
                >
                  <span class="method-card-main">
                    {#if meta.icon}
                      <svelte:component this={meta.icon} size={19} />
                    {/if}
                    <strong>{meta.title}</strong>
                  </span>
                </button>
              {/each}
            {:else}
              <Card class="empty-card">{t("wa_payment_methods_not_configured")}</Card>
            {/if}
          </div>
          <Button class="wide bottom-action payment-submit-button" onclick={createPayment} disabled={!methods.length || payBusy}>
            {t("wa_pay")} {selectedPlan ? priceLabel(selectedPlan) : ""}
            <LockKeyhole size={17} />
          </Button>
        </div>
      </Dialog>

      <Dialog
        open={deviceConfirmOpen}
        title={t("wa_devices_disconnect_title")}
        description={t("wa_devices_disconnect_desc", {
          device: deviceToDisconnect?.display_name || t("wa_device_fallback_name", { index: deviceToDisconnect?.index || "" }),
        })}
        closeLabel={t("wa_close")}
        onclose={closeDeviceDisconnectDialog}
        class="payment-dialog-card"
      >
        <div class="payment-dialog-body">
          <Button variant="outline" class="wide device-danger-button" onclick={disconnectDevice} disabled={deviceDisconnectBusy}>
            <CircleX size={17} />
            {t("wa_devices_disconnect_confirm")}
          </Button>
          <Button variant="secondary" class="wide" onclick={closeDeviceDisconnectDialog} disabled={deviceDisconnectBusy}>
            {t("wa_cancel")}
          </Button>
        </div>
      </Dialog>

      <Dialog
        open={linkEmailOpen}
        title={t("wa_link_email_modal_title")}
        description={linkEmailPending ? t("wa_email_sent_to", { email: linkEmailPending }) : t("wa_link_email_modal_desc")}
        closeLabel={t("wa_close")}
        onclose={closeLinkEmailDialog}
        class={`payment-dialog-card${linkEmailPending ? " link-email-dialog-card" : ""}`}
      >
        <div class="payment-dialog-body">
          {#if !linkEmailPending}
            <div class="field-error-wrap">
              <Tooltip.Root open={Boolean(linkEmailFieldError)}>
                <Input
                  bind:value={linkEmailValue}
                  type="email"
                  placeholder={t("wa_email_placeholder")}
                  autocomplete="email"
                  class={linkEmailFieldError ? "input-error" : ""}
                  on:input={() => (linkEmailFieldError = "")}
                />
                {#if linkEmailFieldError}
                  <Tooltip.Trigger class="field-error-trigger" aria-label={linkEmailFieldError}>
                    <span class="field-error-icon" aria-hidden="true"><TriangleAlert size={18} /></span>
                  </Tooltip.Trigger>
                {/if}
                {#if linkEmailFieldError}
                  <Tooltip.Portal>
                    <Tooltip.Content class="field-error-tooltip">{linkEmailFieldError}</Tooltip.Content>
                  </Tooltip.Portal>
                {/if}
              </Tooltip.Root>
            </div>
            <Button class="wide bottom-action payment-submit-button" onclick={requestLinkEmailCode} disabled={linkEmailBusy}>
              {t("wa_send_code_email")}
            </Button>
          {:else}
            <div class="link-email-code-layout">
              <div class="otp-wrap link-email-code-center">
                <label class="otp-input-wrap">
                  <input
                    bind:value={linkEmailCode}
                    inputmode="numeric"
                    autocomplete="one-time-code"
                    maxlength="6"
                    aria-label={t("wa_email_code_aria")}
                  />
                  <span class="otp-slots" aria-hidden="true">
                    {#each Array.from({ length: 6 }) as _, index}
                      <span class:filled={linkEmailCode[index]}>{linkEmailCode[index] || ""}</span>
                    {/each}
                  </span>
                </label>
                <Button class="wide bottom-action payment-submit-button" onclick={verifyLinkEmailCode} disabled={linkEmailBusy}>
                  {t("wa_confirm")}
                </Button>
              </div>
              <button
                class="link-button link-email-resend"
                type="button"
                on:click={requestLinkEmailCode}
                disabled={linkEmailBusy || linkEmailResendCooldown > 0}
              >
                <RefreshCw size={15} />
                {linkEmailResendCooldown > 0
                  ? t("wa_auth_resend_wait", { seconds: linkEmailResendCooldown })
                  : t("wa_resend_code")}
              </button>
            </div>
          {/if}
          {#if linkEmailStatus}
            <p class:error={linkEmailIsError} class="status-line">{linkEmailStatus}</p>
          {/if}
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

