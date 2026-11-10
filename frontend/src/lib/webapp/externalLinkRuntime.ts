import { createAppLaunchActions } from "./appLaunchActions.js";
import { openAppLinkTarget } from "./appLinkActions.js";
import { isUnsafeAppUrl } from "./appLinks.js";
import type { OpenLinkAction } from "./types.js";
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
  const openExternalLink: OpenLinkAction = (url, kind) => {
    const isPayment = kind === "payment";
    if (!url || (isPayment && isUnsafeAppUrl(url))) return;
    // Public documents belong to the current Mini App. Telegram.openLink only
    // accepts absolute external URLs and throws for these application paths.
    if (/^\/(?![/\\])/.test(url)) {
      assignLocation(url);
      return;
    }
    const isTelegramLink = /^https:\/\/(?:t|telegram)\.me\//i.test(url);
    let telegram = shellState.tg;
    if (isPayment) {
      telegram = hasTelegramLaunchParams() ? telegram || refreshTelegram() : null;
    }
    if (isTelegramLink && telegram?.openTelegramLink) {
      try {
        telegram.openTelegramLink(url);
        return;
      } catch {
        // Fall back to generic external opening below.
      }
    }
    if (telegram?.openLink) {
      try {
        telegram.openLink(url, { try_instant_view: false });
        return;
      } catch (error) {
        if (!isPayment) throw error;
      }
    }
    assignLocation(url);
  };

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
