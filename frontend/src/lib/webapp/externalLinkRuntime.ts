import { createAppLaunchActions } from "./appLaunchActions.js";
import { openAppLinkTarget } from "./appLinkActions.js";
import { buildExternalAppLaunchUrl } from "./appLinks.js";
import type { OpenLinkAction } from "./types.js";
import { shellState } from "./shellState.svelte";

type TelegramWebApp = Record<string, unknown> & {
  openLink?: (url: string, options?: Record<string, unknown>) => void;
  openTelegramLink?: (url: string) => void;
};

type ExternalLinkRuntimeDeps = {
  assignLocation: (url: string) => void;
  locationRef?: Pick<Location, "href">;
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
  locationRef,
  openHiddenAnchor,
  openLaunchTarget,
  refreshTelegram,
  readLaunchTarget,
}: ExternalLinkRuntimeDeps) {
  const openExternalLink: OpenLinkAction = (url, kind) => {
    if (!url) return;
    // Public documents belong to the current Mini App. Telegram.openLink only
    // accepts absolute external URLs and throws for these application paths.
    if (/^\/(?![/\\])/.test(url)) {
      assignLocation(url);
      return;
    }
    const isTelegramLink = /^https:\/\/(?:t|telegram)\.me\//i.test(url);
    if (kind === "payment" && !isTelegramLink && hasTelegramLaunchParams()) {
      const gateway = buildExternalAppLaunchUrl(url, locationRef, getCurrentLang(), "payment");
      if (gateway) {
        const telegram = shellState.tg || refreshTelegram();
        try {
          if (telegram?.openLink) {
            telegram.openLink(gateway, { try_instant_view: false });
            return;
          }
        } catch {
          // Keep a usable continuation when the Telegram bridge is unavailable.
        }
        assignLocation(gateway);
        return;
      }
    }
    const telegram = shellState.tg;
    if (isTelegramLink && telegram?.openTelegramLink) {
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
