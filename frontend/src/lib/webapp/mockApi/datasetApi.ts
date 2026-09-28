import { adminBroadcastDemoResponse } from "./adminBroadcasts";
import { loadDemoDocuments, storeDemoDocuments } from "./documentsState";
import { DEV_MOCK } from "../previewMock.js";
import { adminGiftDemoStats } from "./giftsDemo";
import { withDemoAvatarTicket } from "../demoAvatars.js";
import { jsonBody, paged, queryParams, writeDemoLanguage } from "../demoMockRuntime.js";
import { DATASET, defaultClone, type DemoRecord, type MockApiContext } from "./dataset";
import {
  adminDemoBalance,
  applyDemoBalanceAdjustment,
  applyDemoBalanceConversion,
} from "./balance";
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
import { sortAdminRows, type AdminSortColumn, type AdminSortValue } from "$lib/admin/tableSort.js";
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

const demoInformationPages = new Map<string, string>();
const demoDocuments = loadDemoDocuments();

function demoSortValue(value: unknown): AdminSortValue {
  if (value == null || typeof value === "string" || typeof value === "number") return value;
  if (typeof value === "boolean" || value instanceof Date) return value;
  return String(value);
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

  if (cleanPath === "/admin/stats") {
    const stats = clone(DATASET.stats) as DemoRecord;
    return { ...stats, financial: { ...(stats.financial as DemoRecord), ...adminGiftDemoStats() } };
  }
  const broadcastResponse = adminBroadcastDemoResponse({
    cleanPath,
    method,
    options,
    params,
    clone,
  });
  if (broadcastResponse !== undefined) return broadcastResponse;
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
      panel_compatibility: {
        version: "3.4.4",
        generation: "rw3-numeric-user-id",
        support_status: "current",
        certified_versions: [
          "3.4.4",
          "3.4.3",
          "3.4.2",
          "3.4.1",
          "3.3.2",
          "3.3.0",
          "3.2.3",
          "3.2.1",
          "3.2.0",
          "3.1.0",
          "3.0.0",
        ],
        capabilities: ["numeric-user-ids", "user-stream"],
        observed_capabilities: {},
      },
    };
  }

  if (cleanPath === "/admin/payments") {
    const query = (params.get("search") || "")
      .trim()
      .replace(/^[@#]+/, "")
      .toLowerCase();
    const payments = (DATASET.adminPayments || []).filter((payment) => {
      if (!query) return true;
      const user = (DATASET.adminUsers || []).find((item) => item.user_id === payment.user_id);
      return (
        String(payment.user_id) === query ||
        String(user?.telegram_id) === query ||
        [
          payment.user_label,
          user?.username,
          user?.email,
          [user?.first_name, user?.last_name].filter(Boolean).join(" "),
        ].some((value) =>
          String(value || "")
            .toLowerCase()
            .includes(query)
        )
      );
    });
    const sort = params.get("sort") || "date_desc";
    const sorted = sortAdminRows(payments, sort, [
      {
        asc: "id_asc",
        desc: "id_desc",
        defaultDirection: "desc",
        value: (row) => row.payment_id as number,
      },
      {
        asc: "user_asc",
        desc: "user_desc",
        defaultDirection: "asc",
        value: (row) => row.user_label as string,
      },
      {
        asc: "user_id_asc",
        desc: "user_id_desc",
        defaultDirection: "desc",
        value: (row) => row.user_id as number,
      },
      {
        asc: "traffic_regular_asc",
        desc: "traffic_regular_desc",
        defaultDirection: "desc",
        value: (row) => row.traffic_regular_gb as number | null,
      },
      {
        asc: "traffic_premium_asc",
        desc: "traffic_premium_desc",
        defaultDirection: "desc",
        value: (row) => row.traffic_premium_gb as number | null,
      },
      {
        asc: "amount_asc",
        desc: "amount_desc",
        defaultDirection: "desc",
        value: (row) => row.amount as number,
      },
      {
        asc: "provider_asc",
        desc: "provider_desc",
        defaultDirection: "asc",
        value: (row) => row.provider as string,
      },
      {
        asc: "description_asc",
        desc: "description_desc",
        defaultDirection: "asc",
        value: (row) => row.description as string,
      },
      {
        asc: "status_asc",
        desc: "status_desc",
        defaultDirection: "asc",
        value: (row) => row.status as string,
      },
      {
        asc: "date_asc",
        desc: "date_desc",
        defaultDirection: "desc",
        value: (row) => row.created_at as string,
      },
    ] satisfies AdminSortColumn<(typeof payments)[number]>[]);
    const page = paged(sorted, params, 25);
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
    const decoratedDetail = {
      ...withDemoReferralSummary(detail),
      panel_user_url: detail.panel_user_url || "https://panel.example.com/dashboard/open/user/77",
      balance: clone(adminDemoBalance(id)),
      notification_preferences: detail.notification_preferences || {
        marketing_email: false,
        marketing_telegram: true,
        system_email: true,
        system_telegram: true,
      },
    };
    if (parts[4]) {
      if (parts[4] === "tariff" && method === "POST") {
        const tariffKey = String(jsonBody(options).tariff_key || "");
        const tariff = ((demoTariffs().tariffs || []) as DemoRecord[]).find(
          (item) => item.key === tariffKey && item.billing_model === "period"
        );
        if (!tariff || !detail.active_subscription) {
          return { ok: false, error: "invalid_tariff" };
        }
        const subscription = detail.active_subscription;
        subscription.tariff_key = tariffKey;
        if (jsonBody(options).apply_tariff_hwid_limit) {
          subscription.hwid_device_limit = tariff.hwid_device_limit ?? null;
        }
        return { ok: true, subscription: clone(subscription) };
      }
      if (parts[4] === "notification-preferences" && method === "PATCH") {
        const notificationPreferences = jsonBody(options);
        detail.notification_preferences = notificationPreferences;
        return { ok: true, notification_preferences: clone(notificationPreferences) };
      }
      if (parts[4] === "referrals") {
        const invitees = demoInviteesForUser(id);
        const sort = params.get("sort") || "registration_desc";
        const page = paged(
          sortAdminRows(invitees, sort, [
            { asc: "user_asc", desc: "user_desc", defaultDirection: "asc", value: userName },
            {
              asc: "id_asc",
              desc: "id_desc",
              defaultDirection: "desc",
              value: (row) => row.user_id,
            },
            {
              asc: "registration_asc",
              desc: "registration_desc",
              defaultDirection: "desc",
              value: (row) => row.registration_date,
            },
          ] satisfies AdminSortColumn<(typeof invitees)[number]>[]),
          params,
          25
        );
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
      if (parts[4] === "balance-adjustment" && method === "POST") {
        return { ok: true, balance: clone(applyDemoBalanceAdjustment(id, jsonBody(options))) };
      }
      if (parts[4] === "balance-conversion" && method === "POST") {
        return { ok: true, balance: clone(applyDemoBalanceConversion(id, jsonBody(options))) };
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
    const sort = params.get("sort") || "date_desc";
    logs = sortAdminRows(logs, sort, [
      {
        asc: "date_asc",
        desc: "date_desc",
        defaultDirection: "desc",
        value: (row) => row.timestamp as string,
      },
      {
        asc: "event_asc",
        desc: "event_desc",
        defaultDirection: "asc",
        value: (row) => row.event_type as string,
      },
      {
        asc: "user_asc",
        desc: "user_desc",
        defaultDirection: "asc",
        value: (row) => (row.user_label || row.user_id) as string | number,
      },
      {
        asc: "target_asc",
        desc: "target_desc",
        defaultDirection: "asc",
        value: (row) => (row.target_user_label || row.target_user_id) as string | number,
      },
      {
        asc: "content_asc",
        desc: "content_desc",
        defaultDirection: "asc",
        value: (row) => row.content as string,
      },
    ] satisfies AdminSortColumn<(typeof logs)[number]>[]);
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
    const now = Date.now();
    const search = String(params.get("search") || "")
      .trim()
      .toLowerCase();
    const status = String(params.get("status") || "")
      .trim()
      .toLowerCase();
    const scope = String(params.get("scope") || "")
      .trim()
      .toLowerCase();
    const kind = String(params.get("kind") || "")
      .trim()
      .toLowerCase();
    const allPromos = demoPromos();
    const promos = allPromos.filter((promo) => {
      if (
        search &&
        !String(promo.code || "")
          .toLowerCase()
          .includes(search)
      )
        return false;
      if (scope && String(promo.applies_to || "all").toLowerCase() !== scope) return false;
      if (kind === "personal" && !promo.user_id) return false;
      if (kind === "shared" && promo.user_id) return false;
      const expired = Boolean(promo.valid_until) && Date.parse(String(promo.valid_until)) <= now;
      const usedUp = Number(promo.current_activations || 0) >= Number(promo.max_activations || 0);
      if (status === "disabled") return promo.is_active === false;
      if (status === "expired") return promo.is_active !== false && expired;
      if (status === "used_up") return promo.is_active !== false && !expired && usedUp;
      if (status === "active") return promo.is_active !== false && !expired && !usedUp;
      return true;
    });
    const sort = params.get("sort") || "created_desc";
    const page = paged(
      sortAdminRows(promos, sort, [
        {
          asc: "code_asc",
          desc: "code_desc",
          defaultDirection: "asc",
          value: (row) => demoSortValue(row.code),
        },
        {
          asc: "type_asc",
          desc: "type_desc",
          defaultDirection: "asc",
          value: (row) =>
            [
              row.bonus_days,
              row.discount_percent,
              row.duration_multiplier,
              row.traffic_multiplier,
            ].map(demoSortValue),
        },
        {
          asc: "effect_asc",
          desc: "effect_desc",
          defaultDirection: "desc",
          value: (row) =>
            [
              row.bonus_days,
              row.discount_percent,
              row.duration_multiplier,
              row.traffic_multiplier,
            ].map(demoSortValue),
        },
        {
          asc: "scope_asc",
          desc: "scope_desc",
          defaultDirection: "asc",
          value: (row) => demoSortValue(row.applies_to),
        },
        {
          asc: "eligibility_asc",
          desc: "eligibility_desc",
          defaultDirection: "asc",
          value: (row) => [row.min_subscription_months, row.min_traffic_gb].map(demoSortValue),
        },
        {
          asc: "activations_asc",
          desc: "activations_desc",
          defaultDirection: "desc",
          value: (row) => [row.current_activations, row.max_activations].map(demoSortValue),
        },
        {
          asc: "status_asc",
          desc: "status_desc",
          defaultDirection: "desc",
          value: (row) => demoSortValue(row.is_active),
        },
        {
          asc: "valid_until_asc",
          desc: "valid_until_desc",
          defaultDirection: "asc",
          value: (row) => demoSortValue(row.valid_until),
        },
        {
          asc: "created_asc",
          desc: "created_desc",
          defaultDirection: "desc",
          value: (row) => demoSortValue(row.created_at),
        },
      ] satisfies AdminSortColumn<(typeof promos)[number]>[]),
      params,
      25
    );
    return {
      ok: true,
      promos: clone(page.items),
      total: page.total,
      owned_total: allPromos.filter((promo) => Boolean(promo.user_id)).length,
      page: page.page,
      page_size: page.pageSize,
    };
  }
  const promoActivationsMatch = cleanPath.match(/^\/admin\/promos\/(\d+)\/activations$/);
  if (promoActivationsMatch) {
    const promo = demoPromos().find((item) => item.id === Number(promoActivationsMatch[1]));
    if (!promo) return { ok: false, error: "not_found" };
    return {
      ok: true,
      activations: [],
      total: 0,
      page: Number(params.get("page") || 0),
      page_size: Number(params.get("page_size") || 25),
      revenue_summary: {
        payments_total: 0,
        revenue_payments: 0,
        currencies: [],
      },
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

  if (cleanPath === "/admin/backups") {
    const backups = clone(DATASET.backups);
    return {
      ...backups,
      archives: backups?.archives?.map((archive) => ({
        name: archive.name,
        size_bytes: archive.size_bytes,
        modified_at: archive.modified_at || archive.created_at,
      })),
    };
  }
  if (cleanPath.startsWith("/admin/backup-archives/")) {
    const name = decodeURIComponent(cleanPath.slice("/admin/backup-archives/".length));
    const archive = DATASET.backups?.archives?.find((item) => item.name === name);
    return archive ? { ok: true, archive: clone(archive) } : { ok: false, error: "not_found" };
  }
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

  if (cleanPath === "/documents" && method === "GET") {
    return {
      ok: true,
      documents: [...demoDocuments.values()]
        .filter((document) => String(document.markdown || "").trim())
        .map(({ markdown: _markdown, ...document }) => clone(document)),
    };
  }

  if (cleanPath === "/admin/documents") {
    if (method === "POST") {
      const document = clone(jsonBody(options)) as DemoRecord;
      demoDocuments.set(String(document.slug || ""), document);
      storeDemoDocuments(demoDocuments);
      return { ok: true, ...clone(document) };
    }
    return { ok: true, documents: [...demoDocuments.values()].map(clone) };
  }

  const adminDocumentMatch = cleanPath.match(/^\/admin\/documents\/(.+)$/);
  if (adminDocumentMatch) {
    const slug = decodeURIComponent(adminDocumentMatch[1]);
    const current = demoDocuments.get(slug);
    if (method === "DELETE") {
      demoDocuments.delete(slug);
      storeDemoDocuments(demoDocuments);
      return { ok: true };
    }
    if (method === "PUT") {
      const document = clone(jsonBody(options)) as DemoRecord;
      demoDocuments.delete(slug);
      demoDocuments.set(String(document.slug || slug), document);
      storeDemoDocuments(demoDocuments);
      return { ok: true, ...clone(document) };
    }
    return current ? { ok: true, ...clone(current) } : { ok: false, error: "document_not_found" };
  }

  const publicDocumentMatch = cleanPath.match(/^\/documents\/(.+)$/);
  if (publicDocumentMatch && method === "GET") {
    const document = demoDocuments.get(decodeURIComponent(publicDocumentMatch[1]));
    return document && String(document.markdown || "").trim()
      ? { ok: true, ...clone(document) }
      : { ok: false, error: "document_not_found" };
  }

  if (cleanPath === "/admin/information-pages") {
    const path = String(params.get("path") || "").trim();
    if (method === "GET") {
      return {
        ok: true,
        path,
        markdown: demoInformationPages.get(path) || "",
        exists: demoInformationPages.has(path),
      };
    }
    if (method === "PUT") {
      const body = jsonBody(options);
      const nextPath = String(body.path || "").trim();
      const previousPath = String(body.previous_path || "").trim();
      if (previousPath && previousPath !== nextPath) demoInformationPages.delete(previousPath);
      const markdown = String(body.markdown || "");
      demoInformationPages.set(nextPath, markdown);
      return { ok: true, path: nextPath, markdown, exists: true };
    }
  }

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

  if (cleanPath === "/admin/tariffs/tribute/catalog") {
    return {
      ok: true,
      subscriptions: [
        {
          subscription_id: 101,
          name: "Minishop Standard",
          currency: "rub",
          periods: [
            { period_id: 1001, period: "monthly", price: 299, months: 1 },
            { period_id: 1003, period: "quarterly", price: 799, months: 3 },
            { period_id: 1012, period: "yearly", price: 2990, months: 12 },
          ],
        },
      ],
      products: [
        {
          product_id: 501,
          name: "50 GB top-up",
          type: "digital",
          status: "approved",
          price: 199,
          currency: "rub",
          link: "https://web.tribute.tg/p/501",
        },
      ],
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
