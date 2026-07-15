import { DEV_MOCK } from "../previewMock.js";
import { withDemoAvatarTicket } from "../demoAvatars.js";
import { jsonBody, paged, queryParams, writeDemoLanguage } from "../demoMockRuntime.js";
import { DATASET, defaultClone, type DemoRecord, type MockApiContext } from "./dataset";
import { demoProviderCurrencySupport } from "./providers";
import { demoSettingsSections, persistDemoSettings } from "./settings";
import {
  demoAds,
  demoPromos,
  demoSettingsChanges,
  demoSupportMessages,
  demoSupportTickets,
  demoTariffs,
  setDemoAds,
  setDemoPromos,
  setDemoTariffs,
} from "./state";
import { demoTranslationsPayload } from "./translations";
import {
  demoInviteesForUser,
  demoSupportCounts,
  filterDemoSupportTickets,
  filterDemoUsers,
  userName,
  userSnapshotForTicket,
  withDemoAvatarTickets,
  withDemoAvatars,
  withDemoReferralSummary,
} from "./users";

const DEMO_SHORTCODE_META: [string, string, string][] = [
  ["first_name", "db", "First name"],
  ["last_name", "db", "Last name"],
  ["username", "db", "@username"],
  ["user_id", "db", "User ID"],
  ["email", "db", "User email"],
  ["end_date", "db", "Subscription end date"],
  ["days_left", "db", "Days until expiry"],
  ["subscription_status", "db", "Subscription status"],
  ["tariff_name", "db", "Tariff name"],
  ["tariff_price", "db", "Tariff price"],
  ["traffic_used", "db", "Traffic used, GB"],
  ["traffic_limit", "db", "Traffic limit, GB"],
  ["traffic_left", "db", "Traffic left, GB"],
  ["install_link", "db", "Connection guide link"],
  ["miniapp_link", "db", "Mini App link"],
  ["config_link", "panel", "Subscription key link"],
  ["referral_code", "db", "Referral code"],
  ["referral_bot_link", "db", "Referral link (bot)"],
  ["referral_webapp_link", "db", "Referral link (Mini App)"],
];

const DEMO_SHORTCODE_VALUES: Record<string, string> = {
  first_name: "Alex",
  last_name: "Petrov",
  username: "@alex",
  user_id: "100245",
  email: "alex@example.com",
  end_date: "2030-05-01",
  days_left: "42",
  subscription_status: "active",
  tariff_name: "Premium",
  tariff_price: "299 RUB",
  traffic_used: "30",
  traffic_limit: "100",
  traffic_left: "70",
  install_link: "https://app.example/s/demo",
  miniapp_link: "https://app.example/",
  config_link: "happ://crypt4/demo",
  referral_code: "AB12CD",
  referral_bot_link: "https://t.me/demo_bot?start=ref_uAB12CD",
  referral_webapp_link: "https://app.example/?ref=uAB12CD",
};

function demoBroadcastShortcodes(): { shortcodes: DemoRecord[]; allowed_tags: string[] } {
  return {
    shortcodes: DEMO_SHORTCODE_META.map(([name, cost, description]) => ({
      name,
      cost,
      description,
    })),
    allowed_tags: ["b", "i", "u", "s", "code", "a", "pre", "blockquote"],
  };
}

function renderDemoShortcodes(text: string): { text: string; unknown: string[] } {
  const unknown = new Set<string>();
  const rendered = text.replace(/\{([a-z_][a-z0-9_]*)\}/g, (whole, name: string) => {
    if (name in DEMO_SHORTCODE_VALUES) return DEMO_SHORTCODE_VALUES[name];
    unknown.add(name);
    return whole;
  });
  return { text: rendered, unknown: [...unknown] };
}

export function demoApiResponse(
  path: string,
  cleanPath: string,
  options: RequestInit,
  context: MockApiContext
): unknown {
  const {
    clone = defaultClone,
    currentLang = "ru",
    normalizeLangCode = (value: unknown) => String(value || "ru"),
  } = context;
  const method = String(options.method || "GET").toUpperCase();
  const params = queryParams(path);

  if (cleanPath === "/admin/stats") return clone(DATASET.stats);
  if (cleanPath === "/admin/broadcast/audience-counts") {
    return {
      ok: true,
      counts: { all: 1280, active: 742, inactive: 538, expired: 311, never: 227, admins: 2 },
      email_enabled: true,
    };
  }
  if (cleanPath === "/admin/broadcast" && method === "POST") {
    const body = jsonBody(options);
    const channels = Array.isArray(body.channels) ? body.channels : ["telegram"];
    const target = String(body.target || "all");
    const queued = channels.includes("telegram") ? (target === "admins" ? 2 : 1280) : 0;
    const emailQueued = channels.includes("email") ? (target === "admins" ? 1 : 486) : 0;
    return {
      ok: true,
      queued,
      failed: 0,
      email_queued: emailQueued,
      target,
      channels,
    };
  }
  if (cleanPath === "/admin/broadcast/shortcodes") {
    return { ok: true, ...demoBroadcastShortcodes() };
  }
  if (cleanPath === "/admin/broadcast/preview" && method === "POST") {
    const body = jsonBody(options);
    const rendered = renderDemoShortcodes(String(body.text || ""));
    const subjectRaw = String(body.email_subject || "");
    return {
      ok: true,
      rendered_text: rendered.text,
      rendered_subject: subjectRaw ? renderDemoShortcodes(subjectRaw).text : null,
      unknown_shortcodes: rendered.unknown,
      length: rendered.text.length,
      sent: String(body.mode || "render") === "send_telegram",
    };
  }
  if (cleanPath === "/admin/sync") return { ok: true, status: "queued" };

  if (cleanPath === "/admin/health") {
    return {
      ok: true,
      alerts: [
        {
          id: "provider_not_configured:wata",
          severity: "error",
          sections: ["settings"],
          message_key: "provider_not_configured",
          params: { provider: "Wata" },
        },
        {
          id: "mini_app_url_missing",
          severity: "warning",
          sections: ["settings"],
          message_key: "mini_app_url_missing",
          params: {},
        },
      ],
      checked_at: new Date().toISOString(),
    };
  }

  if (cleanPath === "/admin/payments") {
    const page = paged(DATASET.adminPayments || [], params, 25);
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
    const payment = (DATASET.adminPayments || []).find((item) => item.payment_id === id);
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
    const detail = DATASET.adminUserDetails?.[String(id)];
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
    let logs = [...(DATASET.adminLogs || [])];
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
      setDemoPromos(demoPromos().filter((item) => item.id !== id));
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
    return { ok: true, campaigns: clone(demoAds()), totals: clone(DATASET.adsTotals || {}) };
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
      setDemoAds(demoAds().filter((item) => item.id !== id));
      return { ok: true };
    }
    return { ok: true, campaign: clone(campaign) };
  }

  if (cleanPath === "/admin/backups") return clone(DATASET.backups);
  if (cleanPath === "/admin/backups/create") {
    const archive = clone(DATASET.backups?.archives?.[0] || {}) as DemoRecord;
    archive.name = `minishop-demo-${Date.now()}.zip`;
    archive.created_at = new Date().toISOString();
    return {
      ok: true,
      archive,
      result: { archive_name: archive.name, completed_at: archive.created_at, warnings: [] },
    };
  }
  if (cleanPath === "/admin/backups/upload") {
    return { ok: true, archive: clone(DATASET.backups?.archives?.[0] || {}) };
  }
  if (cleanPath === "/admin/backups/restore") {
    return {
      ok: true,
      result: {
        archive_name: DATASET.backups?.archives?.[0]?.name || "demo.zip",
        database_restored: true,
        warnings: [],
      },
    };
  }

  if (cleanPath === "/admin/settings" && method === "PATCH") {
    const body = jsonBody(options);
    const deletes = (body.deletes || []) as string[];
    for (const key of deletes) demoSettingsChanges.set(key, { deleted: true });
    persistDemoSettings((body.updates || {}) as DemoRecord);
    return {
      ok: true,
      applied: Object.keys((body.updates || {}) as DemoRecord).length,
      reverted: deletes.length,
    };
  }
  if (cleanPath === "/admin/settings")
    return { ok: true, sections: demoSettingsSections(clone), features: [] };

  if (cleanPath === "/admin/tariffs") {
    if (method === "PUT") {
      const body = jsonBody(options);
      const catalog = body.catalog || body;
      setDemoTariffs(defaultClone(catalog) as DemoRecord);
    }
    return {
      ok: true,
      path: "data/tariffs.json",
      catalog: clone(demoTariffs()),
      provider_currency_support: demoProviderCurrencySupport(),
    };
  }

  if (cleanPath === "/admin/panel/internal-squads") {
    return {
      ok: true,
      squads: clone(
        DATASET.panelSquads || [
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
    return { ok: true, ...demoTranslationsPayload(clone) };
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
    if (parts[5] === "typing") return { ok: true };
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
        read_by_user_at: null,
        read_by_admin_at: null,
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
      user_snapshot: userSnapshotForTicket(withDemoAvatarTicket(ticket) as typeof ticket),
      peer_typing: false,
    };
  }

  if (cleanPath === "/support/tickets" && method === "POST") {
    const body = jsonBody(options);
    const user = (DEV_MOCK.data.user || {}) as import("./dataset").DemoAdminUser;
    const ticket = {
      ticket_id: 4900 + demoSupportTickets().length + 1,
      user_id: (user.user_id || user.id) as number,
      subject: String(body.subject || "Новое обращение в поддержку"),
      category: String(body.category || "other"),
      priority: String(body.priority || "normal"),
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
        read_by_user_at: null,
        read_by_admin_at: null,
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
    if (parts[4] === "typing") return { ok: true };
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
        read_by_user_at: null,
        read_by_admin_at: null,
      };
      messages.push(message);
      demoSupportMessages()[String(ticketId)] = messages;
      ticket.last_message_at = message.created_at;
      ticket.last_message_role = "user";
      ticket.status = "awaiting_admin";
      return { ok: true, ticket: clone(withDemoAvatarTicket(ticket)), message: clone(message) };
    }
    return {
      ok: true,
      ticket: clone(withDemoAvatarTicket(ticket)),
      messages: clone(messages),
      peer_typing: false,
    };
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
