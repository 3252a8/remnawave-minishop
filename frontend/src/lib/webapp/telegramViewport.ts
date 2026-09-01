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
const FULLSCREEN_REQUESTED_ATTRIBUTE = "data-telegram-fullscreen-requested";
const MOBILE_FULLSCREEN_PLATFORMS = new Set(["android", "android_x", "ios"]);
const DESKTOP_FULLSIZE_PLATFORMS = new Set(["macos", "tdesktop", "unigram", "weba", "webk"]);

export function applyPreferredTelegramViewportMode(
  telegram: TelegramViewportWebApp,
  {
    root = typeof document === "undefined" ? null : document.documentElement,
  }: { root?: AttributeHost | null } = {}
) {
  const platform = String(telegram.platform || "")
    .trim()
    .toLowerCase();
  if (MOBILE_FULLSCREEN_PLATFORMS.has(platform)) {
    const requestFullscreen = telegram.requestFullscreen;
    if (
      telegram.isFullscreen !== true &&
      telegram.isVersionAtLeast?.("8.0") !== false &&
      requestFullscreen
    ) {
      root?.setAttribute(FULLSCREEN_REQUESTED_ATTRIBUTE, "true");
      try {
        requestFullscreen.call(telegram);
      } catch (error) {
        root?.removeAttribute(FULLSCREEN_REQUESTED_ATTRIBUTE);
        throw error;
      }
    }
    return;
  }
  root?.removeAttribute(FULLSCREEN_REQUESTED_ATTRIBUTE);
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

  function syncFullscreenState({ clearRequested = false }: { clearRequested?: boolean } = {}) {
    if (!root) return;
    if (telegram?.isFullscreen === true) {
      root.setAttribute(FULLSCREEN_ATTRIBUTE, "true");
      root.removeAttribute(FULLSCREEN_REQUESTED_ATTRIBUTE);
    } else {
      root.removeAttribute(FULLSCREEN_ATTRIBUTE);
      if (clearRequested) root.removeAttribute(FULLSCREEN_REQUESTED_ATTRIBUTE);
    }
  }

  function handleFullscreenChanged() {
    syncFullscreenState({ clearRequested: true });
  }

  function setTelegram(next: TelegramViewportWebApp | null) {
    if (telegram === next) {
      syncFullscreenState();
      return;
    }
    telegram?.offEvent?.("fullscreenChanged", handleFullscreenChanged);
    telegram = next;
    telegram?.onEvent?.("fullscreenChanged", handleFullscreenChanged);
    syncFullscreenState();
  }

  function destroy() {
    telegram?.offEvent?.("fullscreenChanged", handleFullscreenChanged);
    telegram = null;
    root?.removeAttribute(FULLSCREEN_ATTRIBUTE);
    root?.removeAttribute(FULLSCREEN_REQUESTED_ATTRIBUTE);
  }

  return { destroy, setTelegram, syncFullscreenState };
}
