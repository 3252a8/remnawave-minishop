import { lockPageScroll } from "./scrollLock";
import { shellState } from "./shellState.svelte";

export function createUiChrome({
  getCurrentLang,
  normalizeLangCode,
  ensureGuestLanguage,
  onLanguageLoadError,
  rememberLanguage,
}: {
  getCurrentLang: () => string;
  normalizeLangCode: (value: string) => string;
  ensureGuestLanguage: (language: string) => Promise<void>;
  onLanguageLoadError: () => void;
  rememberLanguage: (language: string) => void;
}) {
  let releaseScrollLock: (() => void) | null = null;
  let languageClickGuardTimer: number | null = null;
  let languageClickGuardArmTimer: number | null = null;
  let guestLanguageRequestId = 0;

  // Shares the ref-counted lock with dialogs and the admin drawer, so an
  // overlay closing here cannot unfreeze a page another overlay still holds.
  function syncBodyScrollLock(locked: boolean) {
    if (typeof document === "undefined") return;
    if (locked && !releaseScrollLock) {
      releaseScrollLock = lockPageScroll();
      return;
    }
    if (!locked && releaseScrollLock) {
      releaseScrollLock();
      releaseScrollLock = null;
    }
  }

  function clearLanguageClickGuard() {
    if (languageClickGuardTimer) {
      window.clearTimeout(languageClickGuardTimer);
      languageClickGuardTimer = null;
    }
    if (languageClickGuardArmTimer) {
      window.clearTimeout(languageClickGuardArmTimer);
      languageClickGuardArmTimer = null;
    }
    shellState.languageClickGuard = false;
    shellState.languageClickGuardArmed = false;
  }

  function setLanguageMenuOpen(open: boolean) {
    const nextOpen = Boolean(open);
    shellState.languageMenuOpen = nextOpen;
    clearLanguageClickGuard();
    if (nextOpen) {
      shellState.languageClickGuard = true;
      languageClickGuardArmTimer = window.setTimeout(() => {
        shellState.languageClickGuardArmed = true;
        languageClickGuardArmTimer = null;
      }, 220);
      return;
    }
    shellState.languageClickGuard = true;
    shellState.languageClickGuardArmed = false;
    languageClickGuardTimer = window.setTimeout(() => {
      shellState.languageClickGuard = false;
      languageClickGuardTimer = null;
    }, 260);
  }

  async function updateGuestLanguage(nextValue: string) {
    const language = normalizeLangCode(nextValue);
    setLanguageMenuOpen(false);
    if (!language || language === getCurrentLang()) return;
    const requestId = ++guestLanguageRequestId;
    try {
      await ensureGuestLanguage(language);
    } catch (_error) {
      void _error;
      if (requestId === guestLanguageRequestId) onLanguageLoadError();
      return;
    }
    if (requestId !== guestLanguageRequestId) return;
    rememberLanguage(language);
    shellState.guestLanguage = language;
  }

  return {
    clearLanguageClickGuard,
    setLanguageMenuOpen,
    syncBodyScrollLock,
    updateGuestLanguage,
  };
}
