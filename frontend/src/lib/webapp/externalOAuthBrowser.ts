type TelegramBrowser = {
  initData?: string;
  openLink?: (url: string, options?: Record<string, unknown>) => void;
};

function telegramBrowser(): TelegramBrowser | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as Window & { Telegram?: { WebApp?: TelegramBrowser } }).Telegram?.WebApp;
}

/** The SDK is also loaded in ordinary browsers, where initData is empty. */
export function externalOAuthNeedsBrowser(provider: string, miniAppContext = false): boolean {
  return (
    ["google", "yandex", "discord"].includes(provider) &&
    (miniAppContext || Boolean(telegramBrowser()?.initData))
  );
}

/** Open a public cabinet URL, never a session, OAuth callback or linking token. */
export function openOAuthCabinetInBrowser(path: "/" | "/settings/security" = "/"): void {
  if (typeof window === "undefined") return;
  const url = new URL(path, window.location.origin).href;
  const telegram = telegramBrowser();
  if (telegram?.openLink) {
    try {
      telegram.openLink(url, { try_instant_view: false });
      return;
    } catch {
      // Older clients may not expose the external-link method. Never navigate
      // the Mini App to OAuth as a fallback: providers reject its WebView.
    }
  }
  window.open(url, "_blank", "noopener,noreferrer");
}
