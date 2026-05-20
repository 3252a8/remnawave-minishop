export const MANUAL_LOGOUT_FLAG_KEY = "rw_webapp_manual_logout";
export const LANGUAGE_LABELS = {
  ru: "Русский",
  en: "English",
  de: "Deutsch",
  es: "Español",
  fr: "Français",
  tr: "Türkçe",
  uk: "Українська",
};
export const LANGUAGE_FLAGS = {
  ru: "🇷🇺",
  en: "🇬🇧",
  de: "🇩🇪",
  es: "🇪🇸",
  fr: "🇫🇷",
  tr: "🇹🇷",
  uk: "🇺🇦",
};
export const WEBAPP_LANGUAGE_ORDER = ["ru", "en"];
export const APP_SECTION_PATHS = {
  home: "/home",
  invite: "/invite",
  devices: "/devices",
  support: "/support",
  settings: "/settings",
  admin: "/admin",
};
export const ADMIN_SECTIONS = new Set([
  "stats",
  "users",
  "payments",
  "promos",
  "ads",
  "broadcast",
  "logs",
  "support",
  "tariffs",
  "appearance",
  "settings",
]);
export const TELEGRAM_WEBAPP_SCRIPT_URL = "https://telegram.org/js/telegram-web-app.js";
export const TELEGRAM_SDK_BOOT_TIMEOUT_MS = 900;
export const TELEGRAM_SDK_ACTION_TIMEOUT_MS = 1800;
export const TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS = 15000;
