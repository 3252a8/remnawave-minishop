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
    Download,
    FileText,
    Gift,
    Globe2,
    Home,
    LockKeyhole,
    Mail,
    Plus,
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
  import BrandMark from "./BrandMark.svelte";
  import Card from "./lib/components/ui/card.svelte";
  import Dialog from "./lib/components/ui/dialog.svelte";
  import Input from "./lib/components/ui/input.svelte";
  import PreviewBoard from "./PreviewBoard.svelte";
  import AdminPanel from "./admin/AdminPanel.svelte";

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
    admin: "/admin",
  };
  const ADMIN_SECTIONS = new Set([
    "stats",
    "users",
    "payments",
    "promos",
    "ads",
    "broadcast",
    "logs",
    "tariffs",
    "settings",
  ]);
  const TELEGRAM_WEBAPP_SCRIPT_URL = "https://telegram.org/js/telegram-web-app.js";
  const TELEGRAM_SDK_BOOT_TIMEOUT_MS = 900;
  const TELEGRAM_SDK_ACTION_TIMEOUT_MS = 1800;
  const TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS = 15000;

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
      appVersion: "dev+local",
      appRepositoryUrl: "https://github.com/3252a8/remnawave-minishop",
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
        is_admin: true,
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
        premium_used: "32.0 GB",
        premium_limit: "50.0 GB",
        premium_used_bytes: 34359738368,
        premium_limit_bytes: 53687091200,
        premium_baseline_bytes: 53687091200,
        premium_topup_balance_bytes: 0,
        premium_is_limited: false,
        premium_title: "Premium-серверы",
        premium_node_labels: ["Premium NL-1", "Premium DE-1"],
        can_topup_regular_traffic: true,
        can_topup_premium_traffic: true,
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
  let tg = resolveTelegramWebApp();
  let telegramSdkStatus = tg ? "ready" : "idle";
  let telegramSdkPromise = null;
  let telegramLaunchParamsDetected = false;
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
    } else if (mode === "tariffs") {
      DEV_MOCK.data.settings.traffic_mode = false;
      DEV_MOCK.data.subscription = {
        ...DEV_MOCK.data.subscription,
        tariff_key: "standard",
        tariff_name: "Стандарт",
        tariff_description: "100 GB каждый месяц",
        billing_model: "period",
        traffic_limit_strategy: "MONTH",
      };
      DEV_MOCK.data.plans = [
        {
          id: "standard:period:1",
          tariff_key: "standard",
          tariff_name: "Стандарт",
          billing_model: "period",
          sale_mode: "subscription",
          months: 1,
          price: 150,
          currency: "RUB",
          title: "Стандарт",
          subtitle: "1 месяц",
          description: "100 GB каждый месяц",
          monthly_gb: 100,
        },
        {
          id: "standard:period:3",
          tariff_key: "standard",
          tariff_name: "Стандарт",
          billing_model: "period",
          sale_mode: "subscription",
          months: 3,
          price: 400,
          currency: "RUB",
          title: "Стандарт",
          subtitle: "3 месяца",
          description: "100 GB каждый месяц",
          monthly_gb: 100,
        },
        {
          id: "business:period:1",
          tariff_key: "business",
          tariff_name: "Бизнес",
          billing_model: "period",
          sale_mode: "subscription",
          months: 1,
          price: 350,
          currency: "RUB",
          title: "Бизнес",
          subtitle: "1 месяц",
          description: "300 GB и приоритетные серверы",
          monthly_gb: 300,
        },
        {
          id: "traffic:traffic:50",
          tariff_key: "traffic",
          tariff_name: "Трафик",
          billing_model: "traffic",
          sale_mode: "traffic_package",
          months: 50,
          traffic_gb: 50,
          price: 799,
          currency: "RUB",
          title: "Трафик",
          subtitle: "50 GB",
          description: "Пакет без срока действия",
        },
      ];
      DEV_MOCK.data.tariff_change_options = {
        ok: true,
        current: {
          tariff_key: "standard",
          title: "Стандарт",
          description: "100 GB каждый месяц",
          billing_model: "period",
        },
        targets: [
          {
            tariff_key: "business",
            title: "Бизнес",
            description: "300 GB и приоритетные серверы",
            billing_model: "period",
            monthly_gb: 300,
            actions: [
              { mode: "recalc_days", kind: "free", title: "recalc_days", days_after: 10, remaining_days: 25 },
              { mode: "paid_diff", kind: "payment", title: "paid_diff", price: 190, currency: "RUB" },
            ],
          },
          {
            tariff_key: "traffic",
            title: "Трафик",
            description: "Пакеты без срока действия",
            billing_model: "traffic",
            actions: [
              { mode: "convert_days_to_gb", kind: "free", title: "convert_days_to_gb", converted_gb: 18, remaining_days: 25 },
              { mode: "buy_package", kind: "payment", title: "+50 GB", traffic_gb: 50, price: 799, currency: "RUB" },
            ],
          },
        ],
      };
      DEV_MOCK.data.topup_options = {
        ok: true,
        tariff_key: "standard",
        tariff_name: "Стандарт",
        traffic_percent: 86,
        warning_levels: [85, 90, 95],
        plans: [
          { id: "standard:topup:10", tariff_key: "standard", tariff_name: "Стандарт", sale_mode: "topup", traffic_gb: 10, months: 10, price: 99, currency: "RUB", title: "10 GB", subtitle: "Стандарт" },
          { id: "standard:topup:50", tariff_key: "standard", tariff_name: "Стандарт", sale_mode: "topup", traffic_gb: 50, months: 50, price: 399, currency: "RUB", title: "50 GB", subtitle: "Стандарт" },
          { id: "standard:topup:200", tariff_key: "standard", tariff_name: "Стандарт", sale_mode: "topup", traffic_gb: 200, months: 200, price: 1299, currency: "RUB", title: "200 GB", subtitle: "Стандарт" },
        ],
      };
      DEV_MOCK.data.device_topup_options = {
        ok: true,
        tariff_key: "standard",
        tariff_name: "Стандарт",
        current_limit: 5,
        plans: [
          { id: "standard:hwid:1", tariff_key: "standard", tariff_name: "Стандарт", sale_mode: "hwid_devices", device_count: 1, months: 1, price: 99, currency: "RUB", title: "+1", subtitle: "Стандарт" },
          { id: "standard:hwid:3", tariff_key: "standard", tariff_name: "Стандарт", sale_mode: "hwid_devices", device_count: 3, months: 3, price: 249, currency: "RUB", title: "+3", subtitle: "Стандарт" },
        ],
      };
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
    if (section === "invite" || section === "devices" || section === "settings" || section === "admin") {
      return section;
    }
    return "home";
  }

  function sectionFromPath(pathname) {
    const normalizedPath = String(pathname || "")
      .trim()
      .toLowerCase()
      .replace(/\/+$/, "");
    if (!normalizedPath || normalizedPath === "/") return "home";
    if (normalizedPath === "/admin" || normalizedPath.startsWith("/admin/")) return "admin";
    const section = normalizedPath.startsWith("/") ? normalizedPath.slice(1) : normalizedPath;
    return normalizeSection(section);
  }

  function adminSectionFromPath(pathname) {
    const normalized = String(pathname || "").toLowerCase().replace(/\/+$/, "");
    const m = normalized.match(/^\/admin\/([a-z0-9_-]+)(?:\/[^/]+)?$/);
    if (m && ADMIN_SECTIONS.has(m[1])) return m[1];
    return "stats";
  }

  function adminUserIdFromPath(pathname) {
    const normalized = String(pathname || "").toLowerCase().replace(/\/+$/, "");
    const m = normalized.match(/^\/admin\/users\/(-?\d+)$/);
    return m ? Number(m[1]) : null;
  }

  function syncSectionPath(section, replace = false, adminSection = null, adminUserId = null) {
    if (window.location.protocol === "file:") return;
    const normalized = normalizeSection(section);
    let targetPath = APP_SECTION_PATHS[normalized] || APP_SECTION_PATHS.home;
    if (normalized === "admin") {
      const adm = adminSection || adminSectionFromPath(window.location.pathname) || "stats";
      const uid = adminUserId ?? (adm === "users" ? adminUserIdFromPath(window.location.pathname) : null);
      targetPath = adm === "users" && uid ? `/admin/users/${uid}` : `/admin/${adm}`;
    }
    if (window.location.pathname === targetPath) return;
    const nextUrl = `${targetPath}${window.location.search}${window.location.hash}`;
    window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
  }

  function resolveTelegramWebApp() {
    return window.Telegram?.WebApp || null;
  }

  function refreshTelegramWebApp() {
    tg = resolveTelegramWebApp();
    if (tg) telegramSdkStatus = "ready";
    telegramMiniAppInitData = tg?.initData || readTelegramMiniAppInitDataFromLocation();
    if (telegramMiniAppInitData) telegramLaunchParamsDetected = true;
    return tg;
  }

  function readTelegramMiniAppInitDataFromLocation() {
    const queryText = window.location.search.replace(/^\?/, "");
    const hashText = window.location.hash.replace(/^#/, "");
    for (const text of [queryText, hashText]) {
      if (!text) continue;
      const params = new URLSearchParams(text);
      const initData = params.get("tgWebAppData");
      if (initData) return initData;
    }
    return "";
  }

  function hasTelegramLaunchParams() {
    refreshTelegramWebApp();
    if (telegramLaunchParamsDetected || telegramMiniAppInitData) {
      telegramLaunchParamsDetected = true;
      return true;
    }
    const queryText = window.location.search.replace(/^\?/, "");
    const hashText = window.location.hash.replace(/^#/, "");
    const detected = [queryText, hashText].some((text) => {
      if (!text) return false;
      const params = new URLSearchParams(text);
      return ["tgWebAppData", "tgWebAppVersion", "tgWebAppPlatform", "tgWebAppThemeParams"].some((key) =>
        params.has(key),
      );
    });
    if (detected) telegramLaunchParamsDetected = true;
    return detected;
  }

  function loadTelegramSdk(timeoutMs = TELEGRAM_SDK_BOOT_TIMEOUT_MS) {
    if (refreshTelegramWebApp()) return Promise.resolve(tg);
    if (telegramSdkPromise) return telegramSdkPromise;
    if (typeof document === "undefined") return Promise.resolve(null);

    telegramSdkStatus = "loading";
    telegramSdkPromise = new Promise((resolve) => {
      const existingScript = document.querySelector("script[data-rw-telegram-web-app-sdk]");
      const script = existingScript || document.createElement("script");
      let resolved = false;
      let timeoutId = null;

      const resolveOnce = (value) => {
        if (resolved) return;
        resolved = true;
        if (timeoutId) window.clearTimeout(timeoutId);
        resolve(value);
      };

      const refreshFromScript = () => {
        tg = resolveTelegramWebApp();
        telegramSdkStatus = tg ? "ready" : "unavailable";
        return tg;
      };

      script.addEventListener("load", () => resolveOnce(refreshFromScript()), { once: true });
      script.addEventListener(
        "error",
        () => {
          telegramSdkStatus = "unavailable";
          resolveOnce(null);
        },
        { once: true },
      );

      if (!existingScript) {
        script.src = TELEGRAM_WEBAPP_SCRIPT_URL;
        script.async = true;
        script.defer = true;
        script.dataset.rwTelegramWebAppSdk = "1";
        document.head.appendChild(script);
      }

      timeoutId = window.setTimeout(() => {
        if (!tg) telegramSdkStatus = "unavailable";
        resolveOnce(tg);
      }, timeoutMs);
    }).finally(() => {
      telegramSdkPromise = null;
    });
    return telegramSdkPromise;
  }

  async function ensureTelegramSdkForAction() {
    if (refreshTelegramWebApp()) return tg;
    return await loadTelegramSdk(TELEGRAM_SDK_ACTION_TIMEOUT_MS);
  }

  function createTelegramMiniAppAuthTimeout() {
    const controller = typeof AbortController === "undefined" ? null : new AbortController();
    let timedOut = false;
    let timeoutId = null;
    let timeoutPromise = new Promise(() => {});

    if (typeof window !== "undefined") {
      timeoutPromise = new Promise((_, reject) => {
        timeoutId = window.setTimeout(() => {
          timedOut = true;
          controller?.abort();
          const error = new Error("telegram_mini_app_auth_timeout");
          error.name = "AbortError";
          reject(error);
        }, TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS);
      });
    }

    return {
      promise: timeoutPromise,
      get signal() {
        return controller?.signal;
      },
      get timedOut() {
        return timedOut;
      },
      clear() {
        if (timeoutId) window.clearTimeout(timeoutId);
        timeoutId = null;
      },
    };
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

  async function publicApi(path, payload = {}, options = {}) {
    if (MOCK) {
      return mockApi(path, { method: "POST", body: JSON.stringify(payload) });
    }
    const response = await fetch(`${CFG.apiBase}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: options.signal,
    });
    return response.json();
  }

  async function mockApi(path, options = {}) {
    await new Promise((resolve) => window.setTimeout(resolve, 120));
    const cleanPath = String(path || "").split("?")[0];
    const adminUsers = [
      {
        user_id: 100200300,
        telegram_id: 100200300,
        username: "anna_ops",
        first_name: "Анна",
        last_name: "Смирнова",
        email: "anna@example.com",
        telegram_photo_url: "",
        registration_date: "2026-04-24T10:20:00Z",
        is_banned: false,
      },
      {
        user_id: 100200301,
        telegram_id: 87543123,
        username: "client_pro",
        first_name: "Максим",
        last_name: "Котов",
        email: "",
        telegram_photo_url: "",
        registration_date: "2026-04-26T08:15:00Z",
        is_banned: false,
      },
      {
        user_id: 100200302,
        telegram_id: 88440011,
        username: "",
        first_name: "Daria",
        last_name: "",
        email: "daria@example.com",
        telegram_photo_url: "",
        registration_date: "2026-04-29T16:45:00Z",
        is_banned: true,
      },
    ];
    if (path === "/admin/stats") {
      return {
        ok: true,
        users: { total_users: 248, active_subscriptions: 172, banned_users: 3 },
        financial: { total_revenue: 186240, successful_payments_count: 934 },
        panel_sync: { status: "success", last_sync_time: new Date().toISOString(), users_processed: 172, subscriptions_synced: 168 },
        recent_payments: [
          { payment_id: 1, user_id: 100200300, user_label: "anna_ops", amount: 790, currency: "RUB", provider: "yookassa", status: "succeeded", created_at: new Date().toISOString() },
        ],
      };
    }
    if (cleanPath === "/admin/users") return { ok: true, users: adminUsers, total: adminUsers.length, page: 0, page_size: 25 };
    if (cleanPath.startsWith("/admin/users/")) {
      const id = Number(cleanPath.split("/")[3]);
      const user = adminUsers.find((item) => item.user_id === id) || adminUsers[0];
      return {
        ok: true,
        user,
        active_subscription: {
          subscription_id: 10,
          end_date: "2026-06-08T12:00:00Z",
          tariff_key: "standard",
          auto_renew_enabled: true,
          provider: "yookassa",
        },
        subscriptions: [
          { subscription_id: 10, end_date: "2026-06-08T12:00:00Z", tariff_key: "standard", is_active: true, status_from_panel: "ACTIVE" },
          { subscription_id: 9, end_date: "2026-05-08T12:00:00Z", tariff_key: "standard", is_active: false, status_from_panel: "EXPIRED" },
        ],
        total_paid: 2380,
        recent_payments: [
          { payment_id: 12, amount: 790, currency: "RUB", provider: "yookassa", status: "succeeded", created_at: "2026-05-01T14:15:00Z" },
          { payment_id: 11, amount: 790, currency: "RUB", provider: "stars", status: "succeeded", created_at: "2026-04-01T14:15:00Z" },
        ],
        log_count: 18,
        subscription_url: "https://panel.example.com/sub/aBcDeFgHiJkLmNoP",
        referral: {
          code: "ABCD1234",
          bot_link: "https://t.me/preview_bot?start=ref_uABCD1234",
          webapp_link: "https://app.example.com/?ref=uABCD1234",
        },
      };
    }
    if (path === "/admin/tariffs") {
      return {
        ok: true,
        path: "config/tariffs.json",
        catalog: {
          default_tariff: "standard",
          topup_packages_default: { rub: [{ gb: 10, price: 99 }], stars: [] },
          tariffs: [
            {
              key: "standard",
              names: { ru: "Стандарт", en: "Standard" },
              descriptions: { ru: "Базовый набор серверов" },
              squad_uuids: ["db786ee8-816b-4760-80aa-1fc7a3669ff2"],
              billing_model: "period",
              monthly_gb: 500,
              prices_rub: { "1": 150, "3": 400 },
              prices_stars: { "1": 0, "3": 0 },
              enabled_periods: [1, 3],
              enabled: true,
            },
          ],
        },
      };
    }
    if (path === "/admin/settings") return { ok: true, sections: [] };
    if (cleanPath.startsWith("/admin/")) return { ok: true, payments: [], promos: [], logs: [], campaigns: [], total: 0 };
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
    if (path === "/devices/topup-options") return structuredCloneSafe(DEV_MOCK.data.device_topup_options || { ok: true, plans: [] });
    if (cleanPath === "/tariffs/topup-options") {
      const kind = new URLSearchParams(String(path || "").split("?")[1] || "").get("kind") || "regular";
      const payload = structuredCloneSafe(DEV_MOCK.data.topup_options || { ok: true, plans: [] });
      payload.topup_kind = kind;
      payload.plans = (payload.plans || []).filter((plan) => kind === "premium" ? plan.sale_mode === "premium_topup" : plan.sale_mode !== "premium_topup");
      return payload;
    }
    if (path === "/tariffs/change-options") return structuredCloneSafe(DEV_MOCK.data.tariff_change_options || { ok: true, targets: [] });
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
    if (path === "/tariffs/change" && String(options.method || "").toUpperCase() === "POST") {
      return { ok: true, tariff_key: "business" };
    }
    if (path === "/tariffs/change-payment" && String(options.method || "").toUpperCase() === "POST") {
      return {
        ok: true,
        action: "open_link",
        payment_url: "https://example.com/tariff-change-payment-preview",
        payment_id: 10002,
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
      const response = await api("/payments", {
        method: "POST",
        body: JSON.stringify({
          months: selectedPlan.months,
          traffic_gb: selectedPlan.traffic_gb,
          device_count: selectedPlan.device_count,
          tariff_key: selectedPlan.tariff_key,
          sale_mode: selectedPlan.sale_mode,
          method: selectedMethod,
        }),
      });
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
    if (topupOptions?.topup_kind === kind || tariffActionBusy) return;
    tariffActionBusy = true;
    try {
      topupOptions = null;
      selectedTopupPlan = null;
      const response = await api(`/tariffs/topup-options?kind=${encodeURIComponent(kind)}`);
      if (!response?.ok) throw response;
      topupOptions = response;
      selectedTopupPlan = response.plans?.[0] || null;
    } catch (error) {
      showToast(error?.message || t("wa_tariff_options_failed"));
      topupModalOpen = false;
    } finally {
      tariffActionBusy = false;
    }
  }

  async function loadTariffChangeOptions() {
    if (changeOptions || tariffActionBusy) return;
    tariffActionBusy = true;
    try {
      const response = await api("/tariffs/change-options");
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
      const response = await api("/payments", {
        method: "POST",
        body: JSON.stringify({
          months: selectedTopupPlan.months,
          traffic_gb: selectedTopupPlan.traffic_gb,
          tariff_key: selectedTopupPlan.tariff_key || topupOptions?.tariff_key,
          sale_mode: selectedTopupPlan.sale_mode || "topup",
          method: selectedMethod,
        }),
      });
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
      const response = await api("/devices/topup-options");
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
      const response = await api("/payments", {
        method: "POST",
        body: JSON.stringify({
          months: selectedDeviceTopupPlan.device_count || selectedDeviceTopupPlan.months,
          device_count: selectedDeviceTopupPlan.device_count || selectedDeviceTopupPlan.months,
          tariff_key: selectedDeviceTopupPlan.tariff_key || deviceTopupOptions?.tariff_key,
          sale_mode: "hwid_devices",
          method: selectedMethod,
        }),
      });
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
      const response = await api("/tariffs/change", {
        method: "POST",
        body: JSON.stringify({
          tariff_key: selectedChangeTarget.tariff_key,
          mode: selectedChangeAction.mode,
        }),
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
      let response;
      if (selectedChangeAction.mode === "buy_package") {
        response = await api("/payments", {
          method: "POST",
          body: JSON.stringify({
            tariff_key: selectedChangeTarget.tariff_key,
            traffic_gb: selectedChangeAction.traffic_gb,
            months: selectedChangeAction.traffic_gb,
            sale_mode: "topup",
            method: selectedMethod,
          }),
        });
      } else if (selectedChangeAction.mode === "buy_period") {
        response = await api("/payments", {
          method: "POST",
          body: JSON.stringify({
            tariff_key: selectedChangeTarget.tariff_key,
            months: selectedChangeAction.months,
            method: selectedMethod,
          }),
        });
      } else {
        response = await api("/tariffs/change-payment", {
          method: "POST",
          body: JSON.stringify({
            tariff_key: selectedChangeTarget.tariff_key,
            method: selectedMethod,
          }),
        });
      }
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

  function formatTrafficBytes(value) {
    const gb = Number(value || 0) / 1073741824;
    return formatTrafficGb(gb);
  }

  function planKey(plan) {
    return plan?.id || `${plan?.tariff_key || "legacy"}:${plan?.sale_mode || "subscription"}:${plan?.months || plan?.traffic_gb || ""}`;
  }

  function buildTariffCatalog(planList) {
    const byKey = new Map();
    for (const plan of planList || []) {
      const key = String(plan?.tariff_key || planKey(plan) || "").trim();
      if (!key) continue;
      const entry = byKey.get(key) || {
        key,
        title: plan?.tariff_name || plan?.title || key,
        description: plan?.description || "",
        billing_model: plan?.billing_model || (plan?.sale_mode === "traffic_package" || plan?.sale_mode === "traffic" ? "traffic" : "period"),
        monthly_gb: Number(plan?.monthly_gb || 0),
        traffic_packages: [],
        plans_count: 0,
      };
      if (!entry.description && plan?.description) entry.description = plan.description;
      if (!entry.monthly_gb && Number(plan?.monthly_gb || 0) > 0) entry.monthly_gb = Number(plan.monthly_gb);
      const trafficGb = Number(plan?.traffic_gb || 0);
      if (trafficGb > 0) entry.traffic_packages.push(trafficGb);
      entry.plans_count += 1;
      byKey.set(key, entry);
    }
    return Array.from(byKey.values());
  }

  function activeTariffName(sub, planList) {
    const direct = String(sub?.tariff_name || "").trim();
    if (direct) return direct;
    const key = String(sub?.tariff_key || "").trim();
    if (!key) return "";
    const plan = (planList || []).find((item) => item?.tariff_key === key);
    return String(plan?.tariff_name || plan?.title || key).trim();
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

  function tariffLimitLabel(tariff) {
    if (!tariff) return "";
    if (String(tariff.billing_model || "") === "traffic") {
      const values = (tariff.traffic_packages || []).filter((value) => Number(value) > 0).sort((a, b) => a - b);
      if (!values.length) return t("wa_tariff_model_traffic");
      const min = values[0];
      const max = values[values.length - 1];
      return min === max ? formatTrafficGb(min) : `${formatTrafficGb(min)} - ${formatTrafficGb(max)}`;
    }
    if (Number(tariff.monthly_gb || 0) > 0) return formatTrafficGb(tariff.monthly_gb);
    return t("wa_unlimited_traffic");
  }

  function actionKey(action) {
    return `${action?.mode || ""}:${action?.months || ""}:${action?.traffic_gb || ""}:${action?.price || ""}`;
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

  function premiumTrafficPercent(sub) {
    const used = Number(sub?.premium_used_bytes || 0);
    const limit = Number(sub?.premium_limit_bytes || 0);
    if (!limit || limit <= 0) return 0;
    return Math.max(0, Math.min(100, Math.round((used / limit) * 100)));
  }

  function premiumTrafficLabel(sub) {
    return t("wa_traffic_of", { used: sub?.premium_used || "0 GB", limit: sub?.premium_limit || "0 GB" });
  }

  function premiumTitle(sub = subscription) {
    return String(sub?.premium_title || "").trim() || t("wa_premium_traffic_title", {}, "Premium-серверы");
  }

  function premiumTrafficLeftLabel(sub) {
    const left = Math.max(0, Number(sub?.premium_limit_bytes || 0) - Number(sub?.premium_used_bytes || 0));
    return formatTrafficBytes(left);
  }

  function premiumTopupBalanceLabel(sub) {
    return formatTrafficBytes(Number(sub?.premium_topup_balance_bytes || 0));
  }

  function premiumServerLabels(sub) {
    const labels = Array.isArray(sub?.premium_node_labels) && sub.premium_node_labels.length
      ? sub.premium_node_labels
      : sub?.premium_squad_labels || [];
    return labels.map((label) => String(label || "").trim()).filter(Boolean);
  }

  function planDisplayTitle(plan) {
    if (plan?.tariff_key) {
      return plan?.tariff_name || plan?.title || plan?.tariff_key;
    }
    if (trafficMode || plan?.sale_mode === "traffic") {
      return plan?.title || formatTrafficGb(plan?.traffic_gb || plan?.months);
    }
    const months = Number(plan?.months || 0);
    if (months === 12) {
      return t("wa_plan_one_year");
    }
    return plan?.title || "";
  }

  function planSubtitle(plan) {
    if (!plan?.tariff_key) return "";
    if (plan?.subtitle) return plan.subtitle;
    if (plan?.sale_mode === "traffic_package" || plan?.sale_mode === "topup" || plan?.sale_mode === "premium_topup" || plan?.billing_model === "traffic") {
      return formatTrafficGb(plan?.traffic_gb || plan?.months);
    }
    return _formatMonthsForClient(plan?.months);
  }

  function planUnitHint(plan) {
    if (trafficMode || plan?.sale_mode === "traffic" || plan?.sale_mode === "traffic_package" || plan?.sale_mode === "topup" || plan?.sale_mode === "premium_topup") {
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

  function formatCompactNumber(value) {
    const numeric = Number(value || 0);
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
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
    if (topupKind === "premium") return topupOptions?.tariff_name ? t("wa_topup_for_tariff", { tariff: topupOptions.tariff_name }) : "";
    if (singleTariffMode) return "";
    return topupOptions?.tariff_name ? t("wa_topup_for_tariff", { tariff: topupOptions.tariff_name }) : "";
  }

  function topupModalTitle() {
    if (topupKind === "premium") return premiumTitle(subscription);
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

  function _formatMonthsForClient(value) {
    const months = Number(value || 0);
    if (months === 1) return currentLang === "en" ? "1 month" : "1 месяц";
    if (months === 12) return currentLang === "en" ? "1 year" : "1 год";
    return currentLang === "en" ? `${months} months` : `${months} мес.`;
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
          <BrandMark class="brand-mark-lg" logoUrl={CFG.logoUrl} emoji={brandEmoji} />
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
              <BrandMark class="brand-mark-xl" logoUrl={CFG.logoUrl} emoji={brandEmoji} />
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
                <Button
                  variant="telegram"
                  class={`wide telegram-login-button${telegramLoginUnavailable ? " unavailable" : ""}${telegramLoginChecking ? " checking" : ""}`}
                  onclick={openTelegramLogin}
                  disabled={authBusy || telegramLoginBusy || telegramLoginUnavailable}
                  aria-label={telegramLoginLabel}
                >
                  <span class="telegram-login-text">
                    {#if telegramLoginChecking}
                      <span class="telegram-button-spinner" aria-hidden="true"></span>
                    {:else}
                      <Send size={17} />
                    {/if}
                    {telegramLoginLabel}
                  </span>
                </Button>
              </div>
              {#if !telegramLoginChecking && (authStatus || telegramLoginUnavailableMessage)}
                <div
                  class:error={authIsError || Boolean(telegramLoginUnavailableMessage)}
                  class="status-line auth-login-status"
                >
                  {authStatus || telegramLoginUnavailableMessage}
                </div>
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
      <div class="phone-screen" class:home-screen={screen === "home"}>
        {#if screen === "invite" || screen === "devices" || screen === "settings"}
          <header class="app-header accent-title">
            <div class="brand-row">
              <BrandMark logoUrl={CFG.logoUrl} emoji={brandEmoji} />
              <strong>{brandTitle}</strong>
            </div>
          </header>
        {/if}

        {#if screen === "home"}
          <main class="home-layout">
            <div class="login-brand home-brand">
              <BrandMark class="brand-mark-xl" logoUrl={CFG.logoUrl} emoji={brandEmoji} />
              <h1>{brandTitle}</h1>
            </div>

            <div class="home-bottom">
              <Card class={`status-card${subscription.active ? "" : " status-card-inactive"}`}>
                {#if subscription.active}
                  <div class="sub-status">
                    <CheckCircle2 size={23} />
                    <div>
                      <h2>{trafficMode ? t("wa_home_access_active") : t("wa_home_subscription_active")} | {activeSubscriptionTermLabel(subscription)}</h2>
                      {#if hasActiveTariffSubscription && hasMultipleTariffs && currentTariffName}
                        <p class="current-tariff-line">{t("wa_current_tariff", { tariff: currentTariffName })}</p>
                      {/if}
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
                <Card class={canOpenRegularTopupModal ? "traffic-card-clickable" : ""}>
                  {#if canOpenRegularTopupModal}
                    <button class="card-click-target" type="button" on:click={() => openTopupModal("regular")} aria-label={t("wa_topup_traffic")}></button>
                  {/if}
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
                {#if Number(subscription?.premium_limit_bytes || 0) > 0}
                  <Card class={`${canOpenPremiumTopupModal ? "traffic-card-clickable " : ""}premium-traffic-card${subscription?.premium_is_limited ? " premium-traffic-card-limited" : ""}`}>
                    {#if canOpenPremiumTopupModal}
                      <button class="card-click-target" type="button" on:click={() => openTopupModal("premium")} aria-label={premiumTitle(subscription)}></button>
                    {/if}
                    <div class="traffic-top">
                      <span>{premiumTitle(subscription)}</span>
                      <strong>{premiumTrafficLabel(subscription)}</strong>
                    </div>
                    <div class="progress premium-progress">
                      <span style={`width: ${premiumTrafficPercent(subscription)}%`}></span>
                    </div>
                    <div class="traffic-meta premium-traffic-meta">
                      {#if premiumServerLabels(subscription).length}
                        <details class="premium-server-dropdown">
                          <summary>
                            <span>{subscription?.premium_is_limited ? t("wa_premium_access_limited", {}, "Доступ к premium временно ограничен") : t("wa_premium_reset_monthly", {}, "Отдельный лимит на месяц")}</span>
                            <ChevronsUpDown size={13} />
                          </summary>
                          <div class="premium-server-list premium-server-list-dropdown">
                            <small>{t("wa_premium_servers_limited", {}, "Отдельный лимит действует на")}</small>
                            <div>
                              {#each premiumServerLabels(subscription).slice(0, 8) as label}
                                <span>{label}</span>
                              {/each}
                            </div>
                          </div>
                        </details>
                      {:else}
                        <span>{subscription?.premium_is_limited ? t("wa_premium_access_limited", {}, "Доступ к premium временно ограничен") : t("wa_premium_reset_monthly", {}, "Отдельный лимит на месяц")}</span>
                      {/if}
                      <span class="traffic-percent">{premiumTrafficPercent(subscription)}%</span>
                    </div>
                  </Card>
                {/if}
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
                {#if subscription.active}
                  <Button class="wide" onclick={openConnectLink}>
                    <Download size={18} />
                    {t("wa_install_and_configure")}
                  </Button>
                {/if}
                <Button class="wide" variant={subscription.active ? "secondary" : "default"} onclick={openPaymentModal}>
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
                {#if canChangeTariff}
                  <Button class="wide" variant="secondary" onclick={openTariffChangeModal}>
                    <RefreshCw size={18} />
                    {t("wa_change_tariff")}
                  </Button>
                {/if}
                {#if canShowTopupButton}
                  <Button class="wide" variant="secondary" onclick={() => openTopupModal(canOpenRegularTopupModal ? "regular" : "premium")}>
                    <Database size={18} />
                    {t("wa_topup_traffic")}
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
              {#if subscription?.active && subscription?.max_devices !== 0}
                <Button variant="secondary" class="wide" onclick={openDeviceTopupModal}>
                  <Plus size={17} />
                  {t("wa_buy_hwid_devices")}
                </Button>
              {/if}
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
            {#if isAdmin}
              <div class="settings-admin-block">
                <div class="settings-divider" aria-hidden="true"></div>
                <button class="settings-row settings-row-admin" type="button" on:click={openAdminPanel}>
                  <Shield size={21} />
                  <span>
                    <strong>Админ-панель</strong>
                    <small>Управление приложением</small>
                  </span>
                  <ArrowRight size={17} />
                </button>
              </div>
            {/if}
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
                class:language-select-guard--armed={languageClickGuardArmed}
                type="button"
                aria-label={t("wa_close")}
                on:pointerdown|preventDefault|stopPropagation={() => languageClickGuardArmed && setLanguageMenuOpen(false)}
                on:click|preventDefault|stopPropagation={() => languageClickGuardArmed && setLanguageMenuOpen(false)}
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
                <button class="settings-row settings-row-support" type="button" on:click={() => openExternalLink(supportUrl)}>
                  <Send size={21} />
                  <span><strong>{t("menu_support_button")}</strong></span>
                  <ArrowRight size={17} />
                </button>
              {/if}
              {#if userAgreementUrl}
                <button class="settings-row settings-row-policy" type="button" on:click={() => openExternalLink(userAgreementUrl)}>
                  <FileText size={21} />
                  <span><strong>{t("wa_settings_user_agreement")}</strong></span>
                  <ArrowRight size={17} />
                </button>
              {/if}
              {#if privacyPolicyUrl}
                <button class="settings-row settings-row-policy" type="button" on:click={() => openExternalLink(privacyPolicyUrl)}>
                  <Shield size={21} />
                  <span><strong>{t("wa_settings_privacy_policy")}</strong></span>
                  <ArrowRight size={17} />
                </button>
              {/if}
              <button class="settings-row settings-row-logout" type="button" on:click={logout}>
                <UserRound size={21} />
                <span><strong>{t("wa_logout")}</strong><small>{t("wa_end_session")}</small></span>
                <ArrowRight size={17} />
              </button>
            </div>
          </main>
        {/if}

        {#if screen === "home" || screen === "invite" || screen === "devices" || screen === "settings"}
          <nav class:bottom-nav-devices={devicesEnabled} class="bottom-nav" aria-label={t("wa_navigation")}>
            <div class="rail-brand" aria-hidden="true">
              <BrandMark logoUrl={CFG.logoUrl} emoji={brandEmoji} />
              <strong>{brandTitle}</strong>
            </div>
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
            {#if isAdmin}
              <button class="rail-admin-entry" type="button" on:click={openAdminPanel}>
                <Shield size={21} />
                <span>Админ-панель</span>
              </button>
            {/if}
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
          {#if tariffMode && !singleTariffMode && paymentStep === "tariff"}
            {#if tariffCatalog.length}
              <div class="option-list tariff-list">
                {#each tariffCatalog as tariff}
                  <button
                    class:active={selectedTariffKey === tariff.key}
                    class="option-row tariff-row"
                    type="button"
                    on:click={() => selectTariff(tariff)}
                  >
                    <span class="option-row-main">
                      <strong>{tariff.title}</strong>
                      <small>{tariff.description || t("wa_tariff_no_description")}</small>
                    </span>
                    <span class="option-row-meta">
                      <em>{tariffLimitLabel(tariff)}</em>
                      {#if selectedTariffKey === tariff.key}
                        <CheckCircle2 size={18} />
                      {:else}
                        <ArrowRight size={17} />
                      {/if}
                    </span>
                  </button>
                {/each}
              </div>
              <Button class="wide bottom-action payment-submit-button" onclick={continueWithSelectedTariff} disabled={!selectedTariffKey}>
                {t("wa_next")}
                <ArrowRight size={17} />
              </Button>
            {:else}
              <Card class="empty-card">{t("wa_no_tariff_change_options")}</Card>
            {/if}
          {:else}
            {#if tariffMode}
              {#if !singleTariffMode && !(subscription?.active && subscription?.tariff_key && tariffCatalog.some((t) => t.key === subscription.tariff_key))}
                <button class="back-inline" type="button" on:click={backToTariffList}>
                  <ArrowLeft size={16} />
                  {t("wa_back_to_tariffs")}
                </button>
              {/if}
              {#if hasMultipleTariffs && selectedTariff}
                <p class="tariff-step-caption">{t("wa_selected_tariff", { tariff: selectedTariff.title })}</p>
              {/if}
            {/if}
            {#if selectedTariffPlans.length}
              <div class="period-grid period-grid-two-columns">
                {#each selectedTariffPlans as plan}
                  <button
                    class:active={planKey(selectedPlan) === planKey(plan)}
                    class="period-card"
                    type="button"
                    on:click={() => (selectedPlan = plan)}
                  >
                    <strong>{planSubtitle(plan) || planDisplayTitle(plan)}</strong>
                    <span>{priceLabel(plan)}</span>
                    {#if planUnitHint(plan)}
                      <small>{planUnitHint(plan)}</small>
                    {/if}
                    {#if planKey(selectedPlan) === planKey(plan)}
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
              <Button class="wide bottom-action payment-submit-button" onclick={createPayment} disabled={!selectedPlan || !methods.length || payBusy}>
                {t("wa_pay")} {selectedPlan ? priceLabel(selectedPlan) : ""}
                <LockKeyhole size={17} />
              </Button>
            {:else}
              <Card class="empty-card">{t("wa_no_tariff_change_options")}</Card>
            {/if}
          {/if}
          {#if !tariffMode}
            <div class="period-grid period-grid-two-columns">
              {#each plans as plan}
                <button
                  class:active={planKey(selectedPlan) === planKey(plan)}
                  class="period-card"
                  type="button"
                  on:click={() => (selectedPlan = plan)}
                >
                  <strong>{planDisplayTitle(plan)}</strong>
                  {#if planSubtitle(plan)}
                    <em>{planSubtitle(plan)}</em>
                  {/if}
                  <span>{priceLabel(plan)}</span>
                  {#if planUnitHint(plan)}
                    <small>{planUnitHint(plan)}</small>
                  {/if}
                  {#if planKey(selectedPlan) === planKey(plan)}
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
            <Button class="wide bottom-action payment-submit-button" onclick={createPayment} disabled={!selectedPlan || !methods.length || payBusy}>
              {t("wa_pay")} {selectedPlan ? priceLabel(selectedPlan) : ""}
              <LockKeyhole size={17} />
            </Button>
          {/if}
        </div>
      </Dialog>

      <Dialog
        open={changeModalOpen}
        title={t("wa_change_tariff")}
        description={tariffChangeModalDescription()}
        closeLabel={t("wa_close")}
        onclose={closeTariffChangeModal}
        class="payment-dialog-card"
      >
        <div class="payment-dialog-body">
          {#if !changeOptions}
            <div class="dialog-skeleton" aria-label={t("wa_tariff_options_loading")}>
              <div class="tariff-action-list">
                {#each [1, 2] as _}
                  <div class="tariff-action-card skeleton-row">
                    <span>
                      <span class="skeleton-line skeleton-line-title"></span>
                      <span class="skeleton-line skeleton-line-short"></span>
                    </span>
                    <span class="skeleton-line skeleton-line-price"></span>
                  </div>
                {/each}
              </div>
              <div class="payment-divider" aria-hidden="true"></div>
              <div class="option-list">
                {#each [1, 2] as _}
                  <div class="option-row change-action-row skeleton-row">
                    <span class="option-row-main">
                      <span class="skeleton-line skeleton-line-title"></span>
                      <span class="skeleton-line skeleton-line-short"></span>
                    </span>
                  </div>
                {/each}
              </div>
              <div class="skeleton-pay-button"></div>
            </div>
          {:else if changeOptions?.targets?.length}
            <p class="section-kicker">{t("wa_tariff_change_targets_title")}</p>
            <div class="tariff-action-list">
              {#each changeOptions.targets as target}
                <button
                  class:active={selectedChangeTarget?.tariff_key === target.tariff_key}
                  class="tariff-action-card"
                  type="button"
                  on:click={() => {
                    selectedChangeTarget = target;
                    selectedChangeAction = target.actions?.[0] || null;
                  }}
                >
                  <span>
                    <strong>{target.title}</strong>
                    <small>{target.description}</small>
                  </span>
                  <em>{target.billing_model === "traffic" ? t("wa_tariff_model_traffic") : t("wa_tariff_model_period")}</em>
                </button>
              {/each}
            </div>
            {#if selectedChangeTarget?.actions?.length}
              <div class="payment-divider" aria-hidden="true"></div>
              <p class="section-kicker">{t("wa_tariff_change_strategy_title")}</p>
              <div class="option-list">
                {#each selectedChangeTarget.actions as action}
                  <button
                    class:active={actionKey(selectedChangeAction) === actionKey(action)}
                    class="option-row change-action-row"
                    type="button"
                    on:click={() => (selectedChangeAction = action)}
                  >
                    <span class="option-row-main">
                      <strong>{changeActionTitle(action)}</strong>
                      {#if action.mode === "recalc_days"}
                        <small>{t("wa_tariff_change_recalc_hint", { days: Number(action.remaining_days || 0) })}</small>
                      {:else if action.mode === "convert_days_to_gb"}
                        <small>{t("wa_tariff_change_convert_hint", { days: Number(action.remaining_days || 0) })}</small>
                      {:else if action.kind === "payment"}
                        <small>{t("wa_tariff_change_payment_hint")}</small>
                      {/if}
                    </span>
                    {#if actionKey(selectedChangeAction) === actionKey(action)}
                      <CheckCircle2 size={18} />
                    {/if}
                  </button>
                {/each}
              </div>
              {#if selectedChangeAction?.kind === "payment"}
                <div class="method-grid">
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
                </div>
              {/if}
              <Button class="wide bottom-action payment-submit-button" onclick={openTariffChangeConfirm} disabled={tariffActionBusy || payBusy}>
                {selectedChangeAction?.kind === "payment" ? t("wa_pay") : t("wa_apply")}
                <ArrowRight size={17} />
              </Button>
            {:else}
              <Card class="empty-card">{t("wa_no_tariff_change_options")}</Card>
            {/if}
          {:else}
            <Card class="empty-card">{t("wa_no_tariff_change_options")}</Card>
          {/if}
        </div>
      </Dialog>

      <Dialog
        open={changeConfirmOpen}
        title={t("wa_tariff_change_confirm_title")}
        description={t("wa_tariff_change_confirm_desc")}
        closeLabel={t("wa_close")}
        onclose={closeTariffChangeConfirm}
        class="payment-dialog-card"
      >
        <div class="payment-dialog-body">
          <Card class="confirm-summary-card">
            {#each tariffChangeSummary() as row}
              <p>{row}</p>
            {/each}
          </Card>
          <Button class="wide bottom-action payment-submit-button" onclick={applyTariffChange} disabled={tariffActionBusy || payBusy}>
            {selectedChangeAction?.kind === "payment" ? t("wa_confirm_and_pay") : t("wa_confirm_and_apply")}
            <ArrowRight size={17} />
          </Button>
          <Button variant="secondary" class="wide" onclick={closeTariffChangeConfirm} disabled={tariffActionBusy || payBusy}>
            {t("wa_cancel")}
          </Button>
        </div>
      </Dialog>

      <Dialog
        open={topupModalOpen}
        title={topupModalTitle()}
        description={topupModalDescription()}
        closeLabel={t("wa_close")}
        onclose={closeTopupModal}
        class="payment-dialog-card"
      >
        <div class="payment-dialog-body">
          {#if !topupOptions}
            <div class="dialog-skeleton" aria-label={t("wa_tariff_options_loading")}>
              <div class="option-list">
                {#each [1, 2, 3] as _}
                  <div class="option-row plan-row skeleton-row">
                    <span class="option-row-main">
                      <span class="skeleton-line skeleton-line-title"></span>
                      <span class="skeleton-line skeleton-line-short"></span>
                    </span>
                    <span class="option-row-meta">
                      <span class="skeleton-line skeleton-line-price"></span>
                      <span class="skeleton-line skeleton-line-tiny"></span>
                    </span>
                  </div>
                {/each}
              </div>
              <div class="method-grid">
                {#each [1, 2] as _}
                  <div class="method-card skeleton-method">
                    <span class="skeleton-dot"></span>
                    <span class="skeleton-line skeleton-line-method"></span>
                  </div>
                {/each}
              </div>
              <div class="skeleton-pay-button"></div>
            </div>
          {:else if topupOptions?.plans?.length}
            <div class="option-list">
              {#each topupOptions.plans as plan}
                <button
                  class:active={planKey(selectedTopupPlan) === planKey(plan)}
                  class="option-row plan-row"
                  type="button"
                  on:click={() => (selectedTopupPlan = plan)}
                >
                  <span class="option-row-main">
                    <strong>{plan.title}</strong>
                    {#if !singleTariffMode || plan.sale_mode === "premium_topup"}
                      <small>{plan.subtitle || topupOptions.tariff_name}</small>
                    {/if}
                  </span>
                  <span class="option-row-meta">
                    <em>{priceLabel(plan)}</em>
                    {#if planUnitHint(plan)}
                      <small>{planUnitHint(plan)}</small>
                    {/if}
                  </span>
                </button>
              {/each}
            </div>
            {@const carryoverNotes = topupCarryoverNotes()}
            {#if carryoverNotes.length}
              <div class="topup-carryover-note">
                {#each carryoverNotes as note}
                  <p>{note}</p>
                {/each}
              </div>
            {/if}
            <div class="method-grid">
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
            </div>
            <Button class="wide bottom-action payment-submit-button" onclick={createTopupPayment} disabled={!selectedTopupPlan || !methods.length || payBusy}>
              {t("wa_buy_traffic")} {selectedTopupPlan ? priceLabel(selectedTopupPlan) : ""}
              <LockKeyhole size={17} />
            </Button>
          {:else}
            <Card class="empty-card">{t("wa_no_topup_options")}</Card>
          {/if}
        </div>
      </Dialog>

      <Dialog
        open={deviceTopupModalOpen}
        title={t("wa_buy_hwid_devices")}
        description={deviceTopupModalDescription()}
        closeLabel={t("wa_close")}
        onclose={closeDeviceTopupModal}
        class="payment-dialog-card"
      >
        <div class="payment-dialog-body">
          {#if !deviceTopupOptions}
            <div class="dialog-skeleton" aria-label={t("wa_tariff_options_loading")}>
              <div class="option-list">
                {#each [1, 2, 3] as _}
                  <div class="option-row plan-row skeleton-row">
                    <span class="option-row-main">
                      <span class="skeleton-line skeleton-line-title"></span>
                      <span class="skeleton-line skeleton-line-short"></span>
                    </span>
                    <span class="option-row-meta">
                      <span class="skeleton-line skeleton-line-price"></span>
                    </span>
                  </div>
                {/each}
              </div>
              <div class="method-grid">
                {#each [1, 2] as _}
                  <div class="method-card skeleton-method">
                    <span class="skeleton-dot"></span>
                    <span class="skeleton-line skeleton-line-method"></span>
                  </div>
                {/each}
              </div>
              <div class="skeleton-pay-button"></div>
            </div>
          {:else if deviceTopupOptions?.plans?.length}
            <div class="option-list">
              {#each deviceTopupOptions.plans as plan}
                <button
                  class:active={planKey(selectedDeviceTopupPlan) === planKey(plan)}
                  class="option-row plan-row"
                  type="button"
                  on:click={() => (selectedDeviceTopupPlan = plan)}
                >
                  <span class="option-row-main">
                    <strong>{t("wa_hwid_devices_package", { count: Number(plan.device_count || plan.months || 0) })}</strong>
                    <small>{plan.subtitle || deviceTopupOptions.tariff_name}</small>
                  </span>
                  <span class="option-row-meta">
                    <em>{priceLabel(plan)}</em>
                    {#if planKey(selectedDeviceTopupPlan) === planKey(plan)}
                      <CheckCircle2 size={18} />
                    {/if}
                  </span>
                </button>
              {/each}
            </div>
            <div class="method-grid">
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
            </div>
            <Button class="wide bottom-action payment-submit-button" onclick={createDeviceTopupPayment} disabled={!selectedDeviceTopupPlan || !methods.length || payBusy}>
              {t("wa_pay")} {selectedDeviceTopupPlan ? priceLabel(selectedDeviceTopupPlan) : ""}
              <LockKeyhole size={17} />
            </Button>
          {:else}
            <Card class="empty-card">{t("wa_no_hwid_device_options")}</Card>
          {/if}
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

