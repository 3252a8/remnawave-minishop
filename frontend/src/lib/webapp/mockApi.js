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
      if (Object.prototype.hasOwnProperty.call(updates, "WEBAPP_LOGO_USE_EMOJI")) {
        DEV_MOCK.config.logoUseEmoji = Boolean(updates.WEBAPP_LOGO_USE_EMOJI);
      }
      if (updates.WEBAPP_LOGO_EMOJI) DEV_MOCK.config.logoEmoji = updates.WEBAPP_LOGO_EMOJI;
      if (updates.WEBAPP_LOGO_EMOJI_FONT) {
        DEV_MOCK.config.logoEmojiFont = updates.WEBAPP_LOGO_EMOJI_FONT;
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
    } catch (_e) {
      void _e;
    }
    return { ok: true, applied: 1, reverted: 0 };
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
              key: "WEBAPP_LOGO_USE_EMOJI",
              type: "bool",
              section: "appearance",
              label: "Emoji logo",
              value: Boolean(DEV_MOCK.config.logoUseEmoji),
            },
            {
              key: "WEBAPP_LOGO_URL",
              type: "url",
              section: "appearance",
              label: "URL логотипа",
              value: DEV_MOCK.config.logoUrl || "",
            },
            {
              key: "WEBAPP_LOGO_EMOJI",
              type: "string",
              section: "appearance",
              label: "Emoji",
              value: DEV_MOCK.config.logoEmoji || "🫥",
            },
            {
              key: "WEBAPP_LOGO_EMOJI_FONT",
              type: "string",
              section: "appearance",
              label: "Emoji font",
              value: DEV_MOCK.config.logoEmojiFont || "system",
              choices: [
                { value: "system", label: "Системный" },
                { value: "noto-color", label: "Noto Color Emoji" },
                { value: "noto-color-animated", label: "Noto Color Emoji Animated" },
              ],
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
              value: true,
            },
            {
              key: "TRIAL_DURATION_DAYS",
              type: "int",
              section: "pricing",
              subsection: "trial",
              label: "Длительность триала (дней)",
              value: 3,
            },
            {
              key: "TRIAL_TRAFFIC_LIMIT_GB",
              type: "float",
              section: "pricing",
              subsection: "trial",
              label: "Лимит трафика триала (ГБ)",
              value: 5,
            },
            {
              key: "TRIAL_TRAFFIC_STRATEGY",
              type: "string",
              section: "pricing",
              subsection: "trial",
              label: "Стратегия сброса трафика триала",
              value: "NO_RESET",
            },
            {
              key: "TRIAL_SQUAD_UUIDS",
              type: "string",
              section: "pricing",
              subsection: "trial",
              label: "Internal Squads для триала",
              value: "2f2f6e0a-1f2d-4e80-a33b-0ebf3a409012",
            },
            ...[
              ["MONTH_1_ENABLED", "bool", true],
              ["RUB_PRICE_1_MONTH", "float", 150],
              ["STARS_PRICE_1_MONTH", "int", 0],
              ["MONTH_3_ENABLED", "bool", true],
              ["RUB_PRICE_3_MONTHS", "float", 400],
              ["STARS_PRICE_3_MONTHS", "int", 0],
              ["MONTH_6_ENABLED", "bool", false],
              ["RUB_PRICE_6_MONTHS", "float", 750],
              ["STARS_PRICE_6_MONTHS", "int", 0],
              ["MONTH_12_ENABLED", "bool", false],
              ["RUB_PRICE_12_MONTHS", "float", 1200],
              ["STARS_PRICE_12_MONTHS", "int", 0],
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
  if (path === "/me") return clone(DEV_MOCK.data);
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
  if (path === "/auth/email/request") return { ok: true };
  if (path === "/auth/email/verify" || path === "/auth/email/magic") {
    return { ok: true, csrf_token: "local-preview-csrf" };
  }
  if (path === "/auth/email/password") {
    return { ok: false, error: "password_login_failed", fallback: "email_code" };
  }
  if (path === "/auth/token") {
    return { ok: true, csrf_token: "local-preview-csrf" };
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
    return { ok: true };
  }
  if (path === "/account/email/verify" && String(options.method || "").toUpperCase() === "POST") {
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
    return { ok: true, csrf_token: "local-preview-csrf" };
  }
  if (path === "/payments" && String(options.method || "").toUpperCase() === "POST") {
    return {
      ok: true,
      action: "open_link",
      payment_url: "https://example.com/payment-preview",
      payment_id: 10001,
    };
  }
  if (/^\/payments\/\d+$/.test(path) && String(options.method || "GET").toUpperCase() === "GET") {
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
