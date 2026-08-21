export type TelegramViewportWebApp = {
  exitFullscreen?: () => void;
  isFullscreen?: boolean;
  isVersionAtLeast?: (version: string) => boolean;
  onEvent?: (eventType: "fullscreenChanged", eventHandler: () => void) => void;
  offEvent?: (eventType: "fullscreenChanged", eventHandler: () => void) => void;
  platform?: string;
  requestFullscreen?: () => void;
};

type AttributeHost = {
  removeAttribute(name: string): void;
  setAttribute(name: string, value: string): void;
};

const FULLSCREEN_ATTRIBUTE = "data-telegram-fullscreen";
const MOBILE_FULLSCREEN_PLATFORMS = new Set(["android", "android_x", "ios"]);
const DESKTOP_FULLSIZE_PLATFORMS = new Set(["macos", "tdesktop", "unigram", "weba", "webk"]);

export function applyPreferredTelegramViewportMode(telegram: TelegramViewportWebApp) {
  const platform = String(telegram.platform || "")
    .trim()
    .toLowerCase();
  if (MOBILE_FULLSCREEN_PLATFORMS.has(platform)) {
    if (telegram.isFullscreen !== true && telegram.isVersionAtLeast?.("8.0") !== false) {
      telegram.requestFullscreen?.();
    }
    return;
  }
  if (DESKTOP_FULLSIZE_PLATFORMS.has(platform) && telegram.isFullscreen === true) {
    telegram.exitFullscreen?.();
  }
}

export function createTelegramViewportBridge({
  root = typeof document === "undefined" ? null : document.documentElement,
}: {
  root?: AttributeHost | null;
} = {}) {
  let telegram: TelegramViewportWebApp | null = null;

  function syncFullscreenState() {
    if (!root) return;
    if (telegram?.isFullscreen === true) {
      root.setAttribute(FULLSCREEN_ATTRIBUTE, "true");
    } else {
      root.removeAttribute(FULLSCREEN_ATTRIBUTE);
    }
  }

  function setTelegram(next: TelegramViewportWebApp | null) {
    if (telegram === next) {
      syncFullscreenState();
      return;
    }
    telegram?.offEvent?.("fullscreenChanged", syncFullscreenState);
    telegram = next;
    telegram?.onEvent?.("fullscreenChanged", syncFullscreenState);
    syncFullscreenState();
  }

  function destroy() {
    telegram?.offEvent?.("fullscreenChanged", syncFullscreenState);
    telegram = null;
    root?.removeAttribute(FULLSCREEN_ATTRIBUTE);
  }

  return { destroy, setTelegram, syncFullscreenState };
}
