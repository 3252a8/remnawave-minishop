import { afterEach, describe, expect, it, vi } from "vitest";
import { externalOAuthNeedsBrowser, openOAuthCabinetInBrowser } from "./externalOAuthBrowser";

afterEach(() => vi.unstubAllGlobals());

function installBrowser(initData = "") {
  const openLink = vi.fn();
  const assign = vi.fn();
  const open = vi.fn();
  vi.stubGlobal("window", {
    location: { origin: "https://shop.example", assign },
    Telegram: { WebApp: { initData, openLink } },
    open,
  });
  return { openLink, assign, open };
}

describe("external OAuth in Telegram", () => {
  it.each(["google", "yandex", "discord"])("blocks %s only inside Mini App", (provider) => {
    installBrowser();
    expect(externalOAuthNeedsBrowser(provider)).toBe(false);
    expect(externalOAuthNeedsBrowser(provider, true)).toBe(true);
    installBrowser("telegram-signed-data");
    expect(externalOAuthNeedsBrowser(provider)).toBe(true);
  });

  it.each(["telegram", "email", "passkey", "qr"])("keeps %s available", (provider) => {
    installBrowser("telegram-signed-data");
    expect(externalOAuthNeedsBrowser(provider, true)).toBe(false);
  });

  it("opens only the public cabinet URL in the external browser", () => {
    const { openLink, assign, open } = installBrowser("secret-session-data");
    openOAuthCabinetInBrowser("/settings/security");
    expect(openLink).toHaveBeenCalledWith("https://shop.example/settings/security", {
      try_instant_view: false,
    });
    expect(assign).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });

  it("never falls back to replacing the WebView when Telegram rejects openLink", () => {
    const { openLink, assign, open } = installBrowser("telegram-signed-data");
    openLink.mockImplementation(() => {
      throw new Error("unavailable");
    });
    openOAuthCabinetInBrowser();
    expect(assign).not.toHaveBeenCalled();
    expect(open).toHaveBeenCalledWith("https://shop.example/", "_blank", "noopener,noreferrer");
  });

  it("is safe when rendered without a browser", () => {
    vi.stubGlobal("window", undefined);
    expect(externalOAuthNeedsBrowser("google")).toBe(false);
    expect(() => openOAuthCabinetInBrowser()).not.toThrow();
  });
});
