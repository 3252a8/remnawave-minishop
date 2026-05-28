import { DEV_MOCK } from "./previewMock.js";
import { DEMO_DATASET } from "./demoDataset.js";

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
const demoSettingsChanges = new Map();

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

function filterDemoUsers(params) {
  let out = [...(DEMO_DATASET.adminUsers || [])];
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

function demoSettingsSections(clone) {
  const sections = clone(DEMO_DATASET.settingsSections || []);
  for (const section of sections) {
    for (const field of section.fields || []) {
      if (!demoSettingsChanges.has(field.key)) continue;
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
  return sections;
}

function applyDemoSettingToMock(key, value) {
  if (key === "WEBAPP_TITLE") DEV_MOCK.config.title = value || "";
  if (key === "WEBAPP_LOGO_URL") DEV_MOCK.config.logoUrl = value || "";
  if (key === "WEBAPP_LOGO_USE_EMOJI") DEV_MOCK.config.logoUseEmoji = Boolean(value);
  if (key === "WEBAPP_LOGO_EMOJI") DEV_MOCK.config.logoEmoji = value || "";
  if (key === "WEBAPP_LOGO_EMOJI_FONT") DEV_MOCK.config.logoEmojiFont = value || "system";
  if (key === "WEBAPP_FAVICON_URL" || key === "WEBAPP_LOGO_FAVICON_URL") {
    DEV_MOCK.config.faviconUrl = value || DEV_MOCK.config.faviconUrl || "";
  }
  if (key === "WEBAPP_FAVICON_USE_CUSTOM") DEV_MOCK.config.faviconUseCustom = Boolean(value);
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
      users: clone(page.items),
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
    if (parts[4]) {
      if (parts[4] === "telegram-profile-link") {
        return { ok: true, url: `https://t.me/${detail.user?.username || "demo_user"}` };
      }
      if (parts[4] === "message" && parts[5] === "preview") {
        return { ok: true, text: "Demo broadcast preview for the selected account." };
      }
      return { ok: true, user: clone(detail.user), detail: clone(detail) };
    }
    return clone(detail);
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
    return { ok: true, tickets: clone(page.items), total: page.total };
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
      return { ok: true, ticket: clone(ticket), message: clone(message) };
    }
    if (method === "PATCH") {
      Object.assign(ticket, jsonBody(options));
      return { ok: true, ticket: clone(ticket) };
    }
    return {
      ok: true,
      ticket: clone(ticket),
      messages: clone(messages),
      user_snapshot: userSnapshotForTicket(ticket),
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
      tickets: clone(page.items),
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
      return { ok: true, ticket: clone(ticket), message: clone(message) };
    }
    return { ok: true, ticket: clone(ticket), messages: clone(messages) };
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
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_SQUAD_UUIDS")) {
        DEV_MOCK.config.trialSquadUuids = updates.TRIAL_SQUAD_UUIDS || "";
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
              key: "TRIAL_SQUAD_UUIDS",
              type: "string",
              section: "pricing",
              subsection: "trial",
              label: "Internal Squads для триала",
              value: DEV_MOCK.config.trialSquadUuids || "",
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
