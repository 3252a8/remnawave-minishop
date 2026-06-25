import { shellState } from "./shellState.svelte";

export function createUiChrome({
  getCurrentLang,
  normalizeLangCode,
}: {
  getCurrentLang: () => string;
  normalizeLangCode: (value: string) => string;
}) {
  let scrollLockApplied = false;
  let languageClickGuardTimer: number | null = null;
  let languageClickGuardArmTimer: number | null = null;

  function syncBodyScrollLock(locked: boolean) {
    if (typeof document === "undefined") return;
    if (locked && !scrollLockApplied) {
      document.body.style.overflow = "hidden";
      scrollLockApplied = true;
      return;
    }
    if (!locked && scrollLockApplied) {
      document.body.style.overflow = "";
      scrollLockApplied = false;
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

  function updateGuestLanguage(nextValue: string) {
    const language = normalizeLangCode(nextValue);
    setLanguageMenuOpen(false);
    if (!language || language === getCurrentLang()) return;
    shellState.guestLanguage = language;
  }

  return {
    clearLanguageClickGuard,
    setLanguageMenuOpen,
    syncBodyScrollLock,
    updateGuestLanguage,
  };
}
