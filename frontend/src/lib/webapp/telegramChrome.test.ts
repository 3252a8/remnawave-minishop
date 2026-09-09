import { afterEach, describe, expect, it, vi } from "vitest";

import {
  syncTelegramChrome,
  systemColorSchemeFromMedia,
  telegramColorScheme,
  watchTelegramColorScheme,
} from "./telegramChrome.js";

function host(version: string) {
  return {
    colorScheme: "light",
    isVersionAtLeast: (required: string) =>
      Number.parseFloat(version) >= Number.parseFloat(required),
    setBackgroundColor: vi.fn(),
    setHeaderColor: vi.fn(),
    setBottomBarColor: vi.fn(),
  };
}

describe("syncTelegramChrome", () => {
  it("paints backdrop, header, and bottom bar on a recent client", () => {
    const tg = host("7.10");
    syncTelegramChrome(tg, { bg: "#f7faff" });
    expect(tg.setBackgroundColor).toHaveBeenCalledWith("#f7faff");
    expect(tg.setHeaderColor).toHaveBeenCalledWith("#f7faff");
    expect(tg.setBottomBarColor).toHaveBeenCalledWith("#f7faff");
  });

  it("touches only the backdrop on 6.1: hex headers landed in 6.9", () => {
    const tg = host("6.1");
    syncTelegramChrome(tg, { bg: "#070d18" });
    expect(tg.setBackgroundColor).toHaveBeenCalledWith("#070d18");
    expect(tg.setHeaderColor).not.toHaveBeenCalled();
    expect(tg.setBottomBarColor).not.toHaveBeenCalled();
  });

  it("ignores a non-hex background: Telegram accepts hex only", () => {
    const tg = host("7.10");
    syncTelegramChrome(tg, { bg: "rgba(0, 0, 0, 0.5)" });
    expect(tg.setBackgroundColor).not.toHaveBeenCalled();
  });

  it("uses the computed root background for CSS-file themes", () => {
    const tg = host("7.10");
    vi.stubGlobal("document", { documentElement: {} });
    vi.stubGlobal("getComputedStyle", () => ({ getPropertyValue: () => " #008080 " }));
    syncTelegramChrome(tg, { color_scheme: "light", style_preset: "win95" });
    expect(tg.setBackgroundColor).toHaveBeenCalledWith("#008080");
    expect(tg.setHeaderColor).toHaveBeenCalledWith("#008080");
  });

  it("stays silent outside Telegram", () => {
    expect(() => syncTelegramChrome(null, { bg: "#ffffff" })).not.toThrow();
  });

  it("survives a client rejecting the call", () => {
    const tg = {
      ...host("7.10"),
      setHeaderColor: vi.fn(() => {
        throw new Error("rejected");
      }),
    };
    expect(() => syncTelegramChrome(tg, { bg: "#ffffff" })).not.toThrow();
  });
});

describe("telegramColorScheme", () => {
  it("returns only light or dark", () => {
    expect(telegramColorScheme({ colorScheme: "light" })).toBe("light");
    expect(telegramColorScheme({ colorScheme: "DARK" })).toBe("dark");
    expect(telegramColorScheme({ colorScheme: "sepia" })).toBe("");
    expect(telegramColorScheme(null)).toBe("");
  });
});

describe("watchTelegramColorScheme", () => {
  it("subscribes to themeChanged and unsubscribes", () => {
    const handlers: Array<() => void> = [];
    const tg = {
      colorScheme: "dark",
      onEvent: vi.fn((_event: "themeChanged", handler: () => void) => handlers.push(handler)),
      offEvent: vi.fn(),
    };
    const seen: string[] = [];
    const stop = watchTelegramColorScheme(tg, (scheme) => seen.push(scheme));
    handlers[0]?.();
    expect(seen).toEqual(["dark"]);
    stop();
    expect(tg.offEvent).toHaveBeenCalled();
  });

  it("returns a no-op when the SDK has no events", () => {
    expect(() => watchTelegramColorScheme({ colorScheme: "dark" }, () => {})()).not.toThrow();
  });
});

// The node test environment has no matchMedia, so the queries are stubbed the
// same way the neighbouring storage tests stub window.
function stubMatchMedia(matching: string[]) {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      matchMedia: (query: string) => ({ matches: matching.includes(query) }),
    },
  });
}

afterEach(() => {
  Reflect.deleteProperty(globalThis, "window");
  vi.unstubAllGlobals();
});

describe("systemColorSchemeFromMedia", () => {
  it("reports the matching scheme", () => {
    stubMatchMedia(["(prefers-color-scheme: light)"]);
    expect(systemColorSchemeFromMedia()).toBe("light");
    stubMatchMedia(["(prefers-color-scheme: dark)"]);
    expect(systemColorSchemeFromMedia()).toBe("dark");
  });

  it("reports no signal where prefers-color-scheme is unsupported", () => {
    // Both queries stay unmatched: answering "dark" here would override the
    // admin theme on nothing but a missing media feature.
    stubMatchMedia([]);
    expect(systemColorSchemeFromMedia()).toBe("");
  });

  it("reports no signal without matchMedia at all", () => {
    Object.defineProperty(globalThis, "window", { configurable: true, value: {} });
    expect(systemColorSchemeFromMedia()).toBe("");
  });
});
