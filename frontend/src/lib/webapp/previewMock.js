import { DEMO_DATASET } from "./demoDataset.js";

const DEMO_LANGUAGE_STORAGE_KEY = "rw_minishop_demo_language";

function readStoredDemoLanguage() {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage?.getItem(DEMO_LANGUAGE_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

const WINDOWS_95_THEME = {
  key: "windows95",
  names: { ru: "Windows 95", en: "Windows 95" },
  enabled: true,
  default: false,
  css_file: "style.css",
  assets_version: 9,
  tokens: {
    color_scheme: "light",
    style_preset: "win95",
  },
};

const ASCII_THEME = {
  key: "ascii",
  names: { ru: "ASCII", en: "ASCII" },
  enabled: true,
  default: false,
  css_file: "style.css",
  tokens: {
    color_scheme: "dark",
    style_preset: "ascii",
  },
};

const INSTALL_GUIDES_CONFIG = {
  version: "1",
  locales: ["ru", "en"],
  brandingSettings: {
    title: "/minishop",
    logoUrl: "https://example.com/logo.svg",
    supportUrl: "https://t.me/support",
  },
  uiConfig: {
    subscriptionInfoBlockType: "collapsed",
    installationGuidesBlockType: "cards",
  },
  baseSettings: {
    metaTitle: "Subscription",
    metaDescription: "Subscription",
    showConnectionKeys: false,
    hideGetLinkButton: false,
  },
  baseTranslations: Object.fromEntries(
    [
      "active",
      "bandwidth",
      "connectionKeysHeader",
      "copyLink",
      "expired",
      "expires",
      "expiresIn",
      "getLink",
      "inactive",
      "indefinitely",
      "installationGuideHeader",
      "linkCopied",
      "linkCopiedToClipboard",
      "name",
      "scanQrCode",
      "scanQrCodeDescription",
      "scanToImport",
      "status",
      "unknown",
    ].map((key) => [
      key,
      {
        ru: key === "installationGuideHeader" ? "Установка и настройка" : key,
        en: key === "installationGuideHeader" ? "Install and configure" : key,
      },
    ])
  ),
  svgLibrary: {
    App: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 7h6M9 17h6"/></svg>',
    Copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="8" y="8" width="10" height="10" rx="2"/><path d="M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    Desktop:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
    Download:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>',
    Phone:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/></svg>',
  },
  platforms: {
    ios: {
      displayName: "iOS",
      svgIconKey: "Phone",
      apps: [
        {
          name: "Streisand",
          svgIconKey: "App",
          featured: true,
          blocks: [
            {
              svgIconKey: "Download",
              svgIconColor: "green",
              title: { ru: "Установите приложение", en: "Install the app" },
              description: {
                ru: "Откройте App Store и установите клиент.",
                en: "Open the App Store and install the client.",
              },
              buttons: [
                {
                  type: "external",
                  link: "https://apps.apple.com/app/streisand/id6450534064",
                  text: { ru: "Открыть App Store", en: "Open App Store" },
                  svgIconKey: "Download",
                },
                {
                  type: "subscriptionLink",
                  link: "streisand://import/{{SUBSCRIPTION_LINK}}",
                  text: { ru: "Импортировать", en: "Import" },
                  svgIconKey: "App",
                },
                {
                  type: "copyButton",
                  link: "{{SUBSCRIPTION_LINK}}",
                  text: { ru: "Скопировать ссылку", en: "Copy link" },
                  svgIconKey: "Copy",
                },
              ],
            },
          ],
        },
      ],
    },
    android: {
      displayName: "Android",
      svgIconKey: "Phone",
      apps: [
        {
          name: "Happ",
          svgIconKey: "App",
          featured: true,
          blocks: [
            {
              svgIconKey: "Download",
              svgIconColor: "emerald",
              title: { ru: "Установите Happ", en: "Install Happ" },
              description: {
                ru: "Загрузите приложение и добавьте подписку по ссылке.",
                en: "Install the app and add the subscription link.",
              },
              buttons: [
                {
                  type: "external",
                  link: "https://play.google.com/store/apps/details?id=com.happproxy",
                  text: { ru: "Открыть Google Play", en: "Open Google Play" },
                  svgIconKey: "Download",
                },
                {
                  type: "copyButton",
                  link: "{{SUBSCRIPTION_LINK}}",
                  text: { ru: "Скопировать ссылку", en: "Copy link" },
                  svgIconKey: "Copy",
                },
              ],
            },
          ],
        },
      ],
    },
    windows: {
      displayName: "Windows",
      svgIconKey: "Desktop",
      apps: [
        {
          name: "Hiddify",
          svgIconKey: "Desktop",
          featured: true,
          blocks: [
            {
              svgIconKey: "Download",
              svgIconColor: "sky",
              title: { ru: "Установите клиент", en: "Install the client" },
              description: {
                ru: "Скачайте приложение и импортируйте ссылку подписки.",
                en: "Download the client and import the subscription link.",
              },
              buttons: [
                {
                  type: "external",
                  link: "https://github.com/hiddify/hiddify-app/releases",
                  text: { ru: "Открыть релизы", en: "Open releases" },
                  svgIconKey: "Download",
                },
                {
                  type: "copyButton",
                  link: "{{SUBSCRIPTION_LINK}}",
                  text: { ru: "Скопировать ссылку", en: "Copy link" },
                  svgIconKey: "Copy",
                },
              ],
            },
          ],
        },
      ],
    },
  },
};

export const DEV_MOCK = {
  config: {
    title: "/minishop",
    primaryColor: "#00fe7a",
    logoUrl: "/webapp-default-logo.webp",
    logoUseEmoji: false,
    logoEmoji: "🫥",
    logoEmojiFont: "system",
    faviconUrl: "/webapp-favicon/19b2a242e5b7bc2d/icon-180.png",
    faviconUseCustom: false,
    trialEnabled: true,
    trialDurationDays: 3,
    trialTrafficLimitGb: 5,
    trialTrafficStrategy: "NO_RESET",
    trialSquadUuids: "2f2f6e0a-1f2d-4e80-a33b-0ebf3a409012",
    apiBase: "/api",
    adminJsAsset: "subscription_webapp_admin.js",
    adminCssAsset: "subscription_webapp_admin.css",
    supportUrl: "https://t.me/support",
    privacyPolicyUrl: "https://example.com/privacy",
    userAgreementUrl: "https://example.com/agreement",
    currency: "RUB",
    language: "ru",
    languages: [
      { code: "ru", label: "Русский", flag: "🇷🇺", base: true },
      { code: "en", label: "English", flag: "🇬🇧", base: true },
    ],
    emailAuthEnabled: true,
    telegramLoginBotUsername: "preview_bot",
    telegramLoginBotId: 1234567890,
    telegramOAuthClientId: 1234567890,
    telegramOAuthRequestAccess: ["write"],
    appVersion: "dev+local",
    appRepositoryUrl: "https://github.com/3252a8/remnawave-minishop",
    themesCatalog: {
      default_theme: "dark",
      themes: [
        {
          key: "dark",
          names: { ru: "Тёмная", en: "Dark" },
          enabled: true,
          default: true,
          tokens: {
            color_scheme: "dark",
            accent: "#00fe7a",
            bg: "#03070b",
            panel: "#111820",
            text: "#f2f7f4",
            muted: "#a9b4b0",
          },
        },
        {
          key: "light",
          names: { ru: "Светлая", en: "Light" },
          enabled: true,
          default: false,
          css_file: "style.css",
          tokens: {
            color_scheme: "light",
          },
        },
        WINDOWS_95_THEME,
        ASCII_THEME,
      ],
    },
  },
  data: {
    ok: true,
    user: {
      id: 100200300,
      username: "username",
      email: "user@example.com",
      email_verified: true,
      password_auth_enabled: false,
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
      panel_short_uuid: "preview-token",
      install_share_token: "8f559061460e8fede78ef18dce887236",
      install_share_url: "https://app.example.com/s/8f559061460e8fede78ef18dce887236",
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
    subscription_guides: {
      ok: true,
      enabled: true,
      config: INSTALL_GUIDES_CONFIG,
      source: "mock",
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
      { id: "yookassa", name: "Карта", icon: "CreditCard" },
      { id: "platega_sbp", name: "Telegram Pay", icon: "CreditCard" },
      { id: "cryptopay", name: "Криптовалюта", icon: "Bitcoin" },
      { id: "freekassa", name: "Другие способы", icon: "Smartphone" },
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
    themes_catalog: {
      default_theme: "dark",
      themes: [
        {
          key: "dark",
          names: { ru: "Тёмная", en: "Dark" },
          enabled: true,
          tokens: {
            color_scheme: "dark",
            accent: "#00fe7a",
            bg: "#03070b",
            panel: "#111820",
            text: "#f2f7f4",
            muted: "#a9b4b0",
          },
        },
        {
          key: "light",
          names: { ru: "Светлая", en: "Light" },
          enabled: true,
          css_file: "style.css",
          tokens: {
            color_scheme: "light",
          },
        },
        WINDOWS_95_THEME,
        ASCII_THEME,
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
      subscription_purchase_description:
        "Покупая или продлевая подписку, вы получаете доступ к VPN/прокси-сервису, который помогает защищать ваше соединение и поддерживать стабильный доступ к сети.",
      subscription_guides_enabled: true,
      email_auth_enabled: true,
    },
  },
};

function applyDemoDataset() {
  const storedLanguage = readStoredDemoLanguage();
  const demoUser = {
    ...(DEMO_DATASET.currentUser || {}),
    id: DEMO_DATASET.currentUser?.id ?? DEMO_DATASET.currentUser?.user_id,
    language_code: storedLanguage || DEMO_DATASET.currentUser?.language_code || "ru",
  };

  Object.assign(DEV_MOCK.config, DEMO_DATASET.config || {});
  DEV_MOCK.config.language = demoUser.language_code || "ru";
  Object.assign(DEV_MOCK.data, {
    user: demoUser,
    subscription: DEMO_DATASET.currentSubscription || DEV_MOCK.data.subscription,
    devices: DEMO_DATASET.devices || DEV_MOCK.data.devices,
    plans: DEMO_DATASET.plans || DEV_MOCK.data.plans,
    payment_methods: DEMO_DATASET.paymentMethods || DEV_MOCK.data.payment_methods,
    referral: DEMO_DATASET.referral || DEV_MOCK.data.referral,
    tariff_change_options:
      DEMO_DATASET.tariff_change_options || DEV_MOCK.data.tariff_change_options,
    topup_options: DEMO_DATASET.topup_options || DEV_MOCK.data.topup_options,
    device_topup_options: DEMO_DATASET.device_topup_options || DEV_MOCK.data.device_topup_options,
    settings: {
      ...DEV_MOCK.data.settings,
      ...(DEMO_DATASET.webappSettings || {}),
    },
  });
}

applyDemoDataset();

function applyDemoTariffScenario(subscriptionPatch = {}) {
  DEV_MOCK.data.subscription = {
    ...DEV_MOCK.data.subscription,
    ...(DEMO_DATASET.currentSubscription || {}),
    ...subscriptionPatch,
    traffic_limit_strategy:
      subscriptionPatch.traffic_limit_strategy ||
      DEMO_DATASET.currentSubscription?.traffic_limit_strategy ||
      DEV_MOCK.data.subscription.traffic_limit_strategy ||
      "MONTH",
  };
  DEV_MOCK.data.plans = DEMO_DATASET.plans;
  DEV_MOCK.data.tariff_change_options =
    DEMO_DATASET.tariff_change_options || DEV_MOCK.data.tariff_change_options;
  DEV_MOCK.data.topup_options = DEMO_DATASET.topup_options || DEV_MOCK.data.topup_options;
  DEV_MOCK.data.device_topup_options =
    DEMO_DATASET.device_topup_options || DEV_MOCK.data.device_topup_options;
}

export function applyPreviewMock(kind) {
  const mode = String(kind || "")
    .trim()
    .toLowerCase();

  const themeKeys = new Set((DEV_MOCK.config.themesCatalog.themes || []).map((theme) => theme.key));
  if (themeKeys.has(mode)) {
    DEV_MOCK.config.themesCatalog.default_theme = mode;
    DEV_MOCK.data.themes_catalog.default_theme = mode;
    for (const theme of DEV_MOCK.config.themesCatalog.themes || []) {
      theme.default = theme.key === mode;
    }
    for (const theme of DEV_MOCK.data.themes_catalog.themes || []) {
      theme.default = theme.key === mode;
    }
    return;
  }

  if (mode === "guides" || mode === "install") {
    DEV_MOCK.data.settings.subscription_guides_enabled = true;
    DEV_MOCK.data.subscription_guides = {
      ...DEV_MOCK.data.subscription_guides,
      enabled: true,
      config: INSTALL_GUIDES_CONFIG,
    };
    return;
  }

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
      {
        months: 10,
        traffic_gb: 10,
        price: 199,
        currency: "RUB",
        title: "10 GB",
        sale_mode: "traffic",
      },
      {
        months: 50,
        traffic_gb: 50,
        price: 799,
        currency: "RUB",
        title: "50 GB",
        sale_mode: "traffic",
      },
      {
        months: 100,
        traffic_gb: 100,
        price: 1390,
        currency: "RUB",
        title: "100 GB",
        sale_mode: "traffic",
      },
      {
        months: 300,
        traffic_gb: 300,
        price: 3490,
        currency: "RUB",
        title: "300 GB",
        sale_mode: "traffic",
      },
    ];
  } else if (mode === "tariffs") {
    DEV_MOCK.data.settings.traffic_mode = false;
    if (DEMO_DATASET.plans?.length) {
      applyDemoTariffScenario();
      return;
    }
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
        tariff_description: "100 GB каждый месяц",
        billing_model: "period",
        months: 1,
        price: 150,
        currency: "RUB",
        title: "Стандарт",
        subtitle: "1 месяц",
        sale_mode: "subscription",
      },
      {
        id: "standard:period:3",
        tariff_key: "standard",
        tariff_name: "Стандарт",
        tariff_description: "100 GB каждый месяц",
        billing_model: "period",
        months: 3,
        price: 400,
        currency: "RUB",
        title: "Стандарт",
        subtitle: "3 месяца",
        sale_mode: "subscription",
      },
      {
        id: "business:period:1",
        tariff_key: "business",
        tariff_name: "Business",
        tariff_description: "500 GB и premium-серверы",
        billing_model: "period",
        months: 1,
        price: 690,
        currency: "RUB",
        title: "Business",
        subtitle: "1 месяц",
        sale_mode: "subscription",
      },
    ];
    DEV_MOCK.data.tariff_change_options = {
      ok: true,
      current: {
        tariff_key: "standard",
        title: "Стандарт",
        description: "100 GB каждый месяц",
        billing_model: "period",
        monthly_gb: 100,
        expires_at: "31.05.2026",
      },
      targets: [
        {
          tariff_key: "business",
          title: "Business",
          description: "500 GB и premium-серверы",
          billing_model: "period",
          monthly_gb: 500,
          price: 690,
          currency: "RUB",
          actions: [
            {
              mode: "recalc_days",
              kind: "free",
              title: "Пересчитать дни",
              days_after: 12,
              remaining_days: 28,
            },
            {
              mode: "paid_diff",
              kind: "payment",
              title: "Доплатить разницу",
              price: 240,
              currency: "RUB",
            },
          ],
        },
      ],
    };
    DEV_MOCK.data.topup_options = {
      ok: true,
      topup_kind: "regular",
      traffic_mode: false,
      tariff_key: "standard",
      regular: {
        can_topup: true,
        monthly_limit_gb: 100,
        used_gb: 86,
        available_gb: 14,
        packages: [
          { gb: 10, price: 99, currency: "RUB" },
          { gb: 50, price: 399, currency: "RUB" },
        ],
      },
      premium: {
        can_topup: true,
        monthly_limit_gb: 25,
        used_gb: 24,
        available_gb: 1,
        packages: [
          { gb: 10, price: 190, currency: "RUB" },
          { gb: 25, price: 390, currency: "RUB" },
        ],
      },
      plans: [
        {
          id: "standard:topup:10",
          tariff_key: "standard",
          tariff_name: "Стандарт",
          sale_mode: "topup",
          traffic_gb: 10,
          months: 10,
          price: 99,
          currency: "RUB",
          title: "10 GB",
          subtitle: "Стандарт",
        },
        {
          id: "standard:premium_topup:10",
          tariff_key: "standard",
          tariff_name: "Стандарт",
          sale_mode: "premium_topup",
          traffic_gb: 10,
          months: 10,
          price: 190,
          currency: "RUB",
          title: "Premium 10 GB",
          subtitle: "Стандарт",
        },
      ],
    };
    DEV_MOCK.data.device_topup_options = {
      ok: true,
      current_devices: 1,
      max_devices: 2,
      available_extra_devices: 3,
      packages: [
        { count: 1, price: 120, currency: "RUB" },
        { count: 3, price: 290, currency: "RUB" },
      ],
      plans: [
        {
          id: "standard:hwid:1",
          tariff_key: "standard",
          tariff_name: "Стандарт",
          sale_mode: "hwid_device",
          purchased_hwid_devices: 1,
          price: 120,
          currency: "RUB",
          title: "+1 устройство",
        },
      ],
    };
  } else if (mode === "depleted") {
    DEV_MOCK.data.settings.traffic_mode = false;
    DEV_MOCK.data.settings.trial_available = false;
    if (DEMO_DATASET.plans?.length) {
      const limitBytes = Number(DEMO_DATASET.currentSubscription?.traffic_limit_bytes || 0);
      applyDemoTariffScenario({
        traffic_used: DEMO_DATASET.currentSubscription?.traffic_limit || "150 GB",
        traffic_used_bytes: limitBytes,
      });
      return;
    }
    return;
  } else if (mode === "devices") {
    DEV_MOCK.data.settings.my_devices_enabled = true;
    DEV_MOCK.data.subscription = {
      ...DEV_MOCK.data.subscription,
      active: true,
      max_devices: 5,
      extra_hwid_devices: 2,
      extra_hwid_devices_valid_until_text: "01.06.2026 12:00",
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
