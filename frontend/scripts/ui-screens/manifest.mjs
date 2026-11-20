// Screen catalogue for the UI screenshot tool.
//
// Static entries cover customer-cabinet screens, mock scenarios, detail pages
// and dialogs. Admin sections are discovered at runtime from the sidebar, and
// every entry with `discover` is expanded into one variant per tab or
// accordion group it renders, so new sections and tabs are captured without
// editing this file.
//
// Entry fields:
//   id         stable file name: `<surface>.<screen>[.<state>]`
//   url        path below /demo/runtime (query string allowed)
//   steps      optional interactions before the shot:
//              { click: selector, nth?: number } | { wait: ms } | { press: key }
//   discover   "tabs" (role=tab triggers with data-value) | "accordions"
//   viewports  limit to some viewports (default: all requested)
//   fullPage   false = viewport-only shot (menus, drawers)
//
// Selectors may use Playwright engines (`:has-text()`); the demo runs in
// Russian by default, so text selectors use the Russian copy.

export const VIEWPORTS = {
  desktop: { width: 1440, height: 900, scale: 1, touch: false },
  mobile: { width: 390, height: 844, scale: 2, touch: true },
};

export const THEMES = ["dark", "light"];

const appScreens = [
  ["app.home", "/home"],
  ["app.home.traffic-details", "/home", { steps: [{ click: ".premium-server-trigger" }] }],
  ["app.home.no-subscription", "/home?mock=no-subscription"],
  ["app.home.trial", "/home?mock=trial"],
  ["app.home.depleted", "/home?mock=depleted"],
  ["app.home.compact", "/home?mock=compact"],
  ["app.home.balance", "/home?mock=user-balance"],
  ["app.home.server-status", "/home?mock=server-status"],
  ["app.home.auto-renew", "/home?mock=auto-renew"],
  ["app.home.notifications-banner", "/home?mock=notifications"],
  ["app.plans", "/plans?mock=checkout-addons"],
  [
    "app.plans.limits",
    "/plans?mock=checkout-addons",
    { steps: [{ click: ".checkout-tariff-toggle" }] },
  ],
  ["app.plans.balance", "/plans?mock=checkout-balance-partial"],
  ["app.checkout.balance", "/checkout?plan=standard&months=1&mock=balance-recurring-partial"],
  ["app.trial", "/trial?mock=trial"],
  ["app.install", "/install?mock=checkout-addons"],
  ["app.invite", "/invite"],
  ...["referrals", "gifts", "codes"].map((tab) => [`app.invite.${tab}`, `/invite/${tab}`]),
  ["app.partner", "/partner?partner_scenario=active_populated", { discover: "tabs" }],
  ["app.partner.empty", "/partner?partner_scenario=active_empty"],
  ["app.partner.apply", "/partner?partner_scenario=no_application"],
  ...["links", "balance", "clients"].map((tab) => [
    `app.partner.${tab}`,
    `/partner/${tab}?partner_scenario=active_populated`,
  ]),
  ["app.devices", "/devices?mock=devices"],
  ["app.support", "/support", { discover: "tabs" }],
  ["app.support.new", "/support/new"],
  ["app.support.ticket", "/support", { steps: [{ click: ".ticket-card" }] }],
  ["app.support.waiting", "/support/4103"],
  ["app.support.conversation", "/support/4101", { fullPage: false }],
  ["app.support.missing", "/support/7", { fullPage: false }],
  [
    "app.support.billing",
    "/support/new",
    {
      steps: [
        { click: '[role="combobox"][aria-label="Категория"]' },
        { click: '[role="option"]:has-text("Оплата")' },
      ],
    },
  ],
  ["app.settings", "/settings"],
  ["app.settings.payments", "/settings/payments"],
  ["app.settings.notifications", "/settings/notifications"],
  ["app.settings.security", "/settings/security"],
  ["app.status", "/status"],
  ["app.login", "/login?mock=auth"],
  ["app.login.password", "/login?mock=auth", { steps: [{ click: ".password-switch-button" }] }],
  [
    "app.trial-captcha",
    "/app/?mock=trial-captcha",
    { steps: [{ click: "button:has-text('Попробовать бесплатно')" }] },
  ],
];

const appDialogs = [
  ["app.invite.gift-dialog", "/invite", [{ click: "button.btn:has-text('Подарить')" }]],
  ["app.invite.qr-dialog", "/invite", [{ click: "button[aria-label='Показать QR-код']" }]],
  [
    "app.devices.rename-dialog",
    "/devices?mock=devices",
    [{ click: "button[aria-label='Переименовать']" }],
  ],
  ["app.settings.language-menu", "/settings", [{ click: ".language-select-trigger" }]],
];

const adminScreens = [
  ["admin.users.1366", "/admin/users", { viewports: ["desktop"], captureWidth: 1366 }],
  [
    "admin.users.detail",
    "/admin/users/910001",
    { discover: "tabs", discoverWithin: ".admin-user-detail-page" },
  ],
  ["admin.users.relationships", "/admin/users?view=relationships&focus=910370"],
  [
    "admin.partners.detail",
    "/admin/partners/partner/10001",
    { discover: "tabs", discoverWithin: ".partners-detail-tab-list" },
  ],
  ["admin.support.ticket", "/admin/support/7", { steps: [{ waitHidden: "[data-sonner-toast]" }] }],
  ["admin.support.conversation", "/admin/support/4101", { fullPage: false }],
  [
    "admin.support.note",
    "/admin/support/4101",
    { steps: [{ click: "#support-internal-note" }], fullPage: false },
  ],
  [
    "admin.support.note-switch",
    "/admin/support/4101",
    {
      fullPage: false,
      steps: [
        { click: "#support-internal-note" },
        {
          compose: {
            editor: ".support-admin-composer .ProseMirror",
            lines: ["Коллеги, проверьте журнал подключения."],
          },
        },
        { click: "#support-internal-note" },
      ],
    },
  ],
  ...["awaiting-admin", "awaiting-user", "closed"].map((status, index) => [
    `admin.support.queue-${status}`,
    "/admin/support",
    { steps: [{ click: ".support-admin-ticket-tabs button", nth: index + 1 }] },
  ]),
  ["admin.settings.menu-buttons", "/admin/settings/menu-buttons"],
  ...["user", "internal"].map((scope) => [
    `admin.translations.${scope}`,
    "/admin/translations",
    { steps: [{ click: `[data-admin-translation-audience="${scope}"]` }] },
  ]),
  [
    "admin.translations.plugins",
    "/admin/translations",
    { steps: [{ click: '[data-admin-translation-scope="plugins"]' }] },
  ],
];

const adminDialogs = [
  ["admin.gifts.detail", "/admin/gifts", [{ click: ".gift-detail-button" }]],
  [
    "admin.payments.detail",
    "/admin/payments",
    [{ click: ".admin-main button[aria-label='Открыть платёж']" }],
  ],
  [
    "admin.gifts.create",
    "/admin/gifts",
    [{ click: "button.admin-btn-primary:has-text('Создать подарок')" }],
  ],
  ["admin.tariffs.editor", "/admin/tariffs", [{ click: "button.admin-btn:has-text('Настроить')" }]],
  [
    "admin.tariffs.create",
    "/admin/tariffs",
    [{ click: "button.admin-btn-primary:has-text('Создать тариф')" }],
  ],
  ["admin.promos.edit", "/admin/promos", [{ click: "button[aria-label='Редактировать']" }]],
  ["admin.ads.campaign", "/admin/ads", [{ click: "button.admin-btn:has-text('Открыть')" }]],
  [
    "admin.appearance.preferences",
    "/admin/appearance",
    [{ click: ".appearance-preferences-trigger" }],
  ],
  [
    "admin.appearance.add-themes",
    "/admin/appearance",
    [{ click: "button.admin-btn-primary:has-text('Добавить темы')" }],
  ],
  [
    "admin.plugins.add",
    "/admin/plugins",
    [{ click: "button.admin-btn-primary:has-text('Добавить плагин')" }],
  ],
  [
    "admin.stats.custom-period",
    "/admin/stats",
    [{ click: "button.admin-revenue-period-btn:has-text('Свой период')" }],
  ],
];

const adminMobileOnly = [
  ["admin.nav-drawer", "/admin/stats", [{ click: ".admin-mobile-toggle" }]],
  ["admin.logs.end", "/admin/logs", [{ scrollTo: ".admin-main .admin-pagination" }]],
  [
    "admin.support.filters",
    "/admin/support",
    [{ click: '.support-list-toolbar button[aria-haspopup="dialog"]' }],
  ],
  [
    "admin.support.details",
    "/admin/support/4101",
    [{ reveal: { content: ".support-user-context", trigger: ".support-mobile-title button" } }],
  ],
  [
    "admin.support.tools",
    "/admin/support/4101",
    [{ reveal: { content: ".support-admin-composer-buttons", trigger: ".support-tools-toggle" } }],
  ],
];

// Measure the usable chat area while composing. These are real editor inputs
// in a shortened viewport; a desktop Chromium runner cannot draw the OS IME.
const draftLines = [
  "Проверяю подключение на телефоне.",
  "Открываю приложение.",
  "Выбираю основной профиль.",
  "Нажимаю подключить.",
  "Жду несколько секунд.",
  "Проверяю сеть.",
  "Переключаюсь на Wi-Fi.",
  "Результат тот же.",
];
const mobileChats = [
  ["app.support", "/support/4101", ".ticket-composer .ProseMirror"],
  ["admin.support", "/admin/support/4101", ".support-admin-composer .ProseMirror"],
];

/**
 * @param {string[]} adminSections ids discovered from the admin sidebar
 */
export function staticScreens(adminSections) {
  const screens = [];
  for (const [id, url, extra] of appScreens) screens.push({ id, url, ...extra });
  for (const [id, url, steps] of appDialogs) screens.push({ id, url, steps, fullPage: false });
  for (const section of adminSections) {
    screens.push({
      id: `admin.${section}`,
      url: `/admin/${section}`,
      discover: section === "settings" ? "accordions" : "tabs",
    });
  }
  for (const [id, url, extra] of adminScreens) screens.push({ id, url, ...extra });
  for (const [id, url, steps] of adminDialogs) screens.push({ id, url, steps });
  for (const [id, url, steps] of adminMobileOnly) {
    screens.push({ id, url, steps, viewports: ["mobile"], fullPage: false });
  }
  for (const [prefix, url, editor] of mobileChats) {
    for (const [state, lines] of [
      ["short", draftLines.slice(0, 1)],
      ["long", draftLines],
    ]) {
      screens.push({
        id: `${prefix}.typing-${state}`,
        url,
        viewports: ["mobile"],
        fullPage: false,
        steps: [{ compose: { editor, height: 470, lines } }],
      });
    }
    screens.push({
      id: `${prefix}.typing-compact`,
      url,
      viewports: ["mobile"],
      fullPage: false,
      visualArea: { width: 320, layoutHeight: 568, top: 24, height: 295, safeTop: 96 },
      steps: [{ compose: { editor, lines: draftLines } }],
    });
  }
  return screens;
}
