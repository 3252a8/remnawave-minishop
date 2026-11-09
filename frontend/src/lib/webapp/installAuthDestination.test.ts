import { afterEach, describe, expect, it, vi } from "vitest";
import { buildExternalOAuthStartUrl, buildTelegramOAuthStartUrl } from "./authHelpers";
import {
  rememberInstallAuthDestination,
  restoreInstallAuthDestination,
} from "./installAuthDestination";

function installBrowser(path = "/install?platform=ios&app=client-v2") {
  const values = new Map<string, string>();
  const browser = {
    location: new URL(`https://shop.test${path}`),
    sessionStorage: {
      getItem: vi.fn((key: string) => values.get(key) || null),
      setItem: vi.fn((key: string, value: string) => values.set(key, value)),
      removeItem: vi.fn((key: string) => values.delete(key)),
    },
    history: {
      replaceState: vi.fn((_state: unknown, _title: string, path: string) => {
        browser.location = new URL(path, browser.location);
      }),
    },
  };
  vi.stubGlobal("window", browser);
  return { browser, values };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("install destination through authentication", () => {
  it.each([
    "google",
    "yandex",
    "vk",
    "github",
    "discord",
    "telegram",
    "password",
    "email",
    "passkey",
  ])("retains a plugin request through %s login, including the password screen", (provider) => {
    const request = "12".repeat(16);
    const { browser } = installBrowser(`/extensions/sample-client/connect?request=${request}`);
    rememberInstallAuthDestination("login");
    browser.location = new URL("https://shop.test/login/password");
    if (provider === "telegram") buildTelegramOAuthStartUrl();
    else if (!["password", "email", "passkey"].includes(provider))
      buildExternalOAuthStartUrl(provider, "login", "ru");
    browser.location = new URL(`https://shop.test/?external_auth=${provider}:success`);
    expect(restoreInstallAuthDestination(true)).toBe(true);
    expect(browser.location.pathname).toBe("/extensions/sample-client/connect");
    expect(browser.location.searchParams.get("request")).toBe(request);
    expect(browser.location.searchParams.get("external_auth")).toBe(`${provider}:success`);
    expect(restoreInstallAuthDestination(true)).toBe(false);
  });

  it("does not replay stale authentication parameters from a plugin URL", () => {
    const { browser } = installBrowser(
      "/extensions/sample-client/connect?request=pending&code=old&state=old&external_auth=old"
    );
    rememberInstallAuthDestination("login");
    browser.location = new URL("https://shop.test/?telegram_auth=success");
    expect(restoreInstallAuthDestination()).toBe(true);
    expect(browser.location.searchParams.get("request")).toBe("pending");
    expect(browser.location.searchParams.has("code")).toBe(false);
    expect(browser.location.searchParams.has("state")).toBe(false);
    expect(browser.location.searchParams.has("external_auth")).toBe(false);
  });

  it.each([
    "?external_auth=google:success",
    "?external_auth=google:cancelled",
    "?telegram_auth=success",
    "?telegram_auth=cancelled",
  ])("restores the scoped destination once after %s", (status) => {
    const { browser, values } = installBrowser();
    rememberInstallAuthDestination("login");
    browser.location = new URL(`https://shop.test/${status}`);
    expect(restoreInstallAuthDestination()).toBe(true);
    expect(browser.location.pathname).toBe("/install");
    expect(browser.location.searchParams.get("platform")).toBe("ios");
    expect(browser.location.searchParams.get("app")).toBe("client-v2");
    expect(values.size).toBe(0);
    expect(restoreInstallAuthDestination()).toBe(false);
  });

  it("retains the destination while the sign-in screen switches to password mode", () => {
    const { browser, values } = installBrowser();
    rememberInstallAuthDestination("login");
    browser.location = new URL("https://shop.test/login/password");
    buildExternalOAuthStartUrl("google", "login", "en");
    expect(values.size).toBe(1);
    buildTelegramOAuthStartUrl();
    expect(values.size).toBe(1);
    expect(restoreInstallAuthDestination(true)).toBe(true);
    expect(browser.location.pathname).toBe("/install");
  });

  it("does not replace a newer checkout, account linking, or merging destination", () => {
    const { browser, values } = installBrowser();
    rememberInstallAuthDestination("login");
    browser.location = new URL(`https://shop.test/checkout/${"ab".repeat(16)}`);
    expect(buildExternalOAuthStartUrl("google", "login", "en")).toContain("tariff_access=");
    expect(values.size).toBe(0);
    expect(restoreInstallAuthDestination(true)).toBe(false);
    for (const purpose of ["link", "merge"] as const) {
      browser.location = new URL("https://shop.test/install?platform=ios");
      rememberInstallAuthDestination("login");
      buildExternalOAuthStartUrl("google", purpose, "en");
      expect(values.size).toBe(0);
    }
  });

  it("discards a pending destination when a newer page opens sign-in", () => {
    const { browser, values } = installBrowser();
    rememberInstallAuthDestination("login");
    browser.location = new URL("https://shop.test/support");
    expect(restoreInstallAuthDestination(true)).toBe(false);
    expect(browser.location.pathname).toBe("/support");
    expect(values.size).toBe(0);
    browser.location = new URL("https://shop.test/install?platform=ios");
    rememberInstallAuthDestination("login");
    browser.location = new URL("https://shop.test/");
    rememberInstallAuthDestination("login");
    expect(values.size).toBe(0);
  });

  it("rejects expired and arbitrary redirect destinations", () => {
    const { browser, values } = installBrowser();
    rememberInstallAuthDestination("login");
    const key = [...values.keys()][0];
    browser.location = new URL("https://shop.test/?telegram_auth=success");
    for (const saved of [
      { pathname: "/install", expiresAt: Date.now() - 1 },
      { pathname: "//evil.test/install", expiresAt: Date.now() + 1000 },
      { pathname: "/settings/security", expiresAt: Date.now() + 1000 },
    ]) {
      values.set(key, JSON.stringify(saved));
      expect(restoreInstallAuthDestination()).toBe(false);
      expect(browser.location.pathname).toBe("/");
      expect(values.size).toBe(0);
    }
  });

  it("keeps sign-in available when session storage is blocked", () => {
    const { browser } = installBrowser();
    browser.sessionStorage.setItem.mockImplementation(() => {
      throw Error("blocked");
    });
    browser.sessionStorage.getItem.mockImplementation(() => {
      throw Error("blocked");
    });
    expect(() => buildTelegramOAuthStartUrl()).not.toThrow();
    expect(() => buildExternalOAuthStartUrl("google", "login", "en")).not.toThrow();
    browser.location = new URL("https://shop.test/?telegram_auth=success");
    expect(restoreInstallAuthDestination()).toBe(false);
  });
});
