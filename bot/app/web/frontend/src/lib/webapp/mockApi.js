import { DEV_MOCK } from "./previewMock.js";

function defaultClone(value) {
  try {
    return structuredClone(value);
  } catch {
    return JSON.parse(JSON.stringify(value));
  }
}

export async function mockApi(path, options = {}, context = {}) {
  const {
    currentLang = "ru",
    normalizeLangCode = (value) => value || "ru",
    clone = defaultClone,
  } = context;
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
      premium_traffic: {
        state: "good",
        unlimited: false,
        used_bytes: 4 * 1073741824,
        limit_bytes: 25 * 1073741824,
        percent: 16,
      },
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
    },
  ];
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
  if (path === "/admin/stats") {
    return {
      ok: true,
      currency_symbol: "RUB",
      users: { total_users: 248, active_subscriptions: 172, banned_users: 3 },
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
      recent_payments: [
        {
          payment_id: 1,
          user_id: 100200300,
          user_label: "anna_ops",
          amount: 790,
          currency: "RUB",
          provider: "yookassa",
          status: "succeeded",
          created_at: new Date().toISOString(),
        },
      ],
    };
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
  if (path === "/admin/settings") return { ok: true, sections: [] };
  if (cleanPath.startsWith("/admin/"))
    return { ok: true, payments: [], promos: [], logs: [], campaigns: [], total: 0 };
  if (path === "/me") return clone(DEV_MOCK.data);
  if (path === "/auth/email/request") return { ok: true };
  if (path === "/auth/email/verify" || path === "/auth/email/magic") {
    return { ok: true, token: "local-preview", csrf_token: "local-preview-csrf" };
  }
  if (path === "/auth/token") {
    return { ok: true, token: "local-preview", csrf_token: "local-preview-csrf" };
  }
  if (path === "/promo/apply") return { ok: true, end_date_text: "31.05.2026" };
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
    } catch (_error) {
      void _error;
    }
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
