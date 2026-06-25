import {
  buildExternalAppLaunchUrl,
  isHttpUrl,
  isUnsafeAppUrl,
  openUrlWithHiddenAnchor,
} from "./appLinks.js";

type TelegramWebApp = Record<string, unknown> & {
  openLink?: (url: string, options?: Record<string, unknown>) => void;
  openTelegramLink?: (url: string) => void;
};

type LocationRef = Pick<Location, "href"> | null;
type BuildExternalAppLaunchUrl = (
  value: string,
  locationRef?: LocationRef,
  language?: string
) => string;

const buildAppLaunchUrl = buildExternalAppLaunchUrl as BuildExternalAppLaunchUrl;

export type OpenAppLinkOptions = {
  assignLocation?: (url: string) => void;
  currentLang: string;
  getTelegram: () => TelegramWebApp | null;
  hasTelegramLaunchParams: () => boolean;
  locationRef?: LocationRef;
  openExternalLink: (url: string) => void;
  openHiddenAnchor?: (url: string) => void;
  refreshTelegram: () => TelegramWebApp | null;
  setTelegram: (value: TelegramWebApp) => void;
};

export function openAppLinkTarget(url: string, options: OpenAppLinkOptions) {
  const raw = String(url || "").trim();
  if (isUnsafeAppUrl(raw)) return false;
  if (isHttpUrl(raw)) {
    options.openExternalLink(raw);
    return true;
  }

  const currentTg = options.getTelegram() || options.refreshTelegram();
  const gatewayUrl = options.hasTelegramLaunchParams()
    ? buildAppLaunchUrl(raw, options.locationRef || null, options.currentLang)
    : "";
  if (gatewayUrl) {
    if (currentTg?.openLink) {
      try {
        options.setTelegram(currentTg);
        currentTg.openLink(gatewayUrl);
        return true;
      } catch {
        // Fall back to regular browser navigation below.
      }
    }
    const assignLocation =
      options.assignLocation || ((target: string) => window.location.assign(target));
    assignLocation(gatewayUrl);
    return true;
  }

  if (/^tg:\/\//i.test(raw) && currentTg?.openTelegramLink) {
    try {
      options.setTelegram(currentTg);
      currentTg.openTelegramLink(raw);
      return true;
    } catch {
      // Fall back to the generic deeplink path below.
    }
  }

  const openHiddenAnchor = options.openHiddenAnchor || openUrlWithHiddenAnchor;
  openHiddenAnchor(raw);
  return true;
}
