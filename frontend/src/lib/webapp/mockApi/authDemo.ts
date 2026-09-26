import { DEV_MOCK } from "../previewMock.js";
import { withDemoAvatar } from "../demoAvatars.js";
import { DATASET, defaultClone, type DemoRecord } from "./dataset";

export const DEFAULT_DEMO_AUTH_EMAIL = "3252a8@proton.me";
export const DEFAULT_DEMO_AUTH_CODE = "123456";
export const DEFAULT_DEMO_AUTH_PASSWORD = "demo-password";
const DEFAULT_DEMO_AUTH_TELEGRAM_ID = 7410865527;
const DEFAULT_DEMO_AUTH_TELEGRAM_USERNAME = "u3252a8";
const DEFAULT_DEMO_AUTH_TELEGRAM_FIRST_NAME = "3252a8";
const DEFAULT_DEMO_AUTH_TELEGRAM_LAST_NAME = "";

type DemoAuthConfig = DemoRecord & {
  email?: string;
  code?: string;
  password?: string;
  telegram_id?: number | string;
  telegram_username?: string;
  telegram_first_name?: string;
  telegram_last_name?: string;
};

type TelegramAuthData = DemoRecord & {
  id?: number | string;
  username?: string;
  first_name?: string;
  last_name?: string;
};

function scalarIdentity(value: unknown): string | number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value) return value;
  return undefined;
}

function identityFrom(
  record: DemoRecord | null | undefined,
  preferredKey: "id" | "user_id",
  fallbackKey: "id" | "user_id"
): string | number | undefined {
  return scalarIdentity(record?.[preferredKey]) || scalarIdentity(record?.[fallbackKey]);
}

export function demoAuthConfig(): DemoAuthConfig {
  return {
    email: DEFAULT_DEMO_AUTH_EMAIL,
    code: DEFAULT_DEMO_AUTH_CODE,
    password: DEFAULT_DEMO_AUTH_PASSWORD,
    ...(DEV_MOCK.data.auth_demo || {}),
  };
}

export function applyDemoEmailAuthUser(): void {
  const normalizedEmail = String(demoAuthConfig().email || DEFAULT_DEMO_AUTH_EMAIL)
    .trim()
    .toLowerCase();
  const language = DEV_MOCK.data.user?.language_code || DEV_MOCK.config.language || "ru";
  const sourceId =
    identityFrom(DATASET.currentUser, "id", "user_id") ||
    identityFrom(DEV_MOCK.data.user, "id", "user_id") ||
    910001;
  const sourceUserId =
    identityFrom(DATASET.currentUser, "user_id", "id") ||
    identityFrom(DEV_MOCK.data.user, "user_id", "id") ||
    910001;
  DEV_MOCK.data.user = withDemoAvatar(
    {
      ...(DATASET.currentUser || DEV_MOCK.data.user || {}),
      id: sourceId,
      user_id: sourceUserId,
      telegram_id: null,
      telegram_linked: false,
      telegram_notifications_status: "unknown",
      telegram_notifications_enabled: false,
      telegram_notifications_need_prompt: false,
      telegram_notifications_start_link: "https://t.me/preview_bot?start=notifications",
      telegram_photo_url: "",
      avatar_url: "",
      username: DATASET.currentUser?.username || "u3252a8",
      first_name: DATASET.currentUser?.first_name || "3252a8",
      last_name: DATASET.currentUser?.last_name || "",
      email: normalizedEmail,
      email_verified: true,
      password_auth_enabled: true,
      is_admin: true,
      language_code: language,
      registration_date: DATASET.currentUser?.registration_date || "2025-10-16T11:59:50Z",
      panel_status: DATASET.currentUser?.panel_status || "active",
    },
    160
  ) as DemoRecord;
  DEV_MOCK.data.subscription = {
    ...(DEV_MOCK.data.subscription || {}),
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
    traffic_used_bytes: 0,
    traffic_limit: "0 B",
    traffic_limit_bytes: 0,
    premium_used: "0 B",
    premium_used_bytes: 0,
    premium_limit: "0 B",
    premium_limit_bytes: 0,
    can_topup_regular_traffic: false,
    can_topup_premium_traffic: false,
    can_topup_devices: false,
    extra_hwid_devices: 0,
    max_devices: 0,
  };
  if (DATASET.currentSubscription) {
    DEV_MOCK.data.subscription = defaultClone(DATASET.currentSubscription);
  }
  DEV_MOCK.data.settings = {
    ...(DEV_MOCK.data.settings || {}),
    trial_enabled: true,
    trial_available: true,
    trial_without_oauth_enabled: true,
    trial_requires_oauth: false,
    trial_without_telegram_enabled: true,
    trial_requires_telegram: false,
    trial_block_reason: "",
  };
}

export function applyDemoTelegramAuthUser(authData: TelegramAuthData = {}): void {
  const authDemo = demoAuthConfig();
  const adminUser = DATASET.currentUser || {};
  const telegramId = Number(authData.id || authDemo.telegram_id || DEFAULT_DEMO_AUTH_TELEGRAM_ID);
  const username =
    authData.username ||
    authDemo.telegram_username ||
    adminUser.username ||
    DEFAULT_DEMO_AUTH_TELEGRAM_USERNAME;
  const firstName =
    authData.first_name ||
    authDemo.telegram_first_name ||
    adminUser.first_name ||
    DEFAULT_DEMO_AUTH_TELEGRAM_FIRST_NAME;
  const lastName =
    authData.last_name ||
    authDemo.telegram_last_name ||
    adminUser.last_name ||
    DEFAULT_DEMO_AUTH_TELEGRAM_LAST_NAME;
  const language = DEV_MOCK.data.user?.language_code || DEV_MOCK.config.language || "ru";
  const adminId = identityFrom(adminUser, "id", "user_id") || 910001;
  const adminUserId = identityFrom(adminUser, "user_id", "id") || 910001;
  DEV_MOCK.data.user = withDemoAvatar(
    {
      ...(DATASET.currentUser || DEV_MOCK.data.user || {}),
      id: adminId,
      user_id: adminUserId,
      telegram_id: telegramId,
      telegram_linked: true,
      telegram_notifications_status: "needs_start",
      telegram_notifications_enabled: false,
      telegram_notifications_need_prompt: true,
      telegram_notifications_start_link: "https://t.me/preview_bot?start=notifications",
      username,
      first_name: firstName,
      last_name: lastName,
      email: "",
      email_verified: false,
      password_auth_enabled: false,
      is_admin: true,
      language_code: language,
      registration_date: adminUser.registration_date || "2025-10-16T11:59:50Z",
      panel_status: adminUser.panel_status || "active",
    },
    160
  ) as DemoRecord;
  DEV_MOCK.data.subscription = {
    ...(DEV_MOCK.data.subscription || {}),
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
    traffic_used_bytes: 0,
    traffic_limit: "0 B",
    traffic_limit_bytes: 0,
    premium_used: "0 B",
    premium_used_bytes: 0,
    premium_limit: "0 B",
    premium_limit_bytes: 0,
    can_topup_regular_traffic: false,
    can_topup_premium_traffic: false,
    can_topup_devices: false,
    extra_hwid_devices: 0,
    max_devices: 0,
  };
  if (DATASET.currentSubscription) {
    DEV_MOCK.data.subscription = defaultClone(DATASET.currentSubscription);
  }
  DEV_MOCK.data.settings = {
    ...(DEV_MOCK.data.settings || {}),
    trial_enabled: true,
    trial_available: true,
    trial_without_oauth_enabled: true,
    trial_requires_oauth: false,
    trial_without_telegram_enabled: true,
    trial_requires_telegram: false,
    trial_block_reason: "",
  };
}

export function applyDemoEmailLink(email: unknown): void {
  const normalizedEmail = String(email || demoAuthConfig().email || DEFAULT_DEMO_AUTH_EMAIL)
    .trim()
    .toLowerCase();
  DEV_MOCK.data.user = withDemoAvatar(
    {
      ...(DEV_MOCK.data.user || DATASET.currentUser || {}),
      id:
        identityFrom(DEV_MOCK.data.user, "id", "user_id") ||
        identityFrom(DATASET.currentUser, "id", "user_id") ||
        910001,
      user_id:
        identityFrom(DEV_MOCK.data.user, "user_id", "id") ||
        identityFrom(DATASET.currentUser, "user_id", "id") ||
        910001,
      email: normalizedEmail,
      email_verified: true,
      is_admin: true,
    },
    160
  ) as DemoRecord;
  DEV_MOCK.data.settings = {
    ...(DEV_MOCK.data.settings || {}),
    trial_requires_oauth: false,
    trial_requires_telegram: false,
    trial_block_reason: "",
  };
  DEV_MOCK.data.referral = {
    ...(DEV_MOCK.data.referral || {}),
    welcome_bonus_requires_telegram: false,
    welcome_bonus_block_reason: "",
  };
}

export function applyDemoTelegramLink(authData: TelegramAuthData = {}): void {
  const authDemo = demoAuthConfig();
  const adminUser = DATASET.currentUser || {};
  const telegramId = Number(authData.id || authDemo.telegram_id || DEFAULT_DEMO_AUTH_TELEGRAM_ID);
  DEV_MOCK.data.user = withDemoAvatar(
    {
      ...(DEV_MOCK.data.user || adminUser || {}),
      id:
        identityFrom(DEV_MOCK.data.user, "id", "user_id") ||
        identityFrom(adminUser, "id", "user_id") ||
        910001,
      user_id:
        identityFrom(DEV_MOCK.data.user, "user_id", "id") ||
        identityFrom(adminUser, "user_id", "id") ||
        910001,
      telegram_id: telegramId,
      telegram_linked: true,
      telegram_notifications_status: "needs_start",
      telegram_notifications_enabled: false,
      telegram_notifications_need_prompt: true,
      telegram_notifications_start_link: "https://t.me/preview_bot?start=notifications",
      username:
        authData.username ||
        authDemo.telegram_username ||
        adminUser.username ||
        DEFAULT_DEMO_AUTH_TELEGRAM_USERNAME,
      first_name:
        authData.first_name ||
        authDemo.telegram_first_name ||
        adminUser.first_name ||
        DEFAULT_DEMO_AUTH_TELEGRAM_FIRST_NAME,
      last_name:
        authData.last_name ||
        authDemo.telegram_last_name ||
        adminUser.last_name ||
        DEFAULT_DEMO_AUTH_TELEGRAM_LAST_NAME,
      is_admin: true,
    },
    160
  ) as DemoRecord;
}
