import { afterEach, describe, expect, it, vi } from "vitest";

import { runWebappBoot } from "./webappBoot.js";
type TestOverrides = Record<string, unknown>;

function installBrowser(search = "") {
  vi.stubGlobal("document", { title: "Mini Shop" });
  vi.stubGlobal("window", {
    location: {
      href: `https://app.example.com/${search}`,
      search,
    },
    history: { replaceState: vi.fn() },
  });
}

function makeDeps(overrides: TestOverrides = {}) {
  return {
    MOCK: false,
    setMode: vi.fn(),
    hasTelegramLaunchParams: vi.fn(() => false),
    loadTelegramSdk: vi.fn(),
    prepareTelegramMiniApp: vi.fn(),
    loadData: vi.fn(),
    showLogin: vi.fn(),
    clearToken: vi.fn(),
    refreshSession: vi.fn(),
    setCsrfToken: vi.fn(),
    clearManualLogoutFlag: vi.fn(),
    isManuallyLoggedOut: vi.fn(() => false),
    hasEmailCodeLoginDeeplink: vi.fn(() => false),
    finalizeMagicLogin: vi.fn(),
    finalizeTelegramAuth: vi.fn(),
    setAuthStatus: vi.fn(),
    t: (key: string) => key,
    getInitDataForBoot: vi.fn(() => ""),
    getToken: vi.fn(() => ""),
    getCsrfToken: vi.fn(() => ""),
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("runWebappBoot", () => {
  it("maps invite-required Telegram OAuth status to the dedicated auth copy", async () => {
    installBrowser("?telegram_auth=invite_required");
    const deps = makeDeps();

    await runWebappBoot(deps);

    expect(deps.setAuthStatus).toHaveBeenCalledWith("wa_auth_invite_required", true);
    expect(deps.showLogin).toHaveBeenCalledOnce();
    expect(window.history.replaceState).toHaveBeenCalledOnce();
  });

  it("loads data when the backend refreshes an existing cookie session", async () => {
    installBrowser();
    const deps = makeDeps({
      refreshSession: vi.fn(async () => ({ authenticated: true, csrf_token: "csrf-token" })),
      setCsrfToken: vi.fn(),
    });

    await runWebappBoot(deps);

    expect(deps.refreshSession).toHaveBeenCalledOnce();
    expect(deps.setCsrfToken).toHaveBeenCalledWith("csrf-token");
    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(deps.showLogin).not.toHaveBeenCalled();
  });

  it("keeps Telegram initData auth ahead of cookie session refresh", async () => {
    installBrowser();
    const deps = makeDeps({
      getInitDataForBoot: vi.fn(() => "tg-init-data"),
      finalizeTelegramAuth: vi.fn(async () => true),
      refreshSession: vi.fn(async () => ({ authenticated: true, csrf_token: "csrf-token" })),
    });

    await runWebappBoot(deps);

    expect(deps.finalizeTelegramAuth).toHaveBeenCalledWith("tg-init-data", "init_data");
    expect(deps.refreshSession).not.toHaveBeenCalled();
    expect(deps.showLogin).not.toHaveBeenCalled();
  });
});
