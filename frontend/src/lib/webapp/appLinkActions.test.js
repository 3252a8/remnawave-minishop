import { describe, expect, it, vi } from "vitest";

import { openAppLinkTarget } from "./appLinkActions.js";

function makeOptions(overrides = {}) {
  return {
    assignLocation: vi.fn(),
    currentLang: "en",
    getTelegram: () => null,
    hasTelegramLaunchParams: () => false,
    locationRef: { href: "https://shop.example.test/current" },
    openExternalLink: vi.fn(),
    openHiddenAnchor: vi.fn(),
    refreshTelegram: () => null,
    setTelegram: vi.fn(),
    ...overrides,
  };
}

describe("openAppLinkTarget", () => {
  it("rejects unsafe app URLs", () => {
    const options = makeOptions();

    expect(openAppLinkTarget("javascript:alert(1)", options)).toBe(false);

    expect(options.openExternalLink).not.toHaveBeenCalled();
    expect(options.openHiddenAnchor).not.toHaveBeenCalled();
  });

  it("opens HTTP URLs through the external-link path", () => {
    const options = makeOptions();

    expect(openAppLinkTarget(" https://example.test/path ", options)).toBe(true);

    expect(options.openExternalLink).toHaveBeenCalledWith("https://example.test/path");
  });

  it("uses Telegram openLink for mini-app gateway URLs", () => {
    const tg = { openLink: vi.fn() };
    const options = makeOptions({
      getTelegram: () => tg,
      hasTelegramLaunchParams: () => true,
    });

    expect(openAppLinkTarget("vless://profile", options)).toBe(true);

    expect(options.setTelegram).toHaveBeenCalledWith(tg);
    expect(tg.openLink).toHaveBeenCalledOnce();
    expect(tg.openLink.mock.calls[0][0]).toContain("https://shop.example.test/open-app?lang=en#");
    expect(options.assignLocation).not.toHaveBeenCalled();
  });

  it("falls back to browser navigation when Telegram openLink fails", () => {
    const tg = {
      openLink: vi.fn(() => {
        throw new Error("blocked");
      }),
    };
    const options = makeOptions({
      getTelegram: () => tg,
      hasTelegramLaunchParams: () => true,
    });

    expect(openAppLinkTarget("vless://profile", options)).toBe(true);

    expect(options.assignLocation).toHaveBeenCalledOnce();
    expect(options.assignLocation.mock.calls[0][0]).toContain("/open-app?lang=en#");
  });

  it("uses Telegram deeplink API when available", () => {
    const tg = { openTelegramLink: vi.fn() };
    const options = makeOptions({
      refreshTelegram: () => tg,
    });

    expect(openAppLinkTarget("tg://resolve?domain=bot", options)).toBe(true);

    expect(options.setTelegram).toHaveBeenCalledWith(tg);
    expect(tg.openTelegramLink).toHaveBeenCalledWith("tg://resolve?domain=bot");
  });

  it("falls back to the hidden-anchor opener", () => {
    const options = makeOptions();

    expect(openAppLinkTarget("vless://profile", options)).toBe(true);

    expect(options.openHiddenAnchor).toHaveBeenCalledWith("vless://profile");
  });
});
