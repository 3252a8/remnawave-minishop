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
  ["app.home.no-subscription", "/home?mock=no-subscription"],
  ["app.home.trial", "/home?mock=trial"],
  ["app.home.depleted", "/home?mock=depleted"],
  ["app.home.compact", "/home?mock=compact"],
  ["app.home.balance", "/home?mock=user-balance"],
  ["app.home.server-status", "/home?mock=server-status"],
  ["app.home.auto-renew", "/home?mock=auto-renew"],
  ["app.home.notifications-banner", "/home?mock=notifications"],
  ["app.plans", "/plans?mock=checkout-addons"],
  ["app.plans.balance", "/plans?mock=checkout-balance-partial"],
  ["app.install", "/install?mock=checkout-addons"],
  ["app.invite", "/invite"],
  ["app.partner", "/partner?partner_scenario=active_populated", { discover: "tabs" }],
  ["app.partner.empty", "/partner?partner_scenario=active_empty"],
  ["app.partner.apply", "/partner"],
  ["app.devices", "/devices?mock=devices"],
  ["app.support", "/support", { discover: "tabs" }],
  ["app.support.new", "/support/new"],
  ["app.support.ticket", "/support", { steps: [{ click: ".ticket-card" }] }],
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
  ["admin.users.detail", "/admin/users/910001", { discover: "tabs" }],
  ["admin.users.relationships", "/admin/users?view=relationships&focus=910370"],
  [
    "admin.partners.detail",
    "/admin/partners/partner/10001",
    { discover: "tabs", discoverWithin: ".partners-detail-tab-list" },
  ],
  ["admin.support.ticket", "/admin/support/7"],
  ["admin.settings.menu-buttons", "/admin/settings/menu-buttons"],
];

const adminDialogs = [
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

const adminMobileOnly = [["admin.nav-drawer", "/admin/stats", [{ click: ".admin-mobile-toggle" }]]];

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
  return screens;
}
