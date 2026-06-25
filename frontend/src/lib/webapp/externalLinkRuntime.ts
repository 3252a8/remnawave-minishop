import { createAppLaunchActions } from "./appLaunchActions.js";
import { openAppLinkTarget } from "./appLinkActions.js";

type TelegramWebApp = Record<string, unknown> & {
  openLink?: (url: string, options?: Record<string, unknown>) => void;
  openTelegramLink?: (url: string) => void;
};

type ExternalLinkRuntimeDeps = {
  assignLocation: (url: string) => void;
  getCurrentLang: () => string;
  getTelegram: () => TelegramWebApp | null;
  hasTelegramLaunchParams: () => boolean;
  openHiddenAnchor?: (url: string) => void;
  openLaunchTarget?: (url: string) => void;
  refreshTelegram: () => TelegramWebApp | null;
  readLaunchTarget?: () => string;
  setAppLaunchTarget: (target: string) => void;
  setTelegram: (value: TelegramWebApp) => void;
};

export function createExternalLinkRuntime({
  assignLocation,
  getCurrentLang,
  getTelegram,
  hasTelegramLaunchParams,
  openHiddenAnchor,
  openLaunchTarget,
  refreshTelegram,
  readLaunchTarget,
  setAppLaunchTarget,
  setTelegram,
}: ExternalLinkRuntimeDeps) {
  function openExternalLink(url: string) {
    if (!url) return;
    const telegram = getTelegram();
    if (telegram?.openLink) {
      telegram.openLink(url, { try_instant_view: false });
      return;
    }
    assignLocation(url);
  }

  function openAppLink(url: string) {
    openAppLinkTarget(url, {
      currentLang: getCurrentLang(),
      getTelegram,
      hasTelegramLaunchParams,
      openExternalLink,
      openHiddenAnchor,
      refreshTelegram,
      setTelegram,
    });
  }

  return {
    ...createAppLaunchActions({
      openTarget: openLaunchTarget,
      readTarget: readLaunchTarget,
      setAppLaunchTarget,
    }),
    openAppLink,
    openExternalLink,
  };
}
