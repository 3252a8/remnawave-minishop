import { describe, expect, it, vi } from "vitest";

import {
  applyPreferredTelegramViewportMode,
  createTelegramViewportBridge,
  type TelegramViewportWebApp,
} from "./telegramViewport.js";

function makeRoot() {
  const attributes = new Map<string, string>();
  return {
    attributes,
    removeAttribute: vi.fn((name: string) => attributes.delete(name)),
    setAttribute: vi.fn((name: string, value: string) => attributes.set(name, value)),
  };
}

function makeTelegram(isFullscreen = false) {
  const handlers = new Map<string, () => void>();
  const telegram: TelegramViewportWebApp = {
    isFullscreen,
    offEvent: vi.fn((eventType, handler) => {
      if (handlers.get(eventType) === handler) handlers.delete(eventType);
    }),
    onEvent: vi.fn((eventType, handler) => handlers.set(eventType, handler)),
  };
  return { handlers, telegram };
}

describe("createTelegramViewportBridge", () => {
  it("tracks the current Telegram fullscreen state", () => {
    const root = makeRoot();
    const { handlers, telegram } = makeTelegram();
    const bridge = createTelegramViewportBridge({ root });

    bridge.setTelegram(telegram);
    expect(root.attributes.has("data-telegram-fullscreen")).toBe(false);

    telegram.isFullscreen = true;
    handlers.get("fullscreenChanged")?.();
    expect(root.attributes.get("data-telegram-fullscreen")).toBe("true");

    telegram.isFullscreen = false;
    handlers.get("fullscreenChanged")?.();
    expect(root.attributes.has("data-telegram-fullscreen")).toBe(false);
  });

  it("moves the listener when the Telegram instance changes and cleans up", () => {
    const root = makeRoot();
    const first = makeTelegram(true);
    const second = makeTelegram(false);
    const bridge = createTelegramViewportBridge({ root });

    bridge.setTelegram(first.telegram);
    bridge.setTelegram(second.telegram);
    expect(first.telegram.offEvent).toHaveBeenCalledWith("fullscreenChanged", expect.any(Function));
    expect(root.attributes.has("data-telegram-fullscreen")).toBe(false);

    bridge.destroy();
    expect(second.telegram.offEvent).toHaveBeenCalledWith(
      "fullscreenChanged",
      expect.any(Function)
    );
    expect(root.attributes.has("data-telegram-fullscreen")).toBe(false);
  });
});

describe("applyPreferredTelegramViewportMode", () => {
  it.each(["android", "android_x", "ios"])("requests fullscreen on %s", (platform) => {
    const requestFullscreen = vi.fn();
    const exitFullscreen = vi.fn();

    applyPreferredTelegramViewportMode({
      exitFullscreen,
      isFullscreen: false,
      isVersionAtLeast: () => true,
      platform,
      requestFullscreen,
    });

    expect(requestFullscreen).toHaveBeenCalledOnce();
    expect(exitFullscreen).not.toHaveBeenCalled();
  });

  it.each(["macos", "tdesktop", "unigram", "weba", "webk"])(
    "returns %s to fullsize when Telegram opened it in fullscreen",
    (platform) => {
      const requestFullscreen = vi.fn();
      const exitFullscreen = vi.fn();

      applyPreferredTelegramViewportMode({
        exitFullscreen,
        isFullscreen: true,
        platform,
        requestFullscreen,
      });

      expect(exitFullscreen).toHaveBeenCalledOnce();
      expect(requestFullscreen).not.toHaveBeenCalled();
    }
  );

  it("does not force a viewport mode on unknown platforms", () => {
    const requestFullscreen = vi.fn();
    const exitFullscreen = vi.fn();

    applyPreferredTelegramViewportMode({
      exitFullscreen,
      isFullscreen: true,
      platform: "unknown-client",
      requestFullscreen,
    });

    expect(requestFullscreen).not.toHaveBeenCalled();
    expect(exitFullscreen).not.toHaveBeenCalled();
  });

  it("keeps the expanded fallback on mobile clients older than Bot API 8.0", () => {
    const requestFullscreen = vi.fn();

    applyPreferredTelegramViewportMode({
      isFullscreen: false,
      isVersionAtLeast: () => false,
      platform: "ios",
      requestFullscreen,
    });

    expect(requestFullscreen).not.toHaveBeenCalled();
  });
});
