import type { SettingsSavedPayload, SettingsStore } from "./stores/settingsStore";
import type { ThemesStore } from "./stores/themesStore.svelte";

type SaveAppearanceOptions = {
  settingsStore: Pick<SettingsStore, "saveSettings">;
  themesStore: Pick<ThemesStore, "saveThemes">;
  dirtyKeys: string[];
  onSettingsSaved: (payload: SettingsSavedPayload) => void | Promise<void>;
};

const RELOAD_KEYS = new Set([
  "WEBAPP_LOGO_URL",
  "WEBAPP_USER_THEME_MODE_ENABLED",
  "WEBAPP_COMPACT_HOME_ENABLED",
  "WEBAPP_COMPACT_LOGIN_ENABLED",
  "WEBAPP_CHECKOUT_ADDON_VALUE_ANIMATION_ENABLED",
  "WEBAPP_CHECKOUT_ADDON_EDITOR_EXPANDED_BY_DEFAULT",
  "WEBAPP_FAVICON_URL",
  "WEBAPP_FAVICON_USE_CUSTOM",
  "WEBAPP_LOGO_FAVICON_URL",
]);

export async function saveAppearanceChanges({
  settingsStore,
  themesStore,
  dirtyKeys,
  onSettingsSaved,
}: SaveAppearanceOptions): Promise<boolean> {
  const shouldReloadFrontend = dirtyKeys.some((key) => RELOAD_KEYS.has(key));
  let savedSettings: SettingsSavedPayload = { updates: {}, deletes: [] };
  if (dirtyKeys.length) {
    const settingsSaved = await settingsStore.saveSettings((payload) => {
      savedSettings = payload;
    });
    if (!settingsSaved) return false;
  }
  // Refreshing the application can remount the editor and reload its catalog.
  // Persist both drafts before invoking either application refresh callback.
  const themesSaved = await themesStore.saveThemes();
  if (!themesSaved) return false;
  if (dirtyKeys.length) {
    await onSettingsSaved({ ...savedSettings, reloadFrontend: shouldReloadFrontend });
  }
  return true;
}
