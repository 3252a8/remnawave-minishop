import { afterEach, describe, expect, it, vi } from "vitest";

import { createTelegramSdk } from "./telegramSdk.js";

function installBrowser(storedParams: string | null = null, hash = "") {
  const getItem = vi.fn((key: string) => (key === "__telegram__initParams" ? storedParams : null));
  vi.stubGlobal("window", {
    location: { search: "", hash },
    sessionStorage: { getItem },
    clearTimeout,
    setTimeout,
  });
  return { getItem };
}

afterEach(() => vi.unstubAllGlobals());

describe("Telegram SDK launch detection", () => {
  it("recognizes the original Telegram hash", () => {
    installBrowser(null, "#tgWebAppVersion=8.0&tgWebAppPlatform=ios");
    expect(createTelegramSdk().hasLaunchParams()).toBe(true);
  });

  it.each([
    { tgWebAppData: "signed-launch-data" },
    { tgWebAppVersion: "8.0", tgWebAppPlatform: "ios" },
    { tgWebAppVersion: "9.1", tgWebAppPlatform: "android", tgWebAppData: "" },
  ])("restores SDK launch evidence without copying it into URLs: %j", (params) => {
    installBrowser(JSON.stringify(params));
    const sdk = createTelegramSdk();
    expect(sdk.hasLaunchParams()).toBe(true);
    // Authentication data comes from the official SDK after loading, not this probe.
    expect(sdk.initData).toBe("");
    expect(window.location.hash).toBe("");
    expect(window.location.search).toBe("");
  });

  it.each([
    null,
    "broken JSON",
    "null",
    "[]",
    '"launch-data"',
    "{}",
    '{"tgWebAppData":{}}',
    '{"tgWebAppData":" "}',
    '{"tgWebAppVersion":"8.0"}',
    '{"tgWebAppVersion":"8.0","tgWebAppPlatform":"unknown"}',
    '{"tgWebAppVersion":8,"tgWebAppPlatform":"ios"}',
    '{"tgWebAppVersion":"invalid","tgWebAppPlatform":"ios"}',
    '{"tgWebAppThemeParams":"{}","tgWebAppFullscreen":"1"}',
  ])("does not treat ordinary/corrupt browser storage as Telegram: %s", (params) => {
    installBrowser(params);
    expect(createTelegramSdk().hasLaunchParams()).toBe(false);
  });

  it("handles blocked storage and still recognizes current URL parameters", () => {
    const { getItem } = installBrowser();
    getItem.mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect(createTelegramSdk().hasLaunchParams()).toBe(false);
    window.location.hash = "#tgWebAppData=current-launch";
    expect(createTelegramSdk().hasLaunchParams()).toBe(true);
  });
});
