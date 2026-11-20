import { settingsFieldAnchorKey } from "$lib/admin/settingsSections";
import type { SettingsSavedPayload, SettingsStore } from "$lib/admin/stores/settingsStore";
import type { TelegramEmojiApi } from "$lib/telegramEmoji/api";
import { clearMenuDrafts } from "$lib/telegramEmoji/menuDraft";
import type { MenuAppearance } from "$lib/telegramEmoji/types";

const APPEARANCE_KEY = "TELEGRAM_MENU_APPEARANCE_JSON";

/** Keep the menu's dedicated save and draft cache aligned with generic settings writes. */
export function createTelegramMenuSettingsAdapter(
  store: Pick<
    SettingsStore,
    "registerSavedListener" | "setFieldValue" | "registerExtraSaver" | "reportExtraDirty"
  >,
  api: TelegramEmojiApi
) {
  function appearanceSaved(payload: SettingsSavedPayload): boolean {
    return (
      Object.prototype.hasOwnProperty.call(payload.updates, APPEARANCE_KEY) ||
      payload.deletes.includes(APPEARANCE_KEY)
    );
  }

  function subscribeSettingsSaved(listener: () => void): () => void {
    return store.registerSavedListener((payload) => {
      if (appearanceSaved(payload)) listener();
    });
  }

  function subscribeDraftInvalidation(): () => void {
    return subscribeSettingsSaved(() => clearMenuDrafts(api));
  }

  function saveAppearance(appearance: MenuAppearance): void {
    store.setFieldValue(APPEARANCE_KEY, JSON.stringify(appearance));
  }

  function openCustomButtons(): void {
    const anchor = settingsFieldAnchorKey("MENU_BUTTONS_JSON");
    const element = document.querySelector<HTMLElement>(`[data-settings-anchor="${anchor}"]`);
    element?.scrollIntoView({ block: "center" });
    element?.focus({ preventScroll: true });
  }

  /** The header Save also saves the appearance draft, through the menu's own API. */
  function registerSaver(saver: () => void | Promise<void>): () => void {
    return store.registerExtraSaver(saver);
  }

  function reportDirty(count: number): void {
    store.reportExtraDirty("telegram_menu_appearance", count);
  }

  return {
    api,
    saveAppearance,
    registerSaver,
    reportDirty,
    subscribeSettingsSaved,
    subscribeDraftInvalidation,
    openCustomButtons,
  };
}
