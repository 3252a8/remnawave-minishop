import { DEV_MOCK } from "../previewMock.js";
import { jsonBody } from "../demoMockRuntime.js";
import {
  DEFAULT_DEMO_AUTH_EMAIL,
  DEFAULT_DEMO_AUTH_PASSWORD,
  applyDemoEmailAuthUser,
  applyDemoEmailLink,
  applyDemoTelegramAuthUser,
  applyDemoTelegramLink,
  demoAuthConfig,
} from "./authDemo";
import { defaultClone, type DemoRecord, type MockApiContext } from "./dataset";
import { applyDemoDeviceTopup, demoDeviceTopupPlan } from "./deviceTopup";
import type { AdminDemoFixtures } from "./adminFixtures";
import { demoPaymentStatuses, isDeviceTopupSaleMode, nextDemoPaymentId } from "./state";

/**
 * User-facing fallback responses for the docs demo / preview. Always returns a
 * value; unmatched paths resolve to `{ ok: false, error: "not_found" }`.
 */
export function webappFallbackResponse(
  path: string,
  cleanPath: string,
  options: RequestInit,
  context: MockApiContext,
  fixtures: AdminDemoFixtures
): unknown {
  const {
    clone = defaultClone,
    currentLang = "ru",
    normalizeLangCode = (value: unknown) => String(value || "ru"),
  } = context;
  const method = String(options.method || "GET").toUpperCase();
  const { supportTickets, supportMessages, supportCounts, filterSupportTickets } = fixtures;

  if (cleanPath === "/support/tickets" && method === "POST") {
    let payload: DemoRecord = {};
    try {
      payload = JSON.parse(String(options?.body || "{}")) as DemoRecord;
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
    if (parts[4] === "typing") return { ok: true };
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
          body: (JSON.parse(String(options?.body || "{}")) as DemoRecord)?.body || "",
          created_at: new Date().toISOString(),
          read_by_user_at: null,
          read_by_admin_at: null,
        },
      };
    }
    return {
      ok: true,
      ticket,
      messages: clone(supportMessages[Number(ticket.ticket_id)] || []),
      peer_typing: false,
    };
  }
  if (cleanPath === "/support/unread") return { ok: true, unread: 1 };
  if (cleanPath === "/subscription/auto-renew" && method === "POST") {
    const body = jsonBody(options);
    const enabled = Boolean(body.enabled);
    DEV_MOCK.data.subscription = {
      ...(DEV_MOCK.data.subscription || {}),
      auto_renew_enabled: enabled,
      auto_renew_available: true,
      auto_renew_can_enable: true,
      auto_renew_provider_label:
        DEV_MOCK.data.subscription?.auto_renew_provider_label || "CloudPayments",
      provider: DEV_MOCK.data.subscription?.provider || "cloudpayments",
    };
    return {
      ok: true,
      auto_renew_enabled: enabled,
      provider: DEV_MOCK.data.subscription.provider,
      provider_label: DEV_MOCK.data.subscription.auto_renew_provider_label,
    };
  }
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
    applyDemoTelegramAuthUser((body.auth_data || {}) as DemoRecord);
    return { ok: true, csrf_token: "local-preview-csrf" };
  }
  if (path === "/promo/apply") return { ok: true, end_date_text: "31.05.2026" };
  if (path === "/promo/status") {
    const body = jsonBody(options);
    return {
      ok: true,
      status: "standalone",
      code: String(body.code || "DEMO"),
      message: "",
      effect_summary: "+7 дней",
      applies_to: "all",
      min_subscription_months: null,
      min_traffic_gb: null,
      bonus_days: 7,
      end_date_text: null,
    };
  }
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
    const payload = clone(DEV_MOCK.data.topup_options || { ok: true, plans: [] }) as DemoRecord & {
      plans?: (DemoRecord & { sale_mode?: unknown })[];
    };
    payload.topup_kind = kind;
    payload.plans = (payload.plans || []).filter((plan) =>
      kind === "premium" ? plan.sale_mode === "premium_topup" : plan.sale_mode !== "premium_topup"
    );
    return payload;
  }
  if (path === "/tariffs/change-options")
    return clone(DEV_MOCK.data.tariff_change_options || { ok: true, targets: [] });
  if (path === "/devices/disconnect" && String(options.method || "").toUpperCase() === "POST") {
    let payload: DemoRecord = {};
    try {
      payload = options?.body ? (JSON.parse(String(options.body)) as DemoRecord) : {};
    } catch (_error) {
      void _error;
    }
    const devicesHost = DEV_MOCK.data.devices as DemoRecord & {
      devices: (DemoRecord & { token?: unknown })[];
    };
    devicesHost.devices = devicesHost.devices.filter((device) => device.token !== payload.token);
    devicesHost.current_devices = devicesHost.devices.length;
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
    let payload: DemoRecord = {};
    try {
      payload = options?.body ? (JSON.parse(String(options.body)) as DemoRecord) : {};
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
    applyDemoTelegramLink((body.auth_data || {}) as DemoRecord);
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
      const paymentId = nextDemoPaymentId();
      demoPaymentStatuses.set(String(paymentId), {
        status: "pending_yookassa",
        paid: false,
        sale_mode: String(body.sale_mode || "hwid_devices"),
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
