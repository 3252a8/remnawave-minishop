import { createTelegramLaunch } from "./telegramLaunch.js";
import { createTelegramSdk } from "./telegramSdk";
import { shellState } from "./shellState.svelte";
import {
  applyPreferredTelegramViewportMode,
  createTelegramViewportBridge,
} from "./telegramViewport.js";
import {
  setTelegramEmojiDeviceStorage,
  type TelegramDeviceStorage,
} from "./telegramEmojiDeviceCache";

export type TelegramWebAppEvent =
  "fullscreenChanged" | "fullscreenFailed" | "activated" | "themeChanged";

export type TelegramWebApp = Record<string, unknown> & {
  initData?: string;
  DeviceStorage?: TelegramDeviceStorage;
  openInvoice?: (url: string, callback: (status: string) => void) => void;
  openLink?: (url: string, options?: Record<string, unknown>) => void;
  openTelegramLink?: (url: string) => void;
  showScanQrPopup?: (
    params: { text?: string },
    callback?: (text: string) => boolean | void
  ) => void;
  closeScanQrPopup?: () => void;
  platform?: string;
  isFullscreen?: boolean;
  isVersionAtLeast?: (version: string) => boolean;
  onEvent?: (eventType: TelegramWebAppEvent, eventHandler: () => void) => void;
  offEvent?: (eventType: TelegramWebAppEvent, eventHandler: () => void) => void;
  ready?: () => void;
  expand?: () => void;
  requestFullscreen?: () => void;
  exitFullscreen?: () => void;
};

export type TelegramMiniAppAuthTimeout = {
  signal?: AbortSignal;
  promise: Promise<unknown>;
  clear(): void;
  timedOut: boolean;
};

type TelegramSdkLike<Tg> = {
  initData: string;
  refresh(): Tg;
  hasLaunchParams(): boolean;
  load(timeoutMs?: number): Promise<Tg>;
  readInitDataFromLocation(): string;
  ensureForAction: () => Promise<Tg>;
  createMiniAppAuthTimeout: () => TelegramMiniAppAuthTimeout;
};

type CreateTelegramSdk<Tg> = (options: {
  scriptUrl: string;
  bootTimeoutMs: number;
  actionTimeoutMs: number;
  miniAppAuthTimeoutMs: number;
  onStatusChange: (status: string) => void;
  onInitDataChange: (initData: string) => void;
  onTelegramChange: (telegram: Tg) => void;
}) => TelegramSdkLike<Tg>;

export type TelegramRuntime<Tg> = {
  telegramSdk: TelegramSdkLike<Tg>;
  refreshTelegram: () => Tg;
  hasLaunchParams: () => boolean;
  load: (timeoutMs?: number) => Promise<Tg>;
  readInitDataFromLocation: () => string;
  prepareMiniApp: () => void;
  destroy: () => void;
};

export function createTelegramRuntime<Tg = TelegramWebApp | null>({
  actionTimeoutMs,
  bootTimeoutMs,
  createSdk = createTelegramSdk as unknown as CreateTelegramSdk<Tg>,
  miniAppAuthTimeoutMs,
  scriptUrl,
}: {
  actionTimeoutMs: number;
  bootTimeoutMs: number;
  createSdk?: CreateTelegramSdk<Tg>;
  miniAppAuthTimeoutMs: number;
  scriptUrl: string;
}): TelegramRuntime<Tg> {
  let destroyed = false;
  let preparationRequested = false;
  let currentWebApp: TelegramWebApp | null = null;
  let preparedWebApp: TelegramWebApp | null = null;

  function setInitData(initData: string) {
    if (destroyed) return;
    shellState.telegramMiniAppInitData = initData || "";
    if (initData) shellState.telegramHasLaunchParams = true;
  }

  function setStatus(status: string) {
    if (destroyed) return;
    shellState.telegramSdkStatus = status;
  }

  const viewportBridge = createTelegramViewportBridge();

  function prepareMiniApp() {
    if (destroyed) return;
    preparationRequested = true;
    const webApp = currentWebApp;
    if (!webApp || preparedWebApp === webApp) return;
    preparedWebApp = webApp;
    for (const prepare of [webApp.ready, webApp.expand]) {
      try {
        prepare?.call(webApp);
      } catch {
        // A client rejecting one capability must not prevent the viewport setup.
      }
    }
    try {
      applyPreferredTelegramViewportMode(webApp);
    } catch {
      // Expanded mode remains usable when the native fullscreen request fails.
    }
    viewportBridge.syncFullscreenState();
  }

  function setTelegram(telegram: Tg) {
    if (destroyed) return;
    const webApp = telegram as TelegramWebApp | null;
    currentWebApp = webApp;
    shellState.tg = webApp;
    viewportBridge.setTelegram(webApp);
    setTelegramEmojiDeviceStorage(
      webApp?.initData && webApp.isVersionAtLeast?.("9.0") ? (webApp.DeviceStorage ?? null) : null
    );
    if (preparationRequested) prepareMiniApp();
  }

  const telegramSdk = createSdk({
    scriptUrl,
    bootTimeoutMs,
    actionTimeoutMs,
    miniAppAuthTimeoutMs,
    onStatusChange: setStatus,
    onInitDataChange: (initData) => setInitData(initData || ""),
    onTelegramChange: setTelegram,
  });
  const telegramLaunch = createTelegramLaunch<Tg>({
    telegramSdk,
    defaultTimeoutMs: bootTimeoutMs,
    onLoaded: (value, initData) => {
      setTelegram(value);
      setInitData(initData || "");
    },
  });

  function refreshTelegram({ initial = false }: { initial?: boolean } = {}) {
    const telegram = telegramSdk.refresh();
    setTelegram(telegram);
    if (telegram) setStatus("ready");
    else if (initial) setStatus("idle");
    setInitData(telegramSdk.initData || "");
    return telegram;
  }

  refreshTelegram({ initial: true });

  return {
    telegramSdk,
    refreshTelegram,
    hasLaunchParams: telegramLaunch.hasLaunchParams,
    load: telegramLaunch.load,
    readInitDataFromLocation: telegramLaunch.readInitDataFromLocation,
    prepareMiniApp,
    destroy: () => {
      destroyed = true;
      viewportBridge.destroy();
    },
  };
}
