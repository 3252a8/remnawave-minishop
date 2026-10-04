import { builtApiPath } from "$lib/webapp/publicApi";

export function buildTelegramMenuPath() {
  return builtApiPath<"/api/admin/telegram-menu">("/admin/telegram-menu");
}
export function buildTelegramMenuPreviewPath() {
  return builtApiPath<"/api/admin/telegram-menu/preview">("/admin/telegram-menu/preview");
}
export function buildTelegramMenuTestPath() {
  return builtApiPath<"/api/admin/telegram-menu/test">("/admin/telegram-menu/test");
}
export function buildTelegramEmojiLibraryPath() {
  return builtApiPath<"/api/admin/telegram-emoji/library">("/admin/telegram-emoji/library");
}
export function buildTelegramEmojiRefreshPath() {
  return builtApiPath<"/api/admin/telegram-emoji/library/refresh">(
    "/admin/telegram-emoji/library/refresh"
  );
}
export function buildTelegramEmojiCatalogPath(params: URLSearchParams) {
  return builtApiPath<"/api/admin/telegram-emoji/catalog">(
    `/admin/telegram-emoji/catalog?${params}`
  );
}
export function buildTelegramEmojiMediaPath(id: string) {
  return builtApiPath<"/api/admin/telegram-emoji/media/{emoji_id}">(
    `/admin/telegram-emoji/media/${encodeURIComponent(id)}`
  );
}
/** Accept only the catalog's local authenticated media URL, preserving its version. */
export function buildTelegramEmojiMediaUrlPath(url: string) {
  if (!/^\/api\/admin\/telegram-emoji\/media\/[1-9][0-9]{0,19}(?:\?v=[a-f0-9]{16})?$/.test(url))
    return null;
  return builtApiPath<"/api/admin/telegram-emoji/media/{emoji_id}">(url);
}
export function buildTelegramEmojiAdminPath() {
  return builtApiPath<"/api/admin/me">("/admin/me");
}
