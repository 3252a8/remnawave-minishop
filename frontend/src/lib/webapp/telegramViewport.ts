type TelegramViewportEvent = "fullscreenChanged" | "fullscreenFailed" | "activated";

export type TelegramViewportWebApp = {
  exitFullscreen?: () => void;
  isFullscreen?: boolean;
  isVersionAtLeast?: (version: string) => boolean;
  onEvent?: (eventType: TelegramViewportEvent, eventHandler: () => void) => void;
  offEvent?: (eventType: TelegramViewportEvent, eventHandler: () => void) => void;
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
const VIEWPORT_EVENTS: TelegramViewportEvent[] = [
  "fullscreenChanged",
  "fullscreenFailed",
  "activated",
];

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
    for (const event of VIEWPORT_EVENTS) telegram?.offEvent?.(event, handleFullscreenChanged);
    telegram = next;
    for (const event of VIEWPORT_EVENTS) telegram?.onEvent?.(event, handleFullscreenChanged);
    syncFullscreenState({ clearRequested: !next });
  }

  function destroy() {
    for (const event of VIEWPORT_EVENTS) telegram?.offEvent?.(event, handleFullscreenChanged);
    telegram = null;
    root?.removeAttribute(FULLSCREEN_ATTRIBUTE);
    root?.removeAttribute(FULLSCREEN_REQUESTED_ATTRIBUTE);
  }

  return { destroy, setTelegram, syncFullscreenState };
}
