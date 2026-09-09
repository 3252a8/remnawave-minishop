// Keeps the Telegram chrome in sync with the active theme.
//
// The header and the backdrop around a Mini App are drawn by the Telegram client
// itself, which by default takes them from its own theme. With a light app theme
// that yields a dark header above a white screen, so every theme change repaints
// the chrome with the theme background.
//
// Bot API versions: setBackgroundColor since 6.1, hex in setHeaderColor since
// 6.9, setBottomBarColor since 7.10 — older clients simply lack the methods.

type ColorSetter = (color: string) => unknown;

export type TelegramChromeHost = {
  colorScheme?: unknown;
  isVersionAtLeast?: (version: string) => boolean;
  setHeaderColor?: ColorSetter;
  setBackgroundColor?: ColorSetter;
  setBottomBarColor?: ColorSetter;
  onEvent?: (event: "themeChanged", handler: () => void) => unknown;
  offEvent?: (event: "themeChanged", handler: () => void) => unknown;
} | null;

const HEX_COLOR = /^#[0-9a-f]{6}$/i;

function hexOrEmpty(value: unknown): string {
  const raw = String(value || "").trim();
  return HEX_COLOR.test(raw) ? raw : "";
}

function supports(tg: TelegramChromeHost, version: string): boolean {
  if (!tg) return false;
  if (typeof tg.isVersionAtLeast !== "function") return true;
  try {
    return Boolean(tg.isVersionAtLeast(version));
  } catch {
    return false;
  }
}

function rootThemeBackground(): string {
  if (typeof document === "undefined" || typeof getComputedStyle !== "function") return "";
  try {
    return hexOrEmpty(getComputedStyle(document.documentElement).getPropertyValue("--bg"));
  } catch {
    return "";
  }
}

/**
 * Paints the Telegram header, backdrop, and bottom bar with the theme
 * background. A no-op outside Telegram and on clients without those methods.
 */
export function syncTelegramChrome(
  tg: TelegramChromeHost,
  tokens: Record<string, unknown> | null | undefined
): void {
  if (!tg) return;
  const background = hexOrEmpty(tokens?.bg) || rootThemeBackground();
  if (!background) return;

  if (typeof tg.setBackgroundColor === "function" && supports(tg, "6.1")) {
    try {
      tg.setBackgroundColor(background);
    } catch {
      // The client may reject the call; the in-page theme still applies.
    }
  }
  if (typeof tg.setHeaderColor === "function" && supports(tg, "6.9")) {
    try {
      tg.setHeaderColor(background);
    } catch {
      // See above.
    }
  }
  if (typeof tg.setBottomBarColor === "function" && supports(tg, "7.10")) {
    try {
      tg.setBottomBarColor(background);
    } catch {
      // See above.
    }
  }
}

/** The Telegram client's light or dark scheme, when it reports one. */
export function telegramColorScheme(tg: TelegramChromeHost): string {
  const scheme = String(tg?.colorScheme || "")
    .trim()
    .toLowerCase();
  return scheme === "light" || scheme === "dark" ? scheme : "";
}

/**
 * Subscribes to theme changes in the Telegram client. Returns an unsubscribe
 * function, or a no-op when the SDK has no event support.
 */
export function watchTelegramColorScheme(
  tg: TelegramChromeHost,
  onChange: (scheme: string) => void
): () => void {
  if (!tg || typeof tg.onEvent !== "function") return () => {};
  const handler = () => onChange(telegramColorScheme(tg));
  try {
    tg.onEvent("themeChanged", handler);
  } catch {
    return () => {};
  }
  return () => {
    try {
      if (typeof tg.offEvent === "function") tg.offEvent("themeChanged", handler);
    } catch {
      // Best-effort unsubscribe: the page is going away as a whole anyway.
    }
  };
}

/**
 * The browser scheme, used when Telegram does not report one. Both queries are
 * probed on purpose: where prefers-color-scheme is unsupported neither matches,
 * and the answer is "no signal" rather than dark — reporting dark there would
 * override the admin's theme on nothing but a missing media feature.
 */
export function systemColorSchemeFromMedia(): string {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return "";
  try {
    if (window.matchMedia("(prefers-color-scheme: light)").matches) return "light";
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
    return "";
  } catch {
    return "";
  }
}

/** Subscribes to prefers-color-scheme; returns an unsubscribe function. */
export function watchMediaColorScheme(onChange: (scheme: string) => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  let query: MediaQueryList;
  try {
    query = window.matchMedia("(prefers-color-scheme: light)");
  } catch {
    return () => {};
  }
  // A light <-> dark switch always flips this query, so one subscription is
  // enough; the scheme itself is re-read so an unsupported feature stays "".
  const handler = () => onChange(systemColorSchemeFromMedia());
  if (typeof query.addEventListener === "function") {
    query.addEventListener("change", handler);
    return () => query.removeEventListener("change", handler);
  }
  return () => {};
}
