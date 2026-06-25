import { createTelegramLaunch } from "./telegramLaunch.js";
import { createTelegramSdk } from "./telegramSdk.js";

export type TelegramWebApp = Record<string, unknown> & {
  initData?: string;
  openInvoice?: (url: string, callback: (status: string) => void) => void;
  openLink?: (url: string, options?: Record<string, unknown>) => void;
  openTelegramLink?: (url: string) => void;
  platform?: string;
  ready?: () => void;
  expand?: () => void;
};

type TelegramSdkLike<Tg> = {
  initData: string;
  refresh(): Tg;
  hasLaunchParams(): boolean;
  load(timeoutMs?: number): Promise<Tg>;
  readInitDataFromLocation(): string;
  ensureForAction?: () => Promise<Tg>;
  createMiniAppAuthTimeout?: () => unknown;
};

type CreateTelegramSdk<Tg> = (options: {
  scriptUrl: string;
  bootTimeoutMs: number;
  actionTimeoutMs: number;
  miniAppAuthTimeoutMs: number;
  onStatusChange: (status: string) => void;
  onInitDataChange: (initData: string) => void;
}) => TelegramSdkLike<Tg>;

export type TelegramRuntime<Tg> = {
  telegramSdk: TelegramSdkLike<Tg>;
  refreshTelegram: () => Tg;
  hasLaunchParams: () => boolean;
  load: (timeoutMs?: number) => Promise<Tg>;
  readInitDataFromLocation: () => string;
};

export function createTelegramRuntime<Tg = TelegramWebApp | null>({
  actionTimeoutMs,
  bootTimeoutMs,
  createSdk = createTelegramSdk as unknown as CreateTelegramSdk<Tg>,
  miniAppAuthTimeoutMs,
  scriptUrl,
  setInitData,
  setStatus,
  setTelegram,
}: {
  actionTimeoutMs: number;
  bootTimeoutMs: number;
  createSdk?: CreateTelegramSdk<Tg>;
  miniAppAuthTimeoutMs: number;
  scriptUrl: string;
  setInitData: (initData: string) => void;
  setStatus: (status: string) => void;
  setTelegram: (telegram: Tg) => void;
}): TelegramRuntime<Tg> {
  const telegramSdk = createSdk({
    scriptUrl,
    bootTimeoutMs,
    actionTimeoutMs,
    miniAppAuthTimeoutMs,
    onStatusChange: setStatus,
    onInitDataChange: (initData) => setInitData(initData || ""),
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
  };
}
