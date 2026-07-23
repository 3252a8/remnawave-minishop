import { DEMO_DATASET } from "../demoDataset.js";
import { withDemoAvatar } from "../demoAvatars.js";
import { readStoredDemoLanguage } from "../demoMockRuntime.js";
import { DEV_MOCK } from "./devMock";
import { INSTALL_GUIDES_CONFIG } from "./installGuidesConfig";
import type { PreviewThemesCatalog } from "./types";

// The generated dataset is treated as a loose record: scenario code probes
// optional fields that older snapshots may not carry.
type DemoDatasetShape = Record<string, unknown> & {
  config?: Record<string, unknown>;
  currentUser?: Record<string, unknown> | null;
  currentSubscription?: Record<string, unknown> | null;
  devices?: Record<string, unknown>;
  plans?: Record<string, unknown>[];
  paymentMethods?: Record<string, unknown>[];
  referral?: Record<string, unknown>;
  webappSettings?: Record<string, unknown>;
  tariff_change_options?: Record<string, unknown>;
  topup_options?: Record<string, unknown>;
  device_topup_options?: Record<string, unknown>;
};

const DATASET = DEMO_DATASET as unknown as DemoDatasetShape;

export function applyDemoDataset(): void {
  const storedLanguage = readStoredDemoLanguage();
  const demoUser = withDemoAvatar(
    {
      ...(DATASET.currentUser || {}),
      id: (DATASET.currentUser?.id ?? DATASET.currentUser?.user_id) as number | string | null,
      language_code: storedLanguage || DATASET.currentUser?.language_code || "ru",
      telegram_notifications_status:
        DATASET.currentUser?.telegram_notifications_status || "enabled",
      telegram_notifications_enabled: DATASET.currentUser?.telegram_notifications_enabled ?? true,
      telegram_notifications_need_prompt:
        DATASET.currentUser?.telegram_notifications_need_prompt ?? false,
      telegram_notifications_start_link:
        DATASET.currentUser?.telegram_notifications_start_link ||
        "https://t.me/preview_bot?start=notifications",
    },
    160
  );

  Object.assign(DEV_MOCK.config, DATASET.config || {});
  DEV_MOCK.config.language = String(demoUser?.language_code || "ru");
  Object.assign(DEV_MOCK.data, {
    user: demoUser,
    subscription: DATASET.currentSubscription || DEV_MOCK.data.subscription,
    devices: DATASET.devices || DEV_MOCK.data.devices,
    plans: DATASET.plans || DEV_MOCK.data.plans,
    payment_methods: DATASET.paymentMethods || DEV_MOCK.data.payment_methods,
    referral: DATASET.referral || DEV_MOCK.data.referral,
    tariff_change_options: DATASET.tariff_change_options || DEV_MOCK.data.tariff_change_options,
    topup_options: DATASET.topup_options || DEV_MOCK.data.topup_options,
    device_topup_options: DATASET.device_topup_options || DEV_MOCK.data.device_topup_options,
    settings: {
      ...DEV_MOCK.data.settings,
      ...(DATASET.webappSettings || {}),
    },
  });
}

function applyDemoTariffScenario(subscriptionPatch: Record<string, unknown> = {}): void {
  DEV_MOCK.data.subscription = {
    ...DEV_MOCK.data.subscription,
    ...(DATASET.currentSubscription || {}),
    ...subscriptionPatch,
    traffic_limit_strategy:
      subscriptionPatch.traffic_limit_strategy ||
      DATASET.currentSubscription?.traffic_limit_strategy ||
      DEV_MOCK.data.subscription.traffic_limit_strategy ||
      "MONTH",
  };
  DEV_MOCK.data.plans = DATASET.plans || [];
  DEV_MOCK.data.tariff_change_options =
    DATASET.tariff_change_options || DEV_MOCK.data.tariff_change_options;
  DEV_MOCK.data.topup_options = DATASET.topup_options || DEV_MOCK.data.topup_options;
  DEV_MOCK.data.device_topup_options =
    DATASET.device_topup_options || DEV_MOCK.data.device_topup_options;
}

function applyInactiveSubscriptionScenario({ trialAvailable = false } = {}): void {
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
  DEV_MOCK.data.plans = DATASET.plans || DEV_MOCK.data.plans;
  DEV_MOCK.data.tariff_change_options =
    DATASET.tariff_change_options || DEV_MOCK.data.tariff_change_options;
}

type EmailOnlyAccountPatch = {
  email?: string;
  referredById?: number | null;
};

function applyEmailOnlyAccountPatch({
  email = "preview-user@mailinator.com",
  referredById = null,
}: EmailOnlyAccountPatch = {}): void {
  DEV_MOCK.data.user = {
    ...(DEV_MOCK.data.user || {}),
    telegram_id: null,
    telegram_linked: false,
    email,
    email_verified: true,
    referred_by_id: referredById,
  };
}

function applyPreviewThemeToCatalog(
  catalog: PreviewThemesCatalog | null | undefined,
  themeKey: string,
  variant: string | null
): void {
  if (!catalog) return;
  catalog.default_theme = themeKey;
  for (const theme of catalog.themes || []) {
    const isDefaultTheme = theme.key === themeKey;
    theme.default = isDefaultTheme;
    if (isDefaultTheme && variant && theme.variants?.[variant]) {
      theme.active_variant = variant;
      theme.tokens = {
        ...(theme.tokens || {}),
        ...(theme.variants[variant] || {}),
      };
    }
  }
}

export function applyPreviewMock(kind: unknown): void {
  const mode = String(kind || "")
    .trim()
    .toLowerCase();

  const previewTheme = (DEV_MOCK.config.themesCatalog.themes || []).find(
    (theme) => theme.key === mode
  );
  if (previewTheme) {
    const themeKey = previewTheme.variant_alias_for || previewTheme.key;
    const variant = previewTheme.variant_alias_for
      ? previewTheme.active_variant || String(previewTheme.tokens?.color_scheme || "") || mode
      : previewTheme.active_variant || String(previewTheme.tokens?.color_scheme || "") || null;
    applyPreviewThemeToCatalog(DEV_MOCK.config.themesCatalog, themeKey, variant);
    applyPreviewThemeToCatalog(DEV_MOCK.data.themes_catalog, themeKey, variant);
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
    if (DATASET.plans?.length) {
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
  } else if (
    mode === "auto-renew" ||
    mode === "autorenew" ||
    mode === "recurring" ||
    mode === "subscription-auto-renew"
  ) {
    DEV_MOCK.data.settings.traffic_mode = false;
    applyDemoTariffScenario({
      auto_renew_enabled: true,
      auto_renew_available: true,
      auto_renew_can_enable: true,
      auto_renew_provider_label: "CloudPayments",
      provider: "cloudpayments",
    });
  } else if (mode === "depleted") {
    DEV_MOCK.data.settings.traffic_mode = false;
    DEV_MOCK.data.settings.trial_available = false;
    if (DATASET.plans?.length) {
      const limitBytes = Number(DATASET.currentSubscription?.traffic_limit_bytes || 0);
      applyDemoTariffScenario({
        traffic_used: DATASET.currentSubscription?.traffic_limit || "150 GB",
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
          traffic_bonus_gb: 15,
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
          traffic_bonus_gb: 45,
        },
      ],
    };
  } else if (mode === "trial") {
    applyInactiveSubscriptionScenario({ trialAvailable: true });
  }
}
