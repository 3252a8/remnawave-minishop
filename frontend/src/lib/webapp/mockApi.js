import { DEV_MOCK } from "./previewMock.js";
import { DEMO_DATASET } from "./demoDataset.js";
import SETTINGS_MANIFEST_SECTIONS from "./settingsManifest.generated.json";
import { withDemoAvatar, withDemoAvatarDetail, withDemoAvatarTicket } from "./demoAvatars.js";

const DEMO_LANGUAGE_STORAGE_KEY = "rw_minishop_demo_language";

function defaultClone(value) {
  try {
    return structuredClone(value);
  } catch {
    return JSON.parse(JSON.stringify(value));
  }
}

let demoPromosState = null;
let demoAdsState = null;
let demoSupportTicketsState = null;
let demoSupportMessagesState = null;
let demoTariffsState = null;
let demoPaymentSequence = 20000;
const demoSettingsChanges = new Map();
const demoPaymentStatuses = new Map();
const deviceTopupSaleModes = new Set(["hwid_device", "hwid_devices", "hwid_devices_renewal"]);
const DEFAULT_DEMO_AUTH_EMAIL = "3252a8@proton.me";
const DEFAULT_DEMO_AUTH_CODE = "123456";
const DEFAULT_DEMO_AUTH_PASSWORD = "demo-password";
const DEFAULT_DEMO_AUTH_TELEGRAM_ID = 7410865527;
const DEFAULT_DEMO_AUTH_TELEGRAM_USERNAME = "u3252a8";
const DEFAULT_DEMO_AUTH_TELEGRAM_FIRST_NAME = "3252a8";
const DEFAULT_DEMO_AUTH_TELEGRAM_LAST_NAME = "";

function demoPromos() {
  if (!demoPromosState) demoPromosState = defaultClone(DEMO_DATASET.promos || []);
  return demoPromosState;
}

function demoAds() {
  if (!demoAdsState) demoAdsState = defaultClone(DEMO_DATASET.ads || []);
  return demoAdsState;
}

function demoSupportTickets() {
  if (!demoSupportTicketsState) {
    demoSupportTicketsState = defaultClone(DEMO_DATASET.supportTickets || []);
  }
  return demoSupportTicketsState;
}

function demoSupportMessages() {
  if (!demoSupportMessagesState) {
    demoSupportMessagesState = defaultClone(DEMO_DATASET.supportMessages || {});
  }
  return demoSupportMessagesState;
}

function demoTariffs() {
  if (!demoTariffsState) {
    demoTariffsState = defaultClone(
      DEMO_DATASET.tariffsCatalog || {
        default_tariff: "",
        topup_packages_default: { rub: [], stars: [] },
        tariffs: [],
      }
    );
  }
  return demoTariffsState;
}

function queryParams(path) {
  return new URLSearchParams(String(path || "").split("?")[1] || "");
}

function jsonBody(options) {
  try {
    return options?.body ? JSON.parse(String(options.body)) : {};
  } catch {
    return {};
  }
}

function isDeviceTopupSaleMode(value) {
  return deviceTopupSaleModes.has(String(value || "").toLowerCase());
}

function demoAuthConfig() {
  return {
    email: DEFAULT_DEMO_AUTH_EMAIL,
    code: DEFAULT_DEMO_AUTH_CODE,
    password: DEFAULT_DEMO_AUTH_PASSWORD,
    ...(DEV_MOCK.data.auth_demo || {}),
  };
}

function applyDemoEmailAuthUser() {
  const normalizedEmail = String(demoAuthConfig().email || DEFAULT_DEMO_AUTH_EMAIL)
    .trim()
    .toLowerCase();
  const language = DEV_MOCK.data.user?.language_code || DEV_MOCK.config.language || "ru";
  DEV_MOCK.data.user = withDemoAvatar(
    {
      ...(DEMO_DATASET.currentUser || DEV_MOCK.data.user || {}),
      id: DEMO_DATASET.currentUser?.id || DEMO_DATASET.currentUser?.user_id || 910001,
      user_id: DEMO_DATASET.currentUser?.user_id || DEMO_DATASET.currentUser?.id || 910001,
      telegram_id: null,
      telegram_linked: false,
      telegram_notifications_status: "unknown",
      telegram_notifications_enabled: false,
      telegram_notifications_need_prompt: false,
      telegram_notifications_start_link: "https://t.me/preview_bot?start=notifications",
      telegram_photo_url: "",
      avatar_url: "",
      username: DEMO_DATASET.currentUser?.username || "u3252a8",
      first_name: DEMO_DATASET.currentUser?.first_name || "3252a8",
      last_name: DEMO_DATASET.currentUser?.last_name || "",
      email: normalizedEmail,
      email_verified: true,
      password_auth_enabled: true,
      is_admin: true,
      language_code: language,
      registration_date: DEMO_DATASET.currentUser?.registration_date || "2025-10-16T11:59:50Z",
      panel_status: DEMO_DATASET.currentUser?.panel_status || "active",
    },
    160
  );
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
  if (DEMO_DATASET.currentSubscription) {
    DEV_MOCK.data.subscription = defaultClone(DEMO_DATASET.currentSubscription);
  }
  DEV_MOCK.data.settings = {
    ...(DEV_MOCK.data.settings || {}),
    trial_enabled: true,
    trial_available: true,
    trial_without_telegram_enabled: true,
    trial_requires_telegram: false,
    trial_block_reason: "",
  };
}

function applyDemoTelegramAuthUser(authData = {}) {
  const authDemo = demoAuthConfig();
  const adminUser = DEMO_DATASET.currentUser || {};
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
  DEV_MOCK.data.user = withDemoAvatar(
    {
      ...(DEMO_DATASET.currentUser || DEV_MOCK.data.user || {}),
      id: adminUser.id || adminUser.user_id || 910001,
      user_id: adminUser.user_id || adminUser.id || 910001,
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
  );
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
  if (DEMO_DATASET.currentSubscription) {
    DEV_MOCK.data.subscription = defaultClone(DEMO_DATASET.currentSubscription);
  }
  DEV_MOCK.data.settings = {
    ...(DEV_MOCK.data.settings || {}),
    trial_enabled: true,
    trial_available: true,
    trial_without_telegram_enabled: true,
    trial_requires_telegram: false,
    trial_block_reason: "",
  };
}

function applyDemoEmailLink(email) {
  const normalizedEmail = String(email || demoAuthConfig().email || DEFAULT_DEMO_AUTH_EMAIL)
    .trim()
    .toLowerCase();
  DEV_MOCK.data.user = withDemoAvatar(
    {
      ...(DEV_MOCK.data.user || DEMO_DATASET.currentUser || {}),
      id: DEV_MOCK.data.user?.id || DEV_MOCK.data.user?.user_id || 910001,
      user_id: DEV_MOCK.data.user?.user_id || DEV_MOCK.data.user?.id || 910001,
      email: normalizedEmail,
      email_verified: true,
      is_admin: true,
    },
    160
  );
  DEV_MOCK.data.settings = {
    ...(DEV_MOCK.data.settings || {}),
    trial_requires_telegram: false,
    trial_block_reason: "",
  };
  DEV_MOCK.data.referral = {
    ...(DEV_MOCK.data.referral || {}),
    welcome_bonus_requires_telegram: false,
    welcome_bonus_block_reason: "",
  };
}

function applyDemoTelegramLink(authData = {}) {
  const authDemo = demoAuthConfig();
  const adminUser = DEMO_DATASET.currentUser || {};
  const telegramId = Number(authData.id || authDemo.telegram_id || DEFAULT_DEMO_AUTH_TELEGRAM_ID);
  DEV_MOCK.data.user = withDemoAvatar(
    {
      ...(DEV_MOCK.data.user || adminUser || {}),
      id: DEV_MOCK.data.user?.id || DEV_MOCK.data.user?.user_id || 910001,
      user_id: DEV_MOCK.data.user?.user_id || DEV_MOCK.data.user?.id || 910001,
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
  );
}

function demoDeviceTopupPlan(body) {
  const deviceCount = Number(body.device_count || body.months || 0);
  const plans = DEV_MOCK.data.device_topup_options?.plans || [];
  return (
    plans.find(
      (plan) =>
        String(plan.tariff_key || "") === String(body.tariff_key || plan.tariff_key || "") &&
        Number(plan.device_count || plan.purchased_hwid_devices || plan.months || 0) === deviceCount
    ) ||
    plans.find(
      (plan) =>
        Number(plan.device_count || plan.purchased_hwid_devices || plan.months || 0) === deviceCount
    ) ||
    null
  );
}

function applyDemoDeviceTopup(deviceCount) {
  const count = Math.max(1, Number(deviceCount || 0));
  const subscription = DEV_MOCK.data.subscription || {};
  const devicesPayload = DEV_MOCK.data.devices || {};
  const topupOptions = DEV_MOCK.data.device_topup_options || {};
  const devices = Array.isArray(devicesPayload.devices) ? devicesPayload.devices : [];
  const currentMax = Number(
    subscription.max_devices ||
      devicesPayload.max_devices ||
      topupOptions.max_devices ||
      topupOptions.current_limit ||
      0
  );
  const nextMax = currentMax > 0 ? currentMax + count : currentMax;
  const currentExtra = Number(
    subscription.extra_hwid_devices || topupOptions.extra_hwid_devices || 0
  );
  const nextExtra = currentExtra + count;
  const validUntil =
    subscription.extra_hwid_devices_valid_until_text ||
    topupOptions.extra_hwid_devices_valid_until_text ||
    subscription.end_date_text ||
    "28.06.2026 12:00";

  DEV_MOCK.data.subscription = {
    ...subscription,
    active: true,
    can_topup_devices: true,
    max_devices: nextMax,
    extra_hwid_devices: nextExtra,
    extra_hwid_devices_valid_until_text: validUntil,
  };
  DEV_MOCK.data.devices = {
    ...devicesPayload,
    ok: true,
    enabled: true,
    current_devices: devices.length || Number(devicesPayload.current_devices || 0),
    max_devices: nextMax,
    max_devices_label: nextMax > 0 ? String(nextMax) : devicesPayload.max_devices_label || "∞",
  };
  DEV_MOCK.data.device_topup_options = {
    ...topupOptions,
    ok: true,
    enabled: true,
    current_devices: devices.length || Number(topupOptions.current_devices || 0),
    max_devices: nextMax,
    current_limit: nextMax,
    extra_hwid_devices: nextExtra,
    extra_hwid_devices_valid_until_text: validUntil,
  };
}

function writeDemoLanguage(language) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage?.setItem(DEMO_LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Demo storage can be unavailable in private contexts; the in-memory mock still updates.
  }
}

function paged(items, params, fallbackSize = 25) {
  const total = items.length;
  if (params.has("limit") || params.has("offset")) {
    const limit = Math.max(1, Number(params.get("limit") || fallbackSize));
    const offset = Math.max(0, Number(params.get("offset") || 0));
    return {
      items: items.slice(offset, offset + limit),
      total,
      page: Math.floor(offset / limit),
      pageSize: limit,
    };
  }
  const page = Math.max(0, Number(params.get("page") || 0));
  const pageSize = Math.max(1, Number(params.get("page_size") || fallbackSize));
  const start = page * pageSize;
  return { items: items.slice(start, start + pageSize), total, page, pageSize };
}

function stringDate(value) {
  const time = Date.parse(value || "");
  return Number.isFinite(time) ? time : 0;
}

function userName(user) {
  return (
    [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim() ||
    user?.username ||
    user?.email ||
    String(user?.user_id || "")
  );
}

function demoUserSeed(user) {
  return Math.abs(Number(user?.user_id || user?.telegram_id || 0)) || 1;
}

function demoFutureIso(user, offsetDays = 30) {
  const seed = demoUserSeed(user);
  const base = Date.parse(user?.registration_date || "") || Date.UTC(2026, 0, 1);
  return new Date(base + (offsetDays + (seed % 180)) * 86400000).toISOString();
}

function withDemoAdminUserMetrics(user) {
  const seed = demoUserSeed(user);
  const paymentsCount =
    user.payments_count ?? (user.panel_status === "bot_only" ? 0 : Math.max(1, seed % 9));
  const paymentsTotal = user.payments_total_amount ?? paymentsCount * (290 + (seed % 11) * 75);
  const invitedCount = user.invited_users_count ?? (seed % 5 === 0 ? seed % 8 : seed % 3);
  const subscriptionExpiresAt =
    user.subscription_expires_at ??
    user.panel_status_expired_at ??
    (user.panel_status === "active" ? demoFutureIso(user, 45) : null);

  return {
    ...user,
    payments_total_amount: paymentsTotal,
    payments_count: paymentsCount,
    payments_currency: user.payments_currency || "RUB",
    invited_users_count: invitedCount,
    subscription_expires_at: subscriptionExpiresAt,
  };
}

function compareNullableDate(a, b, direction = "asc") {
  const at = stringDate(a);
  const bt = stringDate(b);
  if (!at && !bt) return 0;
  if (!at) return 1;
  if (!bt) return -1;
  return direction === "desc" ? bt - at : at - bt;
}

function withDemoAvatars(users, size = 96) {
  return (users || []).map((user) => withDemoAvatar(user, size));
}

function demoAdminUserById(userId) {
  return (DEMO_DATASET.adminUsers || []).find((user) => Number(user.user_id) === Number(userId));
}

function demoInviteesForUser(userId) {
  return (DEMO_DATASET.adminUsers || [])
    .filter((user) => Number(user.referred_by_id) === Number(userId))
    .sort((a, b) => stringDate(b.registration_date) - stringDate(a.registration_date));
}

function withDemoReferralSummary(detail) {
  if (!detail || typeof detail !== "object") return detail;
  const decorated = withDemoAvatarDetail(detail);
  const user = decorated.user || {};
  const inviter = user.referred_by_id ? demoAdminUserById(user.referred_by_id) : null;
  const invitees = demoInviteesForUser(user.user_id);
  return {
    ...decorated,
    referral: {
      ...(decorated.referral || {}),
      inviter: inviter ? withDemoAvatar(inviter) : null,
      invitees_total: invitees.length,
    },
  };
}

function withDemoAvatarTickets(tickets, size = 96) {
  return (tickets || []).map((ticket) => withDemoAvatarTicket(ticket, size));
}

function filterDemoUsers(params) {
  let out = (DEMO_DATASET.adminUsers || []).map(withDemoAdminUserMetrics);
  const q = (params.get("q") || params.get("search") || "").trim().toLowerCase();
  if (q) {
    out = out.filter((user) =>
      [
        user.user_id,
        user.telegram_id,
        user.username,
        user.first_name,
        user.last_name,
        user.email,
        user.panel_user_uuid,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q))
    );
  }

  const filter = params.get("filter") || "all";
  if (filter === "active") out = out.filter((user) => !user.is_banned);
  else if (filter === "banned") out = out.filter((user) => user.is_banned);
  else if (filter === "tg_linked") out = out.filter((user) => user.telegram_linked);
  else if (filter === "no_tg") out = out.filter((user) => !user.telegram_linked);
  else if (filter === "email_linked") out = out.filter((user) => Boolean(user.email));
  else if (filter === "no_email") out = out.filter((user) => !user.email);
  else if (filter === "panel_linked") out = out.filter((user) => Boolean(user.panel_user_uuid));

  const panelStatus = params.get("panel_status") || "all";
  if (panelStatus !== "all") out = out.filter((user) => user.panel_status === panelStatus);

  const premiumTraffic = params.get("premium_traffic") || "all";
  if (premiumTraffic !== "all") {
    out = out.filter((user) => (user.premium_traffic?.state || "none") === premiumTraffic);
  }

  const sort = params.get("sort") || "registered_desc";
  out.sort((a, b) => {
    if (sort === "registered_asc")
      return stringDate(a.registration_date) - stringDate(b.registration_date);
    if (sort === "name_asc") return userName(a).localeCompare(userName(b));
    if (sort === "name_desc") return userName(b).localeCompare(userName(a));
    if (sort === "id_asc") return Number(a.user_id || 0) - Number(b.user_id || 0);
    if (sort === "id_desc") return Number(b.user_id || 0) - Number(a.user_id || 0);
    if (sort === "premium_ratio_asc")
      return Number(a.premium_traffic?.percent ?? -1) - Number(b.premium_traffic?.percent ?? -1);
    if (sort === "premium_ratio_desc")
      return Number(b.premium_traffic?.percent ?? -1) - Number(a.premium_traffic?.percent ?? -1);
    if (sort === "payments_total_asc")
      return Number(a.payments_total_amount || 0) - Number(b.payments_total_amount || 0);
    if (sort === "payments_total_desc")
      return Number(b.payments_total_amount || 0) - Number(a.payments_total_amount || 0);
    if (sort === "payments_count_asc")
      return Number(a.payments_count || 0) - Number(b.payments_count || 0);
    if (sort === "payments_count_desc")
      return Number(b.payments_count || 0) - Number(a.payments_count || 0);
    if (sort === "invited_users_count_asc")
      return Number(a.invited_users_count || 0) - Number(b.invited_users_count || 0);
    if (sort === "invited_users_count_desc")
      return Number(b.invited_users_count || 0) - Number(a.invited_users_count || 0);
    if (sort === "subscription_expires_at_asc")
      return compareNullableDate(a.subscription_expires_at, b.subscription_expires_at, "asc");
    if (sort === "subscription_expires_at_desc")
      return compareNullableDate(a.subscription_expires_at, b.subscription_expires_at, "desc");
    return stringDate(b.registration_date) - stringDate(a.registration_date);
  });

  return out;
}

function demoSupportCounts(items = demoSupportTickets()) {
  const byStatus = { open: 0, awaiting_admin: 0, awaiting_user: 0, resolved: 0, closed: 0 };
  for (const item of items) byStatus[item.status] = (byStatus[item.status] || 0) + 1;
  const closed = (byStatus.closed || 0) + (byStatus.resolved || 0);
  return {
    ...byStatus,
    active: items.length - closed,
    closed,
    total: items.length,
    total_unread_admin: items.reduce((sum, item) => sum + Number(item.unread_admin_count || 0), 0),
  };
}

function filterDemoSupportTickets(items, params) {
  let out = [...items];
  const status = params.get("status");
  if (status === "active")
    out = out.filter((item) => !["closed", "resolved"].includes(item.status));
  else if (status === "closed")
    out = out.filter((item) => ["closed", "resolved"].includes(item.status));
  else if (status) out = out.filter((item) => item.status === status);

  const priority = params.get("priority");
  if (priority) out = out.filter((item) => item.priority === priority);
  const category = params.get("category");
  if (category) out = out.filter((item) => item.category === category);
  const search = (params.get("search") || "").trim().toLowerCase();
  if (search) {
    out = out.filter((item) =>
      [item.subject, item.user?.username, item.user?.email, item.ticket_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(search))
    );
  }

  const priorityRank = { urgent: 4, high: 3, normal: 2, low: 1 };
  const sort = params.get("sort") || "updated_desc";
  out.sort((a, b) => {
    if (sort === "importance_desc") {
      return (
        (priorityRank[b.priority] || 0) - (priorityRank[a.priority] || 0) ||
        stringDate(b.last_message_at || b.created_at) -
          stringDate(a.last_message_at || a.created_at)
      );
    }
    if (sort === "updated_asc") {
      return (
        stringDate(a.last_message_at || a.created_at) -
        stringDate(b.last_message_at || b.created_at)
      );
    }
    if (sort === "created_desc") return stringDate(b.created_at) - stringDate(a.created_at);
    if (sort === "created_asc") return stringDate(a.created_at) - stringDate(b.created_at);
    return (
      stringDate(b.last_message_at || b.created_at) - stringDate(a.last_message_at || a.created_at)
    );
  });
  return out;
}

function demoSettingsValuesByKey() {
  const map = new Map();
  for (const section of DEMO_DATASET.settingsSections || []) {
    for (const field of section.fields || []) {
      map.set(field.key, field);
    }
  }
  return map;
}

function demoRuntimeSettingValue(key) {
  const values = {
    TRIAL_WITHOUT_TELEGRAM_ENABLED: DEV_MOCK.config.trialWithoutTelegramEnabled ?? true,
    REFERRAL_WELCOME_BONUS_DAYS:
      DEV_MOCK.config.referralWelcomeBonusDays ?? DEV_MOCK.data.referral?.welcome_bonus_days ?? 3,
    REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED:
      DEV_MOCK.config.referralWelcomeWithoutTelegramEnabled ?? true,
    REFERRAL_ONE_BONUS_PER_REFEREE:
      DEV_MOCK.config.referralOneBonusPerReferee ??
      DEV_MOCK.data.referral?.one_bonus_per_referee ??
      false,
    LEGACY_REFS: DEV_MOCK.config.legacyRefs ?? true,
    DISPOSABLE_EMAIL_DOMAINS: DEV_MOCK.config.disposableEmailDomains || "",
  };
  return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : undefined;
}

function demoSettingsSections(clone) {
  // Section/field structure comes from the manifest snapshot generated off the
  // Python source of truth (scripts/export_settings_manifest.py), so the demo
  // stays in sync with the real admin. Realistic values are overlaid per field
  // key from the dump-based dataset; fields absent there (e.g. a freshly added
  // section) simply show their placeholders.
  const demoValues = demoSettingsValuesByKey();
  const sections = clone(SETTINGS_MANIFEST_SECTIONS);
  for (const section of sections) {
    for (const field of section.fields || []) {
      const demoField = demoValues.get(field.key);
      if (demoField) {
        if ("value" in demoField) field.value = demoField.value;
        if ("overridden" in demoField) field.overridden = demoField.overridden;
        if ("updated_at" in demoField) field.updated_at = demoField.updated_at;
        if ("source" in demoField) field.source = demoField.source;
        if (field.secret && "has_value" in demoField) field.has_value = demoField.has_value;
      } else {
        const runtimeValue = demoRuntimeSettingValue(field.key);
        if (typeof runtimeValue !== "undefined") field.value = runtimeValue;
      }
      if (demoSettingsChanges.has(field.key)) {
        const change = demoSettingsChanges.get(field.key);
        if (change.deleted) {
          field.value = field.default ?? "";
          field.overridden = false;
        } else {
          field.value = change.value;
          field.overridden = true;
        }
      }
    }
  }
  return sections;
}

function applyDemoSettingToMock(key, value) {
  if (key === "WEBAPP_TITLE") DEV_MOCK.config.title = value || "";
  if (key === "WEBAPP_LOGO_URL") DEV_MOCK.config.logoUrl = value || "";
  if (key === "WEBAPP_FAVICON_URL" || key === "WEBAPP_LOGO_FAVICON_URL") {
    DEV_MOCK.config.faviconUrl = value || DEV_MOCK.config.faviconUrl || "";
  }
  if (key === "WEBAPP_FAVICON_USE_CUSTOM") DEV_MOCK.config.faviconUseCustom = Boolean(value);
  if (key === "TRIAL_ENABLED") {
    DEV_MOCK.config.trialEnabled = Boolean(value);
    DEV_MOCK.data.settings.trial_enabled = Boolean(value);
  }
  if (key === "TRIAL_DURATION_DAYS") {
    DEV_MOCK.config.trialDurationDays = value;
    DEV_MOCK.data.settings.trial_duration_days = Number(value || 0);
  }
  if (key === "TRIAL_TRAFFIC_LIMIT_GB") {
    DEV_MOCK.config.trialTrafficLimitGb = value;
    DEV_MOCK.data.settings.trial_traffic_limit_gb = Number(value || 0);
  }
  if (key === "TRIAL_TRAFFIC_STRATEGY") {
    DEV_MOCK.config.trialTrafficStrategy = value || "NO_RESET";
    DEV_MOCK.data.settings.trial_traffic_strategy = value || "NO_RESET";
  }
  if (key === "TRIAL_WITHOUT_TELEGRAM_ENABLED") {
    DEV_MOCK.config.trialWithoutTelegramEnabled = Boolean(value);
    DEV_MOCK.data.settings.trial_without_telegram_enabled = Boolean(value);
  }
  if (key === "TRIAL_SQUAD_UUIDS") DEV_MOCK.config.trialSquadUuids = value || "";
  if (key === "REFERRAL_WELCOME_BONUS_DAYS") {
    DEV_MOCK.config.referralWelcomeBonusDays = Number(value || 0);
    DEV_MOCK.data.referral.welcome_bonus_days = Number(value || 0);
  }
  if (key === "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED") {
    DEV_MOCK.config.referralWelcomeWithoutTelegramEnabled = Boolean(value);
    DEV_MOCK.data.referral.welcome_bonus_without_telegram_enabled = Boolean(value);
  }
  if (key === "REFERRAL_ONE_BONUS_PER_REFEREE") {
    DEV_MOCK.config.referralOneBonusPerReferee = Boolean(value);
    DEV_MOCK.data.referral.one_bonus_per_referee = Boolean(value);
  }
  if (key === "LEGACY_REFS") DEV_MOCK.config.legacyRefs = Boolean(value);
  if (key === "DISPOSABLE_EMAIL_DOMAINS") {
    DEV_MOCK.config.disposableEmailDomains = value || "";
  }
}

function userSnapshotForTicket(ticket) {
  const detail = DEMO_DATASET.adminUserDetails?.[String(ticket?.user_id)] || {};
  const user = detail.user || ticket?.user || {};
  const sub = detail.active_subscription || {};
  return {
    user_id: user.user_id,
    name: userName(user) || user.username || user.email || String(user.user_id || ""),
    username: user.username || "",
    email: user.email || "",
    tariff: sub.tariff_name || sub.tariff_key || "Demo",
    panel_status: user.panel_status || sub.status_from_panel || "",
    remaining: sub.end_date || "",
    regular_traffic: `${sub.traffic_used_bytes || 0} / ${sub.traffic_limit_bytes || 0}`,
    premium_traffic: `${sub.premium_used_bytes || 0} / ${sub.premium_limit_bytes || 0}`,
  };
}

function demoApiResponse(path, cleanPath, options, context) {
  const { clone, currentLang = "ru", normalizeLangCode = (value) => value || "ru" } = context;
  const method = String(options.method || "GET").toUpperCase();
  const params = queryParams(path);

  if (cleanPath === "/admin/stats") return clone(DEMO_DATASET.stats);
  if (cleanPath === "/admin/broadcast/audience-counts") {
    return {
      ok: true,
      counts: { all: 1280, active: 742, inactive: 538, expired: 311, never: 227 },
    };
  }
  if (cleanPath === "/admin/sync") return { ok: true, status: "queued" };

  if (cleanPath === "/admin/payments") {
    const page = paged(DEMO_DATASET.adminPayments || [], params, 25);
    return {
      ok: true,
      payments: clone(page.items),
      total: page.total,
      page: page.page,
      page_size: page.pageSize,
    };
  }
  if (/^\/admin\/payments\/\d+$/.test(cleanPath)) {
    const id = Number(cleanPath.split("/").pop());
    const payment = (DEMO_DATASET.adminPayments || []).find((item) => item.payment_id === id);
    return payment ? { ok: true, payment: clone(payment) } : { ok: false, error: "not_found" };
  }

  if (cleanPath === "/admin/users") {
    const filtered = filterDemoUsers(params);
    const page = paged(filtered, params, 25);
    return {
      ok: true,
      users: clone(withDemoAvatars(page.items)),
      total: page.total,
      page: page.page,
      page_size: page.pageSize,
    };
  }
  if (cleanPath.startsWith("/admin/users/")) {
    const parts = cleanPath.split("/");
    const id = Number(parts[3]);
    const detail = DEMO_DATASET.adminUserDetails?.[String(id)];
    if (!detail) return { ok: false, error: "not_found" };
    const decoratedDetail = withDemoReferralSummary(detail);
    if (parts[4]) {
      if (parts[4] === "referrals") {
        const invitees = demoInviteesForUser(id);
        const page = paged(invitees, params, 25);
        return {
          ok: true,
          user: clone(decoratedDetail.user),
          inviter: clone(decoratedDetail.referral?.inviter || null),
          invitees: clone(withDemoAvatars(page.items)),
          total: page.total,
          page: page.page,
          page_size: page.pageSize,
        };
      }
      if (parts[4] === "telegram-profile-link") {
        return { ok: true, url: `https://t.me/${detail.user?.username || "demo_user"}` };
      }
      if (parts[4] === "message" && parts[5] === "preview") {
        return { ok: true, text: "Demo broadcast preview for the selected account." };
      }
      return { ok: true, user: clone(decoratedDetail.user), detail: clone(decoratedDetail) };
    }
    return clone(decoratedDetail);
  }

  if (cleanPath === "/admin/logs") {
    let logs = [...(DEMO_DATASET.adminLogs || [])];
    const userId = params.get("user_id");
    if (userId) {
      logs = logs.filter(
        (item) =>
          String(item.user_id || "") === userId || String(item.target_user_id || "") === userId
      );
    }
    const page = paged(logs, params, 50);
    return {
      ok: true,
      logs: clone(page.items),
      total: page.total,
      page: page.page,
      page_size: page.pageSize,
    };
  }

  if (cleanPath === "/admin/promos") {
    if (method === "POST") {
      const body = jsonBody(options);
      demoPromos().unshift({
        id: 3900 + demoPromos().length + 1,
        code: body.code || "DEMO",
        bonus_days: Number(body.bonus_days || 7),
        max_activations: Number(body.max_activations || 1),
        current_activations: 0,
        is_active: true,
        valid_until: new Date(Date.now() + Number(body.valid_days || 30) * 86400000).toISOString(),
        created_at: new Date().toISOString(),
        created_by_admin_id: DEV_MOCK.data.user?.id || DEV_MOCK.data.user?.user_id,
      });
      return { ok: true, promo: clone(demoPromos()[0]) };
    }
    const page = paged(demoPromos(), params, 25);
    return {
      ok: true,
      promos: clone(page.items),
      total: page.total,
      page: page.page,
      page_size: page.pageSize,
    };
  }
  if (cleanPath.startsWith("/admin/promos/")) {
    const id = Number(cleanPath.split("/").pop());
    const promo = demoPromos().find((item) => item.id === id);
    if (!promo) return { ok: false, error: "not_found" };
    if (method === "DELETE") {
      demoPromosState = demoPromos().filter((item) => item.id !== id);
      return { ok: true };
    }
    Object.assign(promo, jsonBody(options));
    return { ok: true, promo: clone(promo) };
  }

  if (cleanPath === "/admin/ads") {
    if (method === "POST") {
      const body = jsonBody(options);
      demoAds().unshift({
        id: 900 + demoAds().length + 1,
        source: body.source || "demo",
        start_param: body.start_param || "demo_campaign",
        cost: Number(body.cost || 0),
        is_active: true,
        created_at: new Date().toISOString(),
        stats: { users: 0, trial_activations: 0, payments: 0, revenue: 0 },
      });
      return { ok: true, campaign: clone(demoAds()[0]) };
    }
    return { ok: true, campaigns: clone(demoAds()), totals: clone(DEMO_DATASET.adsTotals || {}) };
  }
  if (cleanPath.startsWith("/admin/ads/")) {
    const parts = cleanPath.split("/");
    const id = Number(parts[3]);
    const campaign = demoAds().find((item) => item.id === id);
    if (!campaign) return { ok: false, error: "not_found" };
    if (parts[4] === "toggle") {
      campaign.is_active = !campaign.is_active;
      return { ok: true, campaign: clone(campaign) };
    }
    if (method === "DELETE") {
      demoAdsState = demoAds().filter((item) => item.id !== id);
      return { ok: true };
    }
    return { ok: true, campaign: clone(campaign) };
  }

  if (cleanPath === "/admin/backups") return clone(DEMO_DATASET.backups);
  if (cleanPath === "/admin/backups/create") {
    const archive = clone(DEMO_DATASET.backups?.archives?.[0] || {});
    archive.name = `minishop-demo-${Date.now()}.zip`;
    archive.created_at = new Date().toISOString();
    return {
      ok: true,
      archive,
      result: { archive_name: archive.name, completed_at: archive.created_at, warnings: [] },
    };
  }
  if (cleanPath === "/admin/backups/upload") {
    return { ok: true, archive: clone(DEMO_DATASET.backups?.archives?.[0] || {}) };
  }
  if (cleanPath === "/admin/backups/restore") {
    return {
      ok: true,
      result: {
        archive_name: DEMO_DATASET.backups?.archives?.[0]?.name || "demo.zip",
        database_restored: true,
        warnings: [],
      },
    };
  }

  if (cleanPath === "/admin/settings" && method === "PATCH") {
    const body = jsonBody(options);
    for (const key of body.deletes || []) demoSettingsChanges.set(key, { deleted: true });
    for (const [key, value] of Object.entries(body.updates || {})) {
      demoSettingsChanges.set(key, { value, deleted: false });
      applyDemoSettingToMock(key, value);
    }
    return {
      ok: true,
      applied: Object.keys(body.updates || {}).length,
      reverted: (body.deletes || []).length,
    };
  }
  if (cleanPath === "/admin/settings") return { ok: true, sections: demoSettingsSections(clone) };

  if (cleanPath === "/admin/tariffs") {
    if (method === "PUT") {
      const body = jsonBody(options);
      const catalog = body.catalog || body;
      demoTariffsState = defaultClone(catalog);
    }
    return {
      ok: true,
      path: "data/tariffs.json",
      catalog: clone(demoTariffs()),
    };
  }

  if (cleanPath === "/admin/panel/internal-squads") {
    return {
      ok: true,
      squads: clone(
        DEMO_DATASET.panelSquads || [
          { uuid: "db786ee8-816b-4760-80aa-1fc7a3669ff2", name: "Base RU" },
          { uuid: "5f29045a-5e8b-4b06-a7b1-29abf0ad3a54", name: "Base EU" },
          { uuid: "2f2f6e0a-1f2d-4e80-a33b-0ebf3a409012", name: "Premium EU" },
        ]
      ),
    };
  }

  if (cleanPath === "/admin/translations" && method === "PATCH") {
    return { ok: true, applied: 1, reverted: 0, file_written: false };
  }
  if (cleanPath === "/admin/translations") {
    return { ok: true, ...clone(DEMO_DATASET.translations) };
  }

  if (cleanPath === "/admin/support/stats") return { ok: true, stats: demoSupportCounts() };
  if (cleanPath === "/admin/support/tickets") {
    const tickets = filterDemoSupportTickets(demoSupportTickets(), params);
    const page = paged(tickets, params, 50);
    return { ok: true, tickets: clone(withDemoAvatarTickets(page.items)), total: page.total };
  }
  if (cleanPath.startsWith("/admin/support/tickets/")) {
    const parts = cleanPath.split("/");
    const ticketId = Number(parts[4]);
    const ticket = demoSupportTickets().find((item) => item.ticket_id === ticketId);
    if (!ticket) return { ok: false, error: "not_found" };
    const messages = demoSupportMessages()[String(ticketId)] || [];
    if (parts[5] === "read") {
      ticket.unread_admin_count = 0;
      return { ok: true };
    }
    if (parts[5] === "messages") {
      const body = jsonBody(options);
      const message = {
        message_id: Date.now(),
        ticket_id: ticketId,
        author_role: "admin",
        author_user_id: DEV_MOCK.data.user?.id || DEV_MOCK.data.user?.user_id,
        author_name: "Поддержка",
        body: body.body || "",
        is_internal_note: Boolean(body.is_internal_note),
        created_at: new Date().toISOString(),
      };
      messages.push(message);
      demoSupportMessages()[String(ticketId)] = messages;
      ticket.last_message_at = message.created_at;
      ticket.last_message_role = "admin";
      ticket.status = "awaiting_user";
      return { ok: true, ticket: clone(withDemoAvatarTicket(ticket)), message: clone(message) };
    }
    if (method === "PATCH") {
      Object.assign(ticket, jsonBody(options));
      return { ok: true, ticket: clone(withDemoAvatarTicket(ticket)) };
    }
    return {
      ok: true,
      ticket: clone(withDemoAvatarTicket(ticket)),
      messages: clone(messages),
      user_snapshot: userSnapshotForTicket(withDemoAvatarTicket(ticket)),
    };
  }

  if (cleanPath === "/support/tickets" && method === "POST") {
    const body = jsonBody(options);
    const user = DEV_MOCK.data.user || {};
    const ticket = {
      ticket_id: 4900 + demoSupportTickets().length + 1,
      user_id: user.user_id || user.id,
      subject: body.subject || "Новое обращение в поддержку",
      category: body.category || "other",
      priority: body.priority || "normal",
      status: "awaiting_admin",
      unread_user_count: 0,
      unread_admin_count: 1,
      last_message_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      user,
    };
    demoSupportTickets().unshift(ticket);
    demoSupportMessages()[String(ticket.ticket_id)] = [
      {
        message_id: Date.now(),
        ticket_id: ticket.ticket_id,
        author_role: "user",
        author_user_id: ticket.user_id,
        author_name: userName(user) || user.username || "Демо-пользователь",
        body: body.body || "",
        created_at: ticket.created_at,
      },
    ];
    return { ok: true, ticket: clone(ticket) };
  }
  if (cleanPath === "/support/tickets") {
    const tickets = filterDemoSupportTickets(demoSupportTickets(), params);
    const page = paged(tickets, params, 50);
    return {
      ok: true,
      tickets: clone(withDemoAvatarTickets(page.items)),
      total: page.total,
      counts: demoSupportCounts(demoSupportTickets()),
    };
  }
  if (cleanPath.startsWith("/support/tickets/")) {
    const parts = cleanPath.split("/");
    const ticketId = Number(parts[3]);
    const ticket = demoSupportTickets().find((item) => item.ticket_id === ticketId);
    if (!ticket) return { ok: false, error: "not_found" };
    const messages = demoSupportMessages()[String(ticketId)] || [];
    if (parts[4] === "read") {
      ticket.unread_user_count = 0;
      return { ok: true };
    }
    if (parts[4] === "messages") {
      const body = jsonBody(options);
      const user = DEV_MOCK.data.user || {};
      const message = {
        message_id: Date.now(),
        ticket_id: ticketId,
        author_role: "user",
        author_user_id: user.user_id || user.id,
        author_name: userName(user) || user.username || "Демо-пользователь",
        body: body.body || "",
        created_at: new Date().toISOString(),
      };
      messages.push(message);
      demoSupportMessages()[String(ticketId)] = messages;
      ticket.last_message_at = message.created_at;
      ticket.last_message_role = "user";
      ticket.status = "awaiting_admin";
      return { ok: true, ticket: clone(withDemoAvatarTicket(ticket)), message: clone(message) };
    }
    return { ok: true, ticket: clone(withDemoAvatarTicket(ticket)), messages: clone(messages) };
  }
  if (cleanPath === "/support/unread") {
    return {
      ok: true,
      unread: demoSupportTickets().reduce(
        (sum, item) => sum + Number(item.unread_user_count || 0),
        0
      ),
    };
  }

  if (cleanPath === "/account/language" && method === "POST") {
    const language = normalizeLangCode(jsonBody(options).language || currentLang);
    DEV_MOCK.data.user.language_code = language;
    DEV_MOCK.config.language = language;
    writeDemoLanguage(language);
    return { ok: true, language };
  }

  return undefined;
}

export async function mockApi(path, options = {}, context = {}) {
  const {
    currentLang = "ru",
    normalizeLangCode = (value) => value || "ru",
    clone = defaultClone,
  } = context;
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  const cleanPath = String(path || "").split("?")[0];
  const demoResponse = demoApiResponse(path, cleanPath, options, {
    clone,
    currentLang,
    normalizeLangCode,
  });
  if (demoResponse !== undefined) return demoResponse;
  const adminUsers = withDemoAvatars(
    [
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
        premium_traffic: {
          state: "good",
          unlimited: false,
          used_bytes: 4 * 1073741824,
          limit_bytes: 25 * 1073741824,
          percent: 16,
        },
        panel_status: "active",
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
        premium_traffic: {
          state: "warn",
          unlimited: false,
          used_bytes: 22 * 1073741824,
          limit_bytes: 25 * 1073741824,
          percent: 88,
        },
        panel_status: "active",
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
        premium_traffic: { state: "none" },
        panel_status: "bot_only",
      },
    ].map(withDemoAdminUserMetrics)
  );
  const supportTickets = [
    {
      ticket_id: 42,
      user_id: 100200300,
      subject: "Не подключается профиль на телефоне",
      category: "technical",
      priority: "high",
      status: "awaiting_admin",
      unread_user_count: 0,
      unread_admin_count: 2,
      last_message_at: new Date(Date.now() - 18 * 60000).toISOString(),
      created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
      user: adminUsers[0],
    },
    {
      ticket_id: 43,
      user_id: 100200300,
      subject: "Вопрос по оплате подписки",
      category: "billing",
      priority: "normal",
      status: "awaiting_user",
      unread_user_count: 1,
      unread_admin_count: 0,
      last_message_at: new Date(Date.now() - 4 * 3600000).toISOString(),
      created_at: new Date(Date.now() - 6 * 3600000).toISOString(),
      user: adminUsers[0],
    },
    {
      ticket_id: 41,
      user_id: 100200300,
      subject: "Закрытый вопрос по старому профилю",
      category: "technical",
      priority: "low",
      status: "closed",
      unread_user_count: 0,
      unread_admin_count: 0,
      last_message_at: new Date(Date.now() - 4 * 86400000).toISOString(),
      created_at: new Date(Date.now() - 6 * 86400000).toISOString(),
      closed_at: new Date(Date.now() - 4 * 86400000).toISOString(),
      user: adminUsers[0],
    },
  ];
  const adminPayments = [
    {
      payment_id: 12,
      user_id: 100200300,
      user_label: "anna_ops",
      telegram_id: 100200300,
      traffic_regular_gb: null,
      traffic_premium_gb: null,
      provider: "yookassa",
      provider_payment_id: "2f3a7c9e-yk-preview",
      yookassa_payment_id: "2f3a7c9e-yk-preview",
      idempotence_key: "admin-preview-payment-12",
      amount: 790,
      currency: "RUB",
      status: "succeeded",
      description: "Standard · 1 месяц",
      subscription_duration_months: 1,
      sale_mode: "subscription",
      tariff_key: "standard",
      purchased_gb: null,
      purchased_hwid_devices: null,
      promo_code: "SPRING",
      created_at: "2026-05-01T14:15:00Z",
      updated_at: "2026-05-01T14:17:00Z",
    },
    {
      payment_id: 13,
      user_id: 100200301,
      user_label: "client_pro",
      telegram_id: 87543123,
      traffic_regular_gb: 25,
      traffic_premium_gb: null,
      provider: "platega",
      provider_payment_id: "platega-demo-13",
      amount: 199,
      currency: "RUB",
      status: "pending_platega",
      description: "",
      subscription_duration_months: null,
      sale_mode: "traffic_package",
      tariff_key: "standard",
      purchased_gb: 25,
      purchased_hwid_devices: null,
      created_at: new Date(Date.now() - 3 * 3600000).toISOString(),
      updated_at: null,
    },
  ];
  function supportCounts(items = supportTickets) {
    const byStatus = { open: 0, awaiting_admin: 0, awaiting_user: 0, resolved: 0 };
    for (const item of items) {
      byStatus[item.status] = (byStatus[item.status] || 0) + 1;
    }
    const closed = (byStatus.closed || 0) + (byStatus.resolved || 0);
    const active = items.length - closed;
    return { ...byStatus, active, closed, total: items.length };
  }
  function filterSupportTickets(items, params) {
    let out = [...items];
    const status = params.get("status");
    if (status === "active")
      out = out.filter((item) => !["closed", "resolved"].includes(item.status));
    else if (status === "closed")
      out = out.filter((item) => ["closed", "resolved"].includes(item.status));
    else if (status) out = out.filter((item) => item.status === status);
    const priority = params.get("priority");
    if (priority) out = out.filter((item) => item.priority === priority);
    const category = params.get("category");
    if (category) out = out.filter((item) => item.category === category);
    const search = (params.get("search") || "").trim().toLowerCase();
    if (search) {
      out = out.filter((item) =>
        [item.subject, item.user?.username, item.user?.email, String(item.ticket_id)]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(search))
      );
    }
    const sort = params.get("sort") || "updated_desc";
    const priorityRank = { urgent: 4, high: 3, normal: 2, low: 1 };
    out.sort((a, b) => {
      if (sort === "importance_desc") {
        return (
          (priorityRank[b.priority] || 0) - (priorityRank[a.priority] || 0) ||
          new Date(b.last_message_at || b.created_at) - new Date(a.last_message_at || a.created_at)
        );
      }
      if (sort === "updated_asc") {
        return (
          new Date(a.last_message_at || a.created_at) - new Date(b.last_message_at || b.created_at)
        );
      }
      if (sort === "created_desc") return new Date(b.created_at) - new Date(a.created_at);
      if (sort === "created_asc") return new Date(a.created_at) - new Date(b.created_at);
      return (
        new Date(b.last_message_at || b.created_at) - new Date(a.last_message_at || a.created_at)
      );
    });
    return out;
  }
  const supportMessages = {
    42: [
      {
        message_id: 1,
        ticket_id: 42,
        author_role: "user",
        author_user_id: 100200300,
        author_name: "Анна Смирнова",
        body: "После обновления приложения профиль перестал подключаться. Ошибка появляется сразу после импорта ссылки.",
        created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
      },
      {
        message_id: 2,
        ticket_id: 42,
        author_role: "admin",
        author_user_id: 1,
        author_name: "Мария, поддержка",
        body: "Проверили подписку, она активна. Попробуйте удалить старый профиль и импортировать ссылку ещё раз.",
        created_at: new Date(Date.now() - 90 * 60000).toISOString(),
      },
      {
        message_id: 3,
        ticket_id: 42,
        author_role: "user",
        author_user_id: 100200300,
        author_name: "Анна Смирнова",
        body: "Сделал так, но теперь вижу timeout. Телефон iPhone, сеть домашний Wi‑Fi.",
        created_at: new Date(Date.now() - 18 * 60000).toISOString(),
      },
    ],
    43: [
      {
        message_id: 4,
        ticket_id: 43,
        author_role: "user",
        author_user_id: 100200300,
        author_name: "Анна Смирнова",
        body: "Оплата прошла, но срок подписки не изменился.",
        created_at: new Date(Date.now() - 6 * 3600000).toISOString(),
      },
      {
        message_id: 5,
        ticket_id: 43,
        author_role: "admin",
        author_user_id: 2,
        author_name: "Иван, поддержка",
        body: "Платёж нашли и применили вручную. Проверьте, пожалуйста, дату окончания подписки.",
        created_at: new Date(Date.now() - 4 * 3600000).toISOString(),
      },
    ],
  };
  const mockAdminDailySeries = (() => {
    const days = 730;
    const out = [];
    const now = new Date();
    for (let i = 0; i < days; i++) {
      const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
      d.setUTCDate(d.getUTCDate() - (days - 1 - i));
      const iso = d.toISOString().slice(0, 10);
      const wave = Math.sin(i / 5) * 520 + 720 + ((i * 41) % 280);
      out.push({ date: iso, amount: Math.max(0, Math.round(wave)) });
    }
    return out;
  })();
  const compactBackupStamp = (date) => {
    const pad = (value) => String(value).padStart(2, "0");
    return [
      `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`,
      pad(date.getHours()),
      pad(date.getMinutes()),
    ].join("-");
  };
  const mockBackups = [
    {
      name: "minishop-20260527-12-00.zip",
      size_bytes: 184320,
      modified_at: "2026-05-27T09:00:00Z",
      created_at: "2026-05-27T09:00:00Z",
      created_at_local: "2026-05-27T12:00:00+03:00",
      has_database: true,
      has_compose: true,
      database_name: "remnawave_minishop",
      compose_files_count: 6,
      warnings: [],
      manifest: {},
    },
    {
      name: "minishop-20260527-11-00.zip",
      size_bytes: 153600,
      modified_at: "2026-05-27T08:00:00Z",
      created_at: "2026-05-27T08:00:00Z",
      created_at_local: "2026-05-27T11:00:00+03:00",
      has_database: true,
      has_compose: false,
      database_name: "remnawave_minishop",
      compose_files_count: 0,
      warnings: ["Compose source directory is unavailable"],
      manifest: {},
    },
  ];
  if (path === "/admin/stats") {
    return {
      ok: true,
      currency_symbol: "RUB",
      users: {
        total_users: 248,
        active_today: 9,
        active_subscriptions: 172,
        paid_subscriptions: 141,
        trial_users: 8,
        free_subscription_users: 23,
        inactive_users: 76,
        expired_subscription_users: 31,
        banned_users: 3,
        referral_users: 34,
      },
      financial: {
        today_revenue: 1240,
        week_revenue: 15800,
        month_revenue: 44100,
        all_time_revenue: 186240,
        today_payments_count: 4,
        daily_series: mockAdminDailySeries,
      },
      panel_sync: {
        status: "success",
        last_sync_time: new Date().toISOString(),
        users_processed: 172,
        subscriptions_synced: 168,
      },
      recent_payments: adminPayments.slice(0, 1),
    };
  }
  if (cleanPath === "/admin/payments") {
    return {
      ok: true,
      payments: clone(adminPayments),
      total: adminPayments.length,
      page: 0,
      page_size: 25,
    };
  }
  if (cleanPath.startsWith("/admin/payments/")) {
    const id = Number(cleanPath.split("/")[3]);
    if (!Number.isFinite(id)) return { ok: false, error: "not_found" };
    const payment = adminPayments.find((item) => item.payment_id === id) || adminPayments[0];
    return { ok: true, payment: clone(payment) };
  }
  if (cleanPath === "/admin/users")
    return { ok: true, users: adminUsers, total: adminUsers.length, page: 0, page_size: 25 };
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
        {
          subscription_id: 10,
          end_date: "2026-06-08T12:00:00Z",
          tariff_key: "standard",
          is_active: true,
          status_from_panel: "ACTIVE",
        },
        {
          subscription_id: 9,
          end_date: "2026-05-08T12:00:00Z",
          tariff_key: "standard",
          is_active: false,
          status_from_panel: "EXPIRED",
        },
      ],
      total_paid: 2380,
      recent_payments: [
        {
          payment_id: 12,
          amount: 790,
          currency: "RUB",
          provider: "yookassa",
          status: "succeeded",
          created_at: "2026-05-01T14:15:00Z",
        },
        {
          payment_id: 11,
          amount: 790,
          currency: "RUB",
          provider: "stars",
          status: "succeeded",
          created_at: "2026-04-01T14:15:00Z",
        },
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
      path: "data/tariffs.json",
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
            prices_rub: { 1: 150, 3: 400 },
            prices_stars: { 1: 0, 3: 0 },
            enabled_periods: [1, 3],
            enabled: true,
          },
        ],
      },
    };
  }
  if (path === "/admin/panel/internal-squads") {
    return {
      ok: true,
      squads: [
        { uuid: "db786ee8-816b-4760-80aa-1fc7a3669ff2", name: "Base RU" },
        { uuid: "2f2f6e0a-1f2d-4e80-a33b-0ebf3a409012", name: "Trial warmup" },
      ],
    };
  }
  if (path === "/admin/themes") {
    if (String(options.method || "GET").toUpperCase() === "PUT") {
      try {
        const body = options?.body ? JSON.parse(String(options.body)) : {};
        const catalog = body.catalog || body;
        if (catalog?.themes) {
          DEV_MOCK.config.themesCatalog = clone(catalog);
          DEV_MOCK.data.themes_catalog = clone(catalog);
        }
      } catch (_e) {
        void _e;
      }
      return {
        ok: true,
        themes_dir: "data/themes",
        catalog: clone(DEV_MOCK.config.themesCatalog),
      };
    }
    return {
      ok: true,
      themes_dir: "data/themes",
      catalog: clone(DEV_MOCK.config.themesCatalog),
    };
  }
  if (path === "/admin/appearance/logo") {
    return {
      ok: true,
      logo_url: "/webapp-uploaded-logo/logo-0000000000000000.png",
      favicon_url: "/webapp-favicon/0000000000000000/icon-180.png",
    };
  }
  if (path === "/admin/appearance/favicon") {
    return {
      ok: true,
      favicon_url: "/webapp-favicon/1111111111111111/icon-180.png",
      variants: {
        32: "/webapp-favicon/1111111111111111/icon-32.png",
        apple_touch: "/webapp-favicon/1111111111111111/apple-touch-icon.png",
      },
    };
  }
  if (path === "/admin/backups") {
    return {
      ok: true,
      backup_dir: "data/backups",
      archives: clone(mockBackups),
    };
  }
  if (path === "/admin/backups/create") {
    const createdAt = new Date();
    const archive = {
      ...mockBackups[0],
      name: `minishop-${compactBackupStamp(createdAt)}.zip`,
      modified_at: createdAt.toISOString(),
      created_at: createdAt.toISOString(),
      created_at_local: createdAt.toISOString(),
    };
    return {
      ok: true,
      archive,
      result: {
        archive_name: archive.name,
        archive_path: `data/backups/${archive.name}`,
        started_at: createdAt.toISOString(),
        completed_at: createdAt.toISOString(),
        db_dump_included: true,
        compose_files_count: archive.compose_files_count,
        size_bytes: archive.size_bytes,
        warnings: [],
      },
    };
  }
  if (path === "/admin/backups/upload") {
    const uploadedAt = new Date();
    return {
      ok: true,
      archive: {
        ...mockBackups[0],
        name: `minishop-uploaded-${compactBackupStamp(uploadedAt)}-0000000000000000.zip`,
        modified_at: uploadedAt.toISOString(),
        created_at: uploadedAt.toISOString(),
        created_at_local: uploadedAt.toISOString(),
      },
    };
  }
  if (path === "/admin/backups/restore") {
    return {
      ok: true,
      result: {
        archive_name: mockBackups[0].name,
        started_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        database_restored: true,
        compose_files_restored: 6,
        compose_target_dir: "/app/compose-source",
        compose_pre_restore_archive: "data/backups/minishop-pre-restore-20260527-12-15.zip",
        warnings: [],
      },
    };
  }
  if (path === "/admin/settings" && String(options.method || "GET").toUpperCase() === "PATCH") {
    try {
      const body = options?.body ? JSON.parse(String(options.body)) : {};
      const updates = body.updates || {};
      if (Object.prototype.hasOwnProperty.call(updates, "WEBAPP_TITLE")) {
        DEV_MOCK.config.title = updates.WEBAPP_TITLE || "";
      }
      if (Object.prototype.hasOwnProperty.call(updates, "WEBAPP_LOGO_URL")) {
        DEV_MOCK.config.logoUrl = updates.WEBAPP_LOGO_URL || "";
      }
      if (Object.prototype.hasOwnProperty.call(updates, "WEBAPP_FAVICON_URL")) {
        DEV_MOCK.config.faviconUrl = updates.WEBAPP_FAVICON_URL || "";
      }
      if (Object.prototype.hasOwnProperty.call(updates, "WEBAPP_LOGO_FAVICON_URL")) {
        DEV_MOCK.config.faviconUrl =
          updates.WEBAPP_LOGO_FAVICON_URL || DEV_MOCK.config.faviconUrl || "";
      }
      if (Object.prototype.hasOwnProperty.call(updates, "WEBAPP_FAVICON_USE_CUSTOM")) {
        DEV_MOCK.config.faviconUseCustom = Boolean(updates.WEBAPP_FAVICON_USE_CUSTOM);
      }
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_ENABLED")) {
        DEV_MOCK.config.trialEnabled = Boolean(updates.TRIAL_ENABLED);
      }
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_DURATION_DAYS")) {
        DEV_MOCK.config.trialDurationDays = updates.TRIAL_DURATION_DAYS;
      }
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_TRAFFIC_LIMIT_GB")) {
        DEV_MOCK.config.trialTrafficLimitGb = updates.TRIAL_TRAFFIC_LIMIT_GB;
      }
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_TRAFFIC_STRATEGY")) {
        DEV_MOCK.config.trialTrafficStrategy = updates.TRIAL_TRAFFIC_STRATEGY || "NO_RESET";
      }
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_WITHOUT_TELEGRAM_ENABLED")) {
        DEV_MOCK.config.trialWithoutTelegramEnabled = Boolean(
          updates.TRIAL_WITHOUT_TELEGRAM_ENABLED
        );
        DEV_MOCK.data.settings.trial_without_telegram_enabled = Boolean(
          updates.TRIAL_WITHOUT_TELEGRAM_ENABLED
        );
      }
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_SQUAD_UUIDS")) {
        DEV_MOCK.config.trialSquadUuids = updates.TRIAL_SQUAD_UUIDS || "";
      }
      if (Object.prototype.hasOwnProperty.call(updates, "REFERRAL_WELCOME_BONUS_DAYS")) {
        DEV_MOCK.config.referralWelcomeBonusDays = Number(updates.REFERRAL_WELCOME_BONUS_DAYS || 0);
        DEV_MOCK.data.referral.welcome_bonus_days = Number(
          updates.REFERRAL_WELCOME_BONUS_DAYS || 0
        );
      }
      if (
        Object.prototype.hasOwnProperty.call(
          updates,
          "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED"
        )
      ) {
        DEV_MOCK.config.referralWelcomeWithoutTelegramEnabled = Boolean(
          updates.REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED
        );
        DEV_MOCK.data.referral.welcome_bonus_without_telegram_enabled = Boolean(
          updates.REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED
        );
      }
      if (Object.prototype.hasOwnProperty.call(updates, "REFERRAL_ONE_BONUS_PER_REFEREE")) {
        DEV_MOCK.config.referralOneBonusPerReferee = Boolean(
          updates.REFERRAL_ONE_BONUS_PER_REFEREE
        );
        DEV_MOCK.data.referral.one_bonus_per_referee = Boolean(
          updates.REFERRAL_ONE_BONUS_PER_REFEREE
        );
      }
      if (Object.prototype.hasOwnProperty.call(updates, "LEGACY_REFS")) {
        DEV_MOCK.config.legacyRefs = Boolean(updates.LEGACY_REFS);
      }
      if (Object.prototype.hasOwnProperty.call(updates, "DISPOSABLE_EMAIL_DOMAINS")) {
        DEV_MOCK.config.disposableEmailDomains = updates.DISPOSABLE_EMAIL_DOMAINS || "";
      }
    } catch (_e) {
      void _e;
    }
    return { ok: true, applied: 1, reverted: 0 };
  }
  if (path === "/admin/translations" && String(options.method || "GET").toUpperCase() === "PATCH") {
    return { ok: true, applied: 1, reverted: 0, file_written: true };
  }
  if (path === "/admin/translations") {
    return {
      ok: true,
      path: "data/locales-overrides.json",
      override_count: 1,
      languages: [
        { code: "en", label: "English", base: true },
        { code: "ru", label: "Русский", base: true },
      ],
      groups: [
        {
          id: "webapp",
          title: "Mini App",
          description: "User-facing Mini App strings.",
          audience: "user",
          items: [
            {
              key: "wa_nav_home",
              audience: "user",
              values: {
                ru: {
                  base: "Главная",
                  fallback: "Главная",
                  effective: "Главная",
                  override: "",
                  overridden: false,
                },
                en: {
                  base: "Home",
                  fallback: "Главная",
                  effective: "Dashboard",
                  override: "Dashboard",
                  overridden: true,
                },
              },
            },
          ],
        },
        {
          id: "admin",
          title: "Admin panel",
          description: "Admin navigation and labels.",
          audience: "internal",
          items: [
            {
              key: "admin_nav_settings",
              audience: "internal",
              values: {
                ru: {
                  base: "Настройки",
                  fallback: "Настройки",
                  effective: "Настройки",
                  override: "",
                  overridden: false,
                },
                en: {
                  base: "Settings",
                  fallback: "Настройки",
                  effective: "Settings",
                  override: "",
                  overridden: false,
                },
              },
            },
          ],
        },
      ],
    };
  }
  if (path === "/admin/settings")
    return {
      ok: true,
      sections: [
        {
          id: "general",
          order: 1,
          fields: [
            {
              key: "WEBAPP_TITLE",
              type: "string",
              section: "general",
              label: "Web App title",
              value: DEV_MOCK.config.title || "",
              i18n_label_key: "admin_settings_field_webapp_title_label",
              i18n_placeholder_key: "admin_settings_field_webapp_title_placeholder",
              placeholder: "My subscription",
            },
          ],
        },
        {
          id: "appearance",
          order: 2,
          fields: [
            {
              key: "WEBAPP_LOGO_URL",
              type: "url",
              section: "appearance",
              label: "URL логотипа",
              value: DEV_MOCK.config.logoUrl || "",
            },
            {
              key: "WEBAPP_FAVICON_USE_CUSTOM",
              type: "bool",
              section: "appearance",
              label: "Custom favicon",
              value: Boolean(DEV_MOCK.config.faviconUseCustom),
            },
            {
              key: "WEBAPP_FAVICON_URL",
              type: "url",
              section: "appearance",
              label: "Favicon URL",
              value: DEV_MOCK.config.faviconUrl || "",
            },
            {
              key: "WEBAPP_LOGO_FAVICON_URL",
              type: "url",
              section: "appearance",
              label: "Logo favicon URL",
              value: DEV_MOCK.config.faviconUrl || "",
            },
          ],
        },
        {
          id: "pricing",
          order: 11,
          fields: [
            {
              key: "TRIAL_ENABLED",
              type: "bool",
              section: "pricing",
              subsection: "trial",
              label: "Триал включён",
              value: Boolean(DEV_MOCK.config.trialEnabled),
            },
            {
              key: "TRIAL_DURATION_DAYS",
              type: "int",
              section: "pricing",
              subsection: "trial",
              label: "Длительность триала (дней)",
              value: DEV_MOCK.config.trialDurationDays ?? 3,
            },
            {
              key: "TRIAL_TRAFFIC_LIMIT_GB",
              type: "float",
              section: "pricing",
              subsection: "trial",
              label: "Лимит трафика триала (ГБ)",
              value: DEV_MOCK.config.trialTrafficLimitGb ?? 5,
            },
            {
              key: "TRIAL_TRAFFIC_STRATEGY",
              type: "string",
              section: "pricing",
              subsection: "trial",
              label: "Стратегия сброса трафика триала",
              value: DEV_MOCK.config.trialTrafficStrategy || "NO_RESET",
            },
            {
              key: "TRIAL_WITHOUT_TELEGRAM_ENABLED",
              type: "bool",
              section: "pricing",
              subsection: "trial",
              label: "Триал без Telegram",
              value: DEV_MOCK.config.trialWithoutTelegramEnabled ?? true,
            },
            {
              key: "TRIAL_SQUAD_UUIDS",
              type: "string",
              section: "pricing",
              subsection: "trial",
              label: "Internal Squads для триала",
              value: DEV_MOCK.config.trialSquadUuids || "",
            },
            {
              key: "REFERRAL_WELCOME_BONUS_DAYS",
              type: "int",
              section: "pricing",
              subsection: "referral",
              label: "Приветственный бонус (дней)",
              value: DEV_MOCK.config.referralWelcomeBonusDays ?? 3,
            },
            {
              key: "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
              type: "bool",
              section: "pricing",
              subsection: "referral",
              label: "Приветственный бонус без Telegram",
              value: DEV_MOCK.config.referralWelcomeWithoutTelegramEnabled ?? true,
            },
            {
              key: "REFERRAL_ONE_BONUS_PER_REFEREE",
              type: "bool",
              section: "pricing",
              subsection: "referral",
              label: "Один бонус на приглашённого",
              value: Boolean(DEV_MOCK.config.referralOneBonusPerReferee),
            },
            {
              key: "LEGACY_REFS",
              type: "bool",
              section: "pricing",
              subsection: "referral",
              label: "Поддержка старых ref-ссылок",
              value: DEV_MOCK.config.legacyRefs ?? true,
            },
            {
              key: "DISPOSABLE_EMAIL_DOMAINS",
              type: "text",
              section: "pricing",
              subsection: "referral",
              label: "Disposable email домены",
              value: DEV_MOCK.config.disposableEmailDomains || "",
            },
            ...[
              ["MONTH_1_ENABLED", "bool", true],
              ["RUB_PRICE_1_MONTH", "float", 200],
              ["STARS_PRICE_1_MONTH", "int", 0],
              ["REFERRAL_BONUS_DAYS_INVITER_1_MONTH", "int", 3],
              ["REFERRAL_BONUS_DAYS_REFEREE_1_MONTH", "int", 1],
              ["MONTH_3_ENABLED", "bool", true],
              ["RUB_PRICE_3_MONTHS", "float", 600],
              ["STARS_PRICE_3_MONTHS", "int", 0],
              ["REFERRAL_BONUS_DAYS_INVITER_3_MONTHS", "int", 7],
              ["REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS", "int", 3],
              ["MONTH_6_ENABLED", "bool", false],
              ["RUB_PRICE_6_MONTHS", "float", 1200],
              ["STARS_PRICE_6_MONTHS", "int", 0],
              ["REFERRAL_BONUS_DAYS_INVITER_6_MONTHS", "int", 15],
              ["REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS", "int", 7],
              ["MONTH_12_ENABLED", "bool", false],
              ["RUB_PRICE_12_MONTHS", "float", 2400],
              ["STARS_PRICE_12_MONTHS", "int", 0],
              ["REFERRAL_BONUS_DAYS_INVITER_12_MONTHS", "int", 30],
              ["REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS", "int", 15],
              ["TRAFFIC_PACKAGES", "string", "10:99,50:399"],
              ["STARS_TRAFFIC_PACKAGES", "string", ""],
            ].map(([key, type, value]) => ({
              key,
              type,
              section: "pricing",
              subsection: "legacy_tariffs",
              label: key,
              value,
            })),
          ],
        },
      ],
    };
  if (cleanPath === "/admin/support/stats") {
    return {
      ok: true,
      stats: { ...supportCounts(), total_unread_admin: 2 },
    };
  }
  if (cleanPath === "/admin/support/tickets") {
    const params = new URLSearchParams(String(path || "").split("?")[1] || "");
    const tickets = filterSupportTickets(supportTickets, params);
    return { ok: true, tickets: clone(tickets), total: tickets.length };
  }
  if (cleanPath.startsWith("/admin/support/tickets/")) {
    const parts = cleanPath.split("/");
    const ticketId = Number(parts[4]);
    const ticket = clone(
      supportTickets.find((item) => item.ticket_id === ticketId) || supportTickets[0]
    );
    if (parts[5] === "messages") {
      return {
        ok: true,
        ticket,
        message: {
          message_id: Date.now(),
          ticket_id: ticket.ticket_id,
          author_role: "admin",
          author_user_id: 1,
          author_name: "Мария, поддержка",
          body: JSON.parse(options?.body || "{}")?.body || "",
          is_internal_note: Boolean(JSON.parse(options?.body || "{}")?.is_internal_note),
          created_at: new Date().toISOString(),
        },
      };
    }
    if (String(options.method || "GET").toUpperCase() === "PATCH") {
      return { ok: true, ticket: { ...ticket, ...(JSON.parse(options?.body || "{}") || {}) } };
    }
    return {
      ok: true,
      ticket,
      messages: clone([
        ...(supportMessages[ticket.ticket_id] || []),
        {
          message_id: 99,
          ticket_id: ticket.ticket_id,
          author_role: "admin",
          author_user_id: 1,
          author_name: "Мария, поддержка",
          body: "Внутренняя заметка для команды: проверить последние логи панели перед ответом.",
          is_internal_note: true,
          created_at: new Date(Date.now() - 12 * 60000).toISOString(),
        },
      ]),
      user_snapshot: {
        user_id: ticket.user_id,
        name: "Анна Смирнова",
        username: "anna_ops",
        email: "anna@example.com",
        tariff: "Standard",
        panel_status: "ACTIVE",
        remaining: "20 д. 4 ч.",
        regular_traffic: "12 GB / 500 GB",
        premium_traffic: "4 GB / 25 GB",
      },
    };
  }
  if (cleanPath.startsWith("/admin/"))
    return { ok: true, payments: [], promos: [], logs: [], campaigns: [], total: 0 };
  if (
    cleanPath === "/support/tickets" &&
    String(options.method || "GET").toUpperCase() === "POST"
  ) {
    let payload = {};
    try {
      payload = JSON.parse(options?.body || "{}");
    } catch (_error) {
      void _error;
    }
    return {
      ok: true,
      ticket: {
        ticket_id: 44,
        user_id: 100200300,
        subject: payload.subject || "Новое обращение",
        category: payload.category || "other",
        priority: payload.priority || "normal",
        status: "awaiting_admin",
        unread_user_count: 0,
        unread_admin_count: 1,
        last_message_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      },
    };
  }
  if (cleanPath === "/support/tickets") {
    const params = new URLSearchParams(String(path || "").split("?")[1] || "");
    const tickets = filterSupportTickets(supportTickets, params);
    return {
      ok: true,
      tickets: clone(tickets),
      total: tickets.length,
      counts: supportCounts(),
    };
  }
  if (cleanPath.startsWith("/support/tickets/")) {
    const parts = cleanPath.split("/");
    const ticketId = Number(parts[3]);
    const ticket = clone(
      supportTickets.find((item) => item.ticket_id === ticketId) || supportTickets[0]
    );
    if (parts[4] === "read") return { ok: true };
    if (parts[4] === "messages") {
      return {
        ok: true,
        ticket,
        message: {
          message_id: Date.now(),
          ticket_id: ticket.ticket_id,
          author_role: "user",
          author_user_id: 100200300,
          author_name: "Анна Смирнова",
          body: JSON.parse(options?.body || "{}")?.body || "",
          created_at: new Date().toISOString(),
        },
      };
    }
    return { ok: true, ticket, messages: clone(supportMessages[ticket.ticket_id] || []) };
  }
  if (cleanPath === "/support/unread") return { ok: true, unread: 1 };
  if (cleanPath === "/me") return clone(DEV_MOCK.data);
  if (path === "/subscription-guides") return clone(DEV_MOCK.data.subscription_guides);
  if (cleanPath.startsWith("/subscription-guides/public/")) {
    const shareToken = decodeURIComponent(cleanPath.split("/").pop() || "");
    const subscription = clone(DEV_MOCK.data.subscription);
    subscription.install_share_token = shareToken;
    subscription.share_url = `${window.location.origin}/s/${shareToken}`;
    return {
      ...clone(DEV_MOCK.data.subscription_guides),
      subscription,
    };
  }
  if (path === "/auth/email/request") {
    const authDemo = demoAuthConfig();
    return { ok: true, email_code: authDemo.code };
  }
  if (path === "/auth/email/verify" || path === "/auth/email/magic") {
    applyDemoEmailAuthUser();
    return { ok: true, csrf_token: "local-preview-csrf" };
  }
  if (path === "/auth/email/password") {
    const body = jsonBody(options);
    const authDemo = demoAuthConfig();
    const normalizedEmail = String(body.email || "")
      .trim()
      .toLowerCase();
    const password = String(body.password || "");
    if (
      normalizedEmail === String(authDemo.email || DEFAULT_DEMO_AUTH_EMAIL).toLowerCase() &&
      password === String(authDemo.password || DEFAULT_DEMO_AUTH_PASSWORD)
    ) {
      applyDemoEmailAuthUser();
      return { ok: true, csrf_token: "local-preview-csrf" };
    }
    return { ok: false, error: "password_login_failed", fallback: "email_code" };
  }
  if (path === "/auth/token") {
    const body = jsonBody(options);
    applyDemoTelegramAuthUser(body.auth_data || {});
    return { ok: true, csrf_token: "local-preview-csrf" };
  }
  if (path === "/promo/apply") return { ok: true, end_date_text: "31.05.2026" };
  if (
    path === "/referral/welcome-bonus/claim" &&
    String(options.method || "").toUpperCase() === "POST"
  ) {
    const days = Math.max(1, Number(DEV_MOCK.data.referral?.welcome_bonus_days || 3));
    DEV_MOCK.data.subscription = {
      ...DEV_MOCK.data.subscription,
      active: true,
      status: "ACTIVE",
      remaining_text: `${days} д.`,
      end_date_text: "05.05.2026 12:00",
      days_left: days,
      config_link: "https://sub.example.com/sub/referral-preview-token",
      connect_url: "https://sub.example.com/connect/referral-preview-token",
      panel_short_uuid: "referral-preview-token",
      install_share_token: "referral-preview-share",
      install_share_url: "https://app.example.com/s/referral-preview-share",
      traffic_limit: "10 GB",
      traffic_limit_bytes: 10737418240,
      traffic_used: "0 B",
      traffic_used_bytes: 0,
    };
    DEV_MOCK.data.referral = {
      ...(DEV_MOCK.data.referral || {}),
      welcome_bonus_requires_telegram: false,
      welcome_bonus_block_reason: "",
    };
    return {
      ok: true,
      claimed: true,
      end_date_text: "05.05.2026 12:00",
    };
  }
  if (path === "/devices") return clone(DEV_MOCK.data.devices);
  if (path === "/devices/topup-options")
    return clone(DEV_MOCK.data.device_topup_options || { ok: true, plans: [] });
  if (cleanPath === "/tariffs/topup-options") {
    const kind =
      new URLSearchParams(String(path || "").split("?")[1] || "").get("kind") || "regular";
    const payload = clone(DEV_MOCK.data.topup_options || { ok: true, plans: [] });
    payload.topup_kind = kind;
    payload.plans = (payload.plans || []).filter((plan) =>
      kind === "premium" ? plan.sale_mode === "premium_topup" : plan.sale_mode !== "premium_topup"
    );
    return payload;
  }
  if (path === "/tariffs/change-options")
    return clone(DEV_MOCK.data.tariff_change_options || { ok: true, targets: [] });
  if (path === "/devices/disconnect" && String(options.method || "").toUpperCase() === "POST") {
    let payload = {};
    try {
      payload = options?.body ? JSON.parse(String(options.body)) : {};
    } catch (_error) {
      void _error;
    }
    DEV_MOCK.data.devices.devices = DEV_MOCK.data.devices.devices.filter(
      (device) => device.token !== payload.token
    );
    DEV_MOCK.data.devices.current_devices = DEV_MOCK.data.devices.devices.length;
    return { ok: true };
  }
  if (path === "/trial/activate" && String(options.method || "").toUpperCase() === "POST") {
    if (DEV_MOCK.data.settings?.trial_requires_telegram && !DEV_MOCK.data.user?.telegram_linked) {
      return {
        ok: false,
        error: "trial_telegram_required",
        message: "telegram_required",
      };
    }
    DEV_MOCK.data.subscription = {
      ...DEV_MOCK.data.subscription,
      active: true,
      status: "TRIAL",
      remaining_text: "5 д. 0 ч.",
      end_date_text: "05.05.2026 12:00",
      days_left: 5,
      config_link: "https://sub.example.com/sub/trial-preview-token",
      connect_url: "https://sub.example.com/connect/trial-preview-token",
      panel_short_uuid: "trial-preview-token",
      install_share_token: "8f559061460e8fede78ef18dce887236",
      install_share_url: "https://app.example.com/s/8f559061460e8fede78ef18dce887236",
      traffic_limit: "10 GB",
      traffic_limit_bytes: 10737418240,
      traffic_used: "0 B",
      traffic_used_bytes: 0,
    };
    DEV_MOCK.data.settings.trial_available = false;
    return {
      ok: true,
      activated: true,
      days: 5,
      end_date_text: "05.05.2026 12:00",
      traffic_gb: 10,
      config_link: "https://sub.example.com/sub/trial-preview-token",
      connect_url: "https://sub.example.com/connect/trial-preview-token",
    };
  }
  if (path === "/auth/logout") return { ok: true };
  if (path === "/account/language" && String(options.method || "").toUpperCase() === "POST") {
    let payload = {};
    try {
      payload = options?.body ? JSON.parse(String(options.body)) : {};
    } catch (_error) {
      void _error;
    }
    const language = normalizeLangCode(payload?.language || currentLang);
    DEV_MOCK.data.user.language_code = language;
    DEV_MOCK.data.settings.subscription_purchase_description =
      language === "en"
        ? "By buying or renewing a subscription, you get access to a VPN/proxy service that helps protect your connection and keep your access stable."
        : "Покупая или продлевая подписку, вы получаете доступ к VPN/прокси-сервису, который помогает защищать ваше соединение и поддерживать стабильный доступ к сети.";
    return { ok: true, language };
  }
  if (path === "/account/email/request" && String(options.method || "").toUpperCase() === "POST") {
    const authDemo = demoAuthConfig();
    return { ok: true, email_code: authDemo.code };
  }
  if (path === "/account/email/verify" && String(options.method || "").toUpperCase() === "POST") {
    applyDemoEmailLink(demoAuthConfig().email);
    return { ok: true, csrf_token: "local-preview-csrf" };
  }
  if (
    path === "/account/password/request" &&
    String(options.method || "").toUpperCase() === "POST"
  ) {
    return { ok: true };
  }
  if (
    path === "/account/password/confirm" &&
    String(options.method || "").toUpperCase() === "POST"
  ) {
    DEV_MOCK.data.user.password_auth_enabled = true;
    return { ok: true, password_auth_enabled: true };
  }
  if (path === "/account/telegram/link" && String(options.method || "").toUpperCase() === "POST") {
    const body = jsonBody(options);
    applyDemoTelegramLink(body.auth_data || {});
    return { ok: true, csrf_token: "local-preview-csrf" };
  }
  if (
    path === "/account/telegram/notifications/probe" &&
    String(options.method || "").toUpperCase() === "POST"
  ) {
    DEV_MOCK.data.user = {
      ...(DEV_MOCK.data.user || {}),
      telegram_notifications_status: "enabled",
      telegram_notifications_enabled: true,
      telegram_notifications_need_prompt: false,
      telegram_notifications_start_link: "https://t.me/preview_bot?start=notifications",
    };
    return {
      ok: true,
      telegram_notifications: {
        ok: true,
        status: "enabled",
        enabled: true,
        start_link: "https://t.me/preview_bot?start=notifications",
      },
    };
  }
  if (path === "/payments" && String(options.method || "").toUpperCase() === "POST") {
    const body = jsonBody(options);
    if (isDeviceTopupSaleMode(body.sale_mode)) {
      const plan = demoDeviceTopupPlan(body);
      const deviceCount = Number(
        body.device_count || plan?.device_count || plan?.purchased_hwid_devices || body.months || 1
      );
      const paymentId = ++demoPaymentSequence;
      demoPaymentStatuses.set(String(paymentId), {
        status: "pending_yookassa",
        paid: false,
        sale_mode: body.sale_mode || "hwid_devices",
        device_count: deviceCount,
        applied: false,
      });
      return {
        ok: true,
        action: "invoice_sent",
        payment_id: paymentId,
      };
    }
    return {
      ok: true,
      action: "open_link",
      payment_url: "https://example.com/payment-preview",
      payment_id: 10001,
    };
  }
  if (/^\/payments\/\d+$/.test(path) && String(options.method || "GET").toUpperCase() === "GET") {
    const paymentId = String(path.split("/").pop());
    const status = demoPaymentStatuses.get(paymentId);
    if (status) {
      if (!status.applied && isDeviceTopupSaleMode(status.sale_mode)) {
        applyDemoDeviceTopup(status.device_count);
        status.applied = true;
      }
      status.status = "succeeded";
      status.paid = true;
      return {
        ok: true,
        payment_id: Number(paymentId),
        status: status.status,
        paid: status.paid,
      };
    }
    return {
      ok: true,
      payment_id: Number(path.split("/").pop()),
      status: "pending_yookassa",
      paid: false,
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
