import { DEMO_DATASET } from "./demoDataset.js";
import { withDemoAvatar } from "./demoAvatars.js";

const DEMO_LANGUAGE_STORAGE_KEY = "rw_minishop_demo_language";
const DEFAULT_DISPOSABLE_EMAIL_DOMAINS = [
  "10minutemail.com",
  "10minutemail.net",
  "10minutemail.org",
  "20minutemail.com",
  "33mail.com",
  "anonbox.net",
  "anonymbox.com",
  "armyspy.com",
  "byom.de",
  "crazymailing.com",
  "cuvox.de",
  "dayrep.com",
  "deadaddress.com",
  "dispostable.com",
  "dodgeit.com",
  "dodgit.com",
  "dropmail.me",
  "easytrashmail.com",
  "emailfake.com",
  "emailondeck.com",
  "emailtemporanea.com",
  "emailtemporanea.net",
  "einrot.com",
  "fakeinbox.com",
  "filzmail.com",
  "fleckens.hu",
  "generator.email",
  "getairmail.com",
  "getnada.com",
  "grr.la",
  "guerrillamail.biz",
  "guerrillamail.com",
  "guerrillamail.de",
  "guerrillamail.info",
  "guerrillamail.net",
  "guerrillamail.org",
  "guerrillamailblock.com",
  "gustr.com",
  "hmamail.com",
  "incognitomail.org",
  "inboxbear.com",
  "jetable.org",
  "jourrapide.com",
  "kasmail.com",
  "mail-temp.com",
  "mailcatch.com",
  "maildrop.cc",
  "mailexpire.com",
  "mailinator.com",
  "mailinator.net",
  "mailinator.org",
  "mailmetrash.com",
  "mailnesia.com",
  "mailnull.com",
  "mailpoof.com",
  "mailtothis.com",
  "mail.tm",
  "mintemail.com",
  "mohmal.com",
  "moakt.com",
  "mytemp.email",
  "mytrashmail.com",
  "nada.email",
  "no-spam.ws",
  "pookmail.com",
  "rhyta.com",
  "sharklasers.com",
  "sofort-mail.de",
  "spam4.me",
  "spambog.com",
  "spamdecoy.net",
  "spamfree24.org",
  "spamgourmet.com",
  "spamhole.com",
  "spam.la",
  "spammotel.com",
  "superrito.com",
  "teleworm.us",
  "tempail.com",
  "temp-mail.io",
  "temp-mail.org",
  "tempmail.com",
  "tempmail.dev",
  "tempmail.net",
  "tempmailo.com",
  "temporaryemail.net",
  "temporary-mail.net",
  "tempr.email",
  "throwawaymail.com",
  "trash-mail.com",
  "trash-mail.de",
  "trashmail.com",
  "trashmail.me",
  "trashmail.net",
  "trashmailer.com",
  "trashymail.com",
  "weg-werf-email.de",
  "wegwerfmail.de",
  "wegwerfmail.net",
  "wegwerfmail.org",
  "yomail.info",
  "yopmail.com",
  "yopmail.fr",
  "yopmail.net",
].join("\n");

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
    faviconUrl: "/webapp-favicon/19b2a242e5b7bc2d/icon-180.png",
    faviconUseCustom: false,
    trialEnabled: true,
    trialDurationDays: 3,
    trialTrafficLimitGb: 5,
    trialTrafficStrategy: "NO_RESET",
    trialWithoutTelegramEnabled: true,
    trialSquadUuids: "2f2f6e0a-1f2d-4e80-a33b-0ebf3a409012",
    referralWelcomeBonusDays: 3,
    referralWelcomeWithoutTelegramEnabled: true,
    referralOneBonusPerReferee: false,
    legacyRefs: true,
    disposableEmailDomains: DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
    apiBase: "/api",
    adminJsAsset: "subscription_webapp_admin.js",
    adminCssAsset: "subscription_webapp_admin.css",
    supportUrl: "https://t.me/support",
    serverStatusUrl: "https://status.example.com",
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
    appRepositoryUrl: "https://minishop.minidoc.cc/",
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
      telegram_notifications_status: "enabled",
      telegram_notifications_enabled: true,
      telegram_notifications_need_prompt: false,
      telegram_notifications_start_link: "https://t.me/preview_bot?start=notifications",
      telegram_photo_url: "",
      first_name: "Preview",
      language_code: "ru",
      is_admin: true,
    },
    auth_demo: {
      enabled: false,
      email: "3252a8@proton.me",
      code: "123456",
      password: "demo-password",
      telegram_id: 7410865527,
      telegram_username: "u3252a8",
      telegram_first_name: "3252a8",
      telegram_last_name: "",
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
      auto_renew_enabled: true,
      auto_renew_available: true,
      auto_renew_can_enable: true,
      auto_renew_provider_label: "CloudPayments",
      provider: "cloudpayments",
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
      { id: "cloudpayments", name: "CloudPayments", icon: "CreditCard" },
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
      welcome_bonus_without_telegram_enabled: true,
      welcome_bonus_requires_telegram: false,
      welcome_bonus_block_reason: "",
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
      trial_without_telegram_enabled: true,
      trial_requires_telegram: false,
      trial_block_reason: "",
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
  const demoUser = withDemoAvatar(
    {
      ...(DEMO_DATASET.currentUser || {}),
      id: DEMO_DATASET.currentUser?.id ?? DEMO_DATASET.currentUser?.user_id,
      language_code: storedLanguage || DEMO_DATASET.currentUser?.language_code || "ru",
      telegram_notifications_status:
        DEMO_DATASET.currentUser?.telegram_notifications_status || "enabled",
      telegram_notifications_enabled:
        DEMO_DATASET.currentUser?.telegram_notifications_enabled ?? true,
      telegram_notifications_need_prompt:
        DEMO_DATASET.currentUser?.telegram_notifications_need_prompt ?? false,
      telegram_notifications_start_link:
        DEMO_DATASET.currentUser?.telegram_notifications_start_link ||
        "https://t.me/preview_bot?start=notifications",
    },
    160
  );

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

function applyInactiveSubscriptionScenario({ trialAvailable = false } = {}) {
  DEV_MOCK.data.settings.traffic_mode = false;
  DEV_MOCK.data.settings.trial_enabled = true;
  DEV_MOCK.data.settings.trial_available = Boolean(trialAvailable);
  DEV_MOCK.data.settings.trial_requires_telegram = false;
  DEV_MOCK.data.settings.trial_block_reason = "";
  DEV_MOCK.data.settings.trial_duration_days = 5;
  DEV_MOCK.data.settings.trial_traffic_limit_gb = 10;
  DEV_MOCK.data.subscription = {
    ...DEV_MOCK.data.subscription,
    active: false,
    status: "INACTIVE",
    remaining_text: "Подписка не активна",
    end_date_text: "",
    days_left: 0,
    config_link: null,
    connect_url: null,
    panel_short_uuid: "",
    install_share_token: "",
    install_share_url: "",
    traffic_used: "0 B",
    traffic_limit: "0 GB",
    traffic_used_bytes: 0,
    traffic_limit_bytes: 0,
    premium_used_bytes: 0,
    premium_limit_bytes: 0,
    premium_is_limited: false,
  };
  DEV_MOCK.data.settings.my_devices_enabled = true;
  DEV_MOCK.data.devices = {
    ok: true,
    enabled: true,
    current_devices: 0,
    max_devices: 0,
    max_devices_label: "∞",
    devices: [],
  };
  DEV_MOCK.data.plans = DEMO_DATASET.plans || DEV_MOCK.data.plans;
  DEV_MOCK.data.tariff_change_options =
    DEMO_DATASET.tariff_change_options || DEV_MOCK.data.tariff_change_options;
}

function applyEmailOnlyAccountPatch({
  email = "preview-user@mailinator.com",
  referredById = null,
} = {}) {
  DEV_MOCK.data.user = {
    ...(DEV_MOCK.data.user || {}),
    telegram_id: null,
    telegram_linked: false,
    email,
    email_verified: true,
    referred_by_id: referredById,
  };
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

  if (mode === "auth" || mode === "login" || mode === "register") {
    DEV_MOCK.data.auth_demo = {
      ...(DEV_MOCK.data.auth_demo || {}),
      enabled: true,
      email: "3252a8@proton.me",
      code: "123456",
      password: "demo-password",
      telegram_id: 7410865527,
      telegram_username: "u3252a8",
      telegram_first_name: "3252a8",
      telegram_last_name: "",
    };
    DEV_MOCK.data.settings.email_auth_enabled = true;
    DEV_MOCK.data.settings.trial_enabled = true;
    DEV_MOCK.data.settings.trial_available = true;
    return;
  }

  if (mode === "trial-telegram" || mode === "trial_requires_telegram") {
    applyInactiveSubscriptionScenario();
    applyEmailOnlyAccountPatch({ email: "trial-user@mailinator.com" });
    DEV_MOCK.data.settings.trial_enabled = true;
    DEV_MOCK.data.settings.trial_available = false;
    DEV_MOCK.data.settings.trial_requires_telegram = true;
    DEV_MOCK.data.settings.trial_block_reason = "telegram_required";
    DEV_MOCK.data.referral = {
      ...(DEV_MOCK.data.referral || {}),
      welcome_bonus_days: 3,
      welcome_bonus_requires_telegram: false,
      welcome_bonus_block_reason: "",
    };
    return;
  }

  if (
    mode === "referral-telegram" ||
    mode === "referral_welcome_telegram" ||
    mode === "referral-welcome-telegram"
  ) {
    applyInactiveSubscriptionScenario();
    applyEmailOnlyAccountPatch({
      email: "referral-user@mailinator.com",
      referredById: 910001,
    });
    DEV_MOCK.data.settings.trial_enabled = true;
    DEV_MOCK.data.settings.trial_available = false;
    DEV_MOCK.data.settings.trial_requires_telegram = false;
    DEV_MOCK.data.settings.trial_block_reason = "";
    DEV_MOCK.data.referral = {
      ...(DEV_MOCK.data.referral || {}),
      welcome_bonus_days: 3,
      welcome_bonus_without_telegram_enabled: false,
      welcome_bonus_requires_telegram: true,
      welcome_bonus_block_reason: "telegram_required",
    };
    return;
  }

  if (mode === "notifications" || mode === "telegram-notifications" || mode === "needs-bot") {
    DEV_MOCK.data.user = {
      ...(DEV_MOCK.data.user || {}),
      telegram_linked: true,
      telegram_notifications_status: "needs_start",
      telegram_notifications_enabled: false,
      telegram_notifications_need_prompt: true,
      telegram_notifications_start_link: "https://t.me/preview_bot?start=notifications",
    };
    return;
  }

  if (mode === "notifications-blocked") {
    DEV_MOCK.data.user = {
      ...(DEV_MOCK.data.user || {}),
      telegram_linked: true,
      telegram_notifications_status: "blocked",
      telegram_notifications_enabled: false,
      telegram_notifications_need_prompt: true,
      telegram_notifications_start_link: "https://t.me/preview_bot?start=notifications",
    };
    return;
  }

  if (mode === "tariffs") {
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
  } else if (mode === "no-subscription" || mode === "inactive") {
    applyInactiveSubscriptionScenario();
  } else if (mode === "devices") {
    const baseDevices = DEV_MOCK.data.devices || {};
    const baseList = Array.isArray(baseDevices.devices) ? baseDevices.devices : [];
    const devices = [
      ...baseList,
      {
        display_name: "iPad Pro",
        platform_label: "iPadOS 18.4",
        user_agent: "Streisand/1.6 CFNetwork",
        created_at_text: "18.05.2026 12:30",
        hwid_short: "D3MOIPAD...7712AA",
        token: "demo-device-ipad",
        can_disconnect: true,
      },
      {
        display_name: "Windows Laptop",
        platform_label: "Windows 11",
        user_agent: "Hiddify/2.5.7",
        created_at_text: "21.05.2026 19:45",
        hwid_short: "D3MOWIN...50CC91",
        token: "demo-device-windows",
        can_disconnect: true,
      },
    ]
      .slice(0, 5)
      .map((device, index) => ({ ...device, index: index + 1 }));
    DEV_MOCK.data.settings.my_devices_enabled = true;
    DEV_MOCK.data.devices = {
      ...baseDevices,
      ok: true,
      enabled: true,
      current_devices: 5,
      max_devices: 5,
      max_devices_label: "5",
      devices,
    };
    DEV_MOCK.data.subscription = {
      ...DEV_MOCK.data.subscription,
      active: true,
      max_devices: 5,
      can_topup_devices: true,
      extra_hwid_devices: 0,
      extra_hwid_devices_valid_until_text: "",
    };
    DEV_MOCK.data.device_topup_options = {
      ok: true,
      enabled: true,
      tariff_key: "standard",
      tariff_name: "Стандарт",
      current_limit: 5,
      current_devices: 5,
      max_devices: 5,
      available_extra_devices: 3,
      extra_hwid_devices: 0,
      extra_hwid_devices_valid_until_text: "",
      renewal_available: false,
      renewal_recommended_count: 0,
      plans: [
        {
          id: "standard:hwid:1",
          tariff_key: "standard",
          tariff_name: "Стандарт",
          sale_mode: "hwid_devices",
          purchased_hwid_devices: 1,
          price: 120,
          currency: "RUB",
          title: "+1 устройство",
          subtitle: "Стандарт",
          device_count: 1,
        },
        {
          id: "standard:hwid:3",
          tariff_key: "standard",
          tariff_name: "Стандарт",
          sale_mode: "hwid_devices",
          purchased_hwid_devices: 3,
          price: 290,
          currency: "RUB",
          title: "+3 устройства",
          subtitle: "Стандарт",
          device_count: 3,
        },
      ],
    };
  } else if (mode === "trial") {
    applyInactiveSubscriptionScenario({ trialAvailable: true });
  }
}
