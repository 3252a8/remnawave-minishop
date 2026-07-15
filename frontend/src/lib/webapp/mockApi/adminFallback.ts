import { DEV_MOCK } from "../previewMock.js";
import type { PreviewThemesCatalog } from "../previewMock/types";
import { defaultClone, type DemoRecord, type MockApiContext } from "./dataset";
import type { AdminDemoFixtures } from "./adminFixtures";
import { demoProviderCurrencySupport } from "./providers";
import { persistDemoSettings } from "./settings";
import { withCurrentLocaleTranslations } from "./translations";

/**
 * Static admin fallback responses for demo routes that the generated dataset
 * does not cover. Returns undefined when the path is not an admin route.
 */
export function adminFallbackResponse(
  path: string,
  cleanPath: string,
  options: RequestInit,
  context: MockApiContext,
  fixtures: AdminDemoFixtures
): unknown {
  const { clone = defaultClone } = context;
  const {
    adminUsers,
    supportTickets,
    adminPayments,
    supportMessages,
    mockAdminDailySeries,
    mockBackups,
    compactBackupStamp,
    supportCounts,
    filterSupportTickets,
  } = fixtures;

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
      last_vpn_connected_at: "2026-06-05T08:42:00Z",
      vpn_connection_status: "connected",
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
      provider_currency_support: demoProviderCurrencySupport(),
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
        const body = (options?.body ? JSON.parse(String(options.body)) : {}) as DemoRecord;
        const catalog = (body.catalog || body) as DemoRecord & { themes?: unknown };
        if (catalog?.themes) {
          DEV_MOCK.config.themesCatalog = clone(catalog) as unknown as PreviewThemesCatalog;
          DEV_MOCK.data.themes_catalog = clone(catalog) as unknown as PreviewThemesCatalog;
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
    const logoUrl = "/webapp-uploaded-logo/logo-0000000000000000.png";
    const faviconUrl = "/webapp-favicon/0000000000000000/icon-180.png";
    persistDemoSettings({
      WEBAPP_LOGO_URL: logoUrl,
      WEBAPP_LOGO_FAVICON_URL: faviconUrl,
    });
    return {
      ok: true,
      logo_url: logoUrl,
      favicon_url: faviconUrl,
      persisted: true,
    };
  }
  if (path === "/admin/appearance/favicon") {
    const faviconUrl = "/webapp-favicon/1111111111111111/icon-180.png";
    persistDemoSettings({
      WEBAPP_FAVICON_URL: faviconUrl,
      WEBAPP_FAVICON_USE_CUSTOM: true,
    });
    return {
      ok: true,
      favicon_url: faviconUrl,
      persisted: true,
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
      const body = (options?.body ? JSON.parse(String(options.body)) : {}) as DemoRecord;
      const updates = (body.updates || {}) as DemoRecord;
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
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB")) {
        DEV_MOCK.config.trialPremiumTrafficLimitGb = updates.TRIAL_PREMIUM_TRAFFIC_LIMIT_GB;
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
      if (Object.prototype.hasOwnProperty.call(updates, "TRIAL_PREMIUM_SQUAD_UUIDS")) {
        DEV_MOCK.config.trialPremiumSquadUuids = updates.TRIAL_PREMIUM_SQUAD_UUIDS || "";
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
    return withCurrentLocaleTranslations({
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
    } as unknown as Parameters<typeof withCurrentLocaleTranslations>[0]);
  }
  if (path === "/admin/settings")
    return {
      ok: true,
      features: [],
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
              key: "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB",
              type: "float",
              section: "pricing",
              subsection: "trial",
              label: "Trial premium traffic limit (GB)",
              value: DEV_MOCK.config.trialPremiumTrafficLimitGb ?? 0,
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
              key: "TRIAL_PREMIUM_SQUAD_UUIDS",
              type: "string",
              section: "pricing",
              subsection: "trial",
              label: "Premium Internal Squads for trial",
              value: DEV_MOCK.config.trialPremiumSquadUuids || "",
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
              label: "Бонусы только за первый платёж приглашённого",
              description:
                "Если включено, повторные покупки того же приглашённого пользователя больше не начисляют реферальные бонусы ни ему, ни пригласившему. Первый успешный платёж остаётся бонусным.",
              value: Boolean(DEV_MOCK.config.referralOneBonusPerReferee),
            },
            {
              key: "LEGACY_REFS",
              type: "bool",
              section: "pricing",
              subsection: "legacy_tariffs",
              label: "Legacy ref-ссылки с ID пользователя",
              description:
                "Принимать старые ссылки вида /start ref_<telegram_id>, где payload содержит Telegram/user ID пригласившего.",
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
            ...(
              [
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
              ] as [string, string, unknown][]
            ).map(([key, type, value]) => ({
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
    if (parts[5] === "typing") return { ok: true };
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
          body: (JSON.parse(String(options?.body || "{}")) as DemoRecord)?.body || "",
          is_internal_note: Boolean(
            (JSON.parse(String(options?.body || "{}")) as DemoRecord)?.is_internal_note
          ),
          created_at: new Date().toISOString(),
          read_by_user_at: null,
          read_by_admin_at: null,
        },
      };
    }
    if (String(options.method || "GET").toUpperCase() === "PATCH") {
      return {
        ok: true,
        ticket: {
          ...ticket,
          ...((JSON.parse(String(options?.body || "{}")) as DemoRecord) || {}),
        },
      };
    }
    return {
      ok: true,
      ticket,
      messages: clone([
        ...(supportMessages[Number(ticket.ticket_id)] || []),
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
      peer_typing: false,
    };
  }
  if (cleanPath.startsWith("/admin/"))
    return { ok: true, payments: [], promos: [], logs: [], campaigns: [], total: 0 };
  return undefined;
}
