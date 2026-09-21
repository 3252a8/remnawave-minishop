type MenuButtonVisibility = {
  show_in_telegram_webapp?: unknown;
  show_in_browser?: unknown;
};

export function visibleMenuButtons<T extends MenuButtonVisibility>(
  buttons: T[],
  telegramMiniAppContext: boolean
): T[] {
  const visibilityKey = telegramMiniAppContext ? "show_in_telegram_webapp" : "show_in_browser";
  return buttons.filter((button) => button[visibilityKey] !== false);
}
