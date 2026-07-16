import type { DemoAdminUser, DemoRecord, DemoTicket } from "./dataset";
import { withDemoAdminUserMetrics, withDemoAvatars } from "./users";

export type AdminDemoFixtures = {
  adminUsers: DemoAdminUser[];
  supportTickets: DemoTicket[];
  adminPayments: DemoRecord[];
  supportMessages: Record<number, DemoRecord[]>;
  mockAdminDailySeries: { date: string; amount: number }[];
  mockBackups: DemoBackupArchive[];
  compactBackupStamp: (date: Date) => string;
  supportCounts: (items?: DemoTicket[]) => DemoRecord;
  filterSupportTickets: (items: DemoTicket[], params: URLSearchParams) => DemoTicket[];
};

export type DemoBackupArchive = DemoRecord & {
  name: string;
  size_bytes: number;
  modified_at: string;
  created_at: string;
  created_at_local: string;
  compose_files_count: number;
};

/**
 * Per-request admin demo fixtures for the fallback responses that are not
 * backed by the generated dataset. Rebuilt on every mockApi call, matching the
 * former inline definitions inside mockApi().
 */
export function buildAdminDemoFixtures(): AdminDemoFixtures {
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
  const supportTickets: DemoTicket[] = [
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
  const adminPayments: DemoRecord[] = [
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
  function supportCounts(items: DemoTicket[] = supportTickets): DemoRecord {
    const byStatus: Record<string, number> = {
      open: 0,
      awaiting_admin: 0,
      awaiting_user: 0,
      resolved: 0,
    };
    for (const item of items) {
      byStatus[String(item.status)] = (byStatus[String(item.status)] || 0) + 1;
    }
    const closed = (byStatus.closed || 0) + (byStatus.resolved || 0);
    const active = items.length - closed;
    return { ...byStatus, active, closed, total: items.length };
  }
  function filterSupportTickets(items: DemoTicket[], params: URLSearchParams): DemoTicket[] {
    let out = [...items];
    const status = params.get("status");
    if (status === "active")
      out = out.filter((item) => !["closed", "resolved"].includes(String(item.status)));
    else if (status === "closed")
      out = out.filter((item) => ["closed", "resolved"].includes(String(item.status)));
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
    const priorityRank: Record<string, number> = { urgent: 4, high: 3, normal: 2, low: 1 };
    const ticketTime = (item: DemoTicket) =>
      Number(new Date(String(item.last_message_at || item.created_at)));
    out.sort((a, b) => {
      if (sort === "importance_desc") {
        return (
          (priorityRank[String(b.priority)] || 0) - (priorityRank[String(a.priority)] || 0) ||
          ticketTime(b) - ticketTime(a)
        );
      }
      if (sort === "updated_asc") {
        return ticketTime(a) - ticketTime(b);
      }
      if (sort === "created_desc")
        return Number(new Date(String(b.created_at))) - Number(new Date(String(a.created_at)));
      if (sort === "created_asc")
        return Number(new Date(String(a.created_at))) - Number(new Date(String(b.created_at)));
      return ticketTime(b) - ticketTime(a);
    });
    return out;
  }
  const supportMessages: Record<number, DemoRecord[]> = {
    42: [
      {
        message_id: 1,
        ticket_id: 42,
        author_role: "user",
        author_user_id: 100200300,
        author_name: "Анна Смирнова",
        body: "После обновления приложения профиль перестал подключаться. Ошибка появляется сразу после импорта ссылки.",
        created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
        read_by_admin_at: new Date(Date.now() - 110 * 60000).toISOString(),
        read_by_user_at: null,
      },
      {
        message_id: 2,
        ticket_id: 42,
        author_role: "admin",
        author_user_id: 1,
        author_name: "Мария, поддержка",
        body: "Проверили подписку, она активна. Попробуйте удалить старый профиль и импортировать ссылку ещё раз.",
        created_at: new Date(Date.now() - 90 * 60000).toISOString(),
        read_by_user_at: new Date(Date.now() - 80 * 60000).toISOString(),
        read_by_admin_at: null,
      },
      {
        message_id: 3,
        ticket_id: 42,
        author_role: "user",
        author_user_id: 100200300,
        author_name: "Анна Смирнова",
        body: "Сделал так, но теперь вижу timeout. Телефон iPhone, сеть домашний Wi‑Fi.",
        created_at: new Date(Date.now() - 18 * 60000).toISOString(),
        read_by_user_at: null,
        read_by_admin_at: null,
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
    const out: { date: string; amount: number }[] = [];
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
  const compactBackupStamp = (date: Date) => {
    const pad = (value: number) => String(value).padStart(2, "0");
    return [
      `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`,
      pad(date.getHours()),
      pad(date.getMinutes()),
    ].join("-");
  };
  const mockBackups: DemoBackupArchive[] = [
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
  return {
    adminUsers,
    supportTickets,
    adminPayments,
    supportMessages,
    mockAdminDailySeries,
    mockBackups,
    compactBackupStamp,
    supportCounts,
    filterSupportTickets,
  };
}
