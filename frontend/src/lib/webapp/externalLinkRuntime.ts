import { createAppLaunchActions } from "./appLaunchActions.js";
import { openAppLinkTarget } from "./appLinkActions.js";
import { shellState } from "./shellState.svelte";

type TelegramWebApp = Record<string, unknown> & {
  openLink?: (url: string, options?: Record<string, unknown>) => void;
  openTelegramLink?: (url: string) => void;
};

type ExternalLinkRuntimeDeps = {
  assignLocation: (url: string) => void;
  getCurrentLang: () => string;
  hasTelegramLaunchParams: () => boolean;
  openHiddenAnchor?: (url: string) => void;
  openLaunchTarget?: (url: string) => void;
  refreshTelegram: () => TelegramWebApp | null;
  readLaunchTarget?: () => string;
};

export function createExternalLinkRuntime({
  assignLocation,
  getCurrentLang,
  hasTelegramLaunchParams,
  openHiddenAnchor,
  openLaunchTarget,
  refreshTelegram,
  readLaunchTarget,
}: ExternalLinkRuntimeDeps) {
  function openExternalLink(url: string) {
    if (!url) return;
    const telegram = shellState.tg;
    if (/^https:\/\/(?:t|telegram)\.me\//i.test(url) && telegram?.openTelegramLink) {
      try {
        telegram.openTelegramLink(url);
        return;
      } catch {
        // Fall back to generic external opening below.
      }
    }
    if (telegram?.openLink) {
      telegram.openLink(url, { try_instant_view: false });
      return;
    }
    assignLocation(url);
  }

  function openAppLink(url: string) {
    openAppLinkTarget(url, {
      currentLang: getCurrentLang(),
      getTelegram: () => shellState.tg,
      hasTelegramLaunchParams,
      openExternalLink,
      openHiddenAnchor,
      refreshTelegram,
      setTelegram: (value) => {
        shellState.tg = value;
      },
    });
  }

  return {
    ...createAppLaunchActions({
      openTarget: openLaunchTarget,
      readTarget: readLaunchTarget,
    }),
    openAppLink,
    openExternalLink,
  };
}
