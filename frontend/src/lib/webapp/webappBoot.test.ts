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
    linkTelegramAfterExternalAuth: vi.fn(),
    restorePendingExternalOauth: vi.fn(async () => true),
    setAuthStatus: vi.fn(),
    showAccountLinkStatus: vi.fn(),
    t: (key: string) => key,
    getInitDataForBoot: vi.fn(() => ""),
    getToken: vi.fn(() => ""),
    getCsrfToken: vi.fn(() => ""),
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("runWebappBoot", () => {
  it("preserves the session on a temporary profile failure", async () => {
    installBrowser();
    const deps = makeDeps({
      getToken: () => "saved-session",
      loadData: vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    });
    await runWebappBoot(deps);
    expect(deps.clearToken).not.toHaveBeenCalled();
    expect(deps.showLogin).not.toHaveBeenCalled();
    expect(deps.setMode).toHaveBeenLastCalledWith("bootError");
  });

  it("ends a stalled boot without deleting the session", async () => {
    vi.useFakeTimers();
    installBrowser();
    const deps = makeDeps({ refreshSession: () => new Promise(() => {}) });
    const boot = runWebappBoot(deps);
    await vi.advanceTimersByTimeAsync(20001);
    await boot;
    expect(deps.setMode).toHaveBeenLastCalledWith("bootError");
    expect(deps.clearToken).not.toHaveBeenCalled();
  });

  it("returns to login for an invalid saved session", async () => {
    installBrowser();
    const deps = makeDeps({
      getToken: () => "expired-session",
      loadData: vi.fn(async () => {
        throw Object.assign(new Error("unauthorized"), { status: 401 });
      }),
    });
    await runWebappBoot(deps);
    expect(deps.clearToken).toHaveBeenCalledOnce();
    expect(deps.showLogin).toHaveBeenCalledOnce();
  });
  it("continues matching OIDC email login with email confirmation", async () => {
    installBrowser("?external_auth=google:email_confirmation_required");
    const deps = makeDeps();

    await runWebappBoot(deps);

    expect(deps.showLogin).toHaveBeenCalledOnce();
    expect(deps.restorePendingExternalOauth).toHaveBeenCalledOnce();
    expect(deps.loadData).not.toHaveBeenCalled();
    expect(window.history.replaceState).toHaveBeenCalledOnce();
  });

  it("links Telegram initData after a successful external login", async () => {
    installBrowser("?external_auth=yandex:success");
    const deps = makeDeps();

    await runWebappBoot(deps);

    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(deps.linkTelegramAfterExternalAuth).toHaveBeenCalledOnce();
    expect(deps.loadData.mock.invocationCallOrder[0]).toBeLessThan(
      deps.linkTelegramAfterExternalAuth.mock.invocationCallOrder[0]
    );
    expect(deps.finalizeTelegramAuth).not.toHaveBeenCalled();
  });

  it("keeps the authenticated account and explains an external identity conflict", async () => {
    installBrowser("?external_auth=yandex:account_merge_yandex_conflict");
    const deps = makeDeps();

    await runWebappBoot(deps);

    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(deps.showAccountLinkStatus).toHaveBeenCalledWith("account_merge_yandex_conflict");
    expect(deps.finalizeTelegramAuth).not.toHaveBeenCalled();
    expect(deps.showLogin).not.toHaveBeenCalled();
  });

  it("keeps the authenticated account after a Telegram OAuth merge conflict", async () => {
    installBrowser("?telegram_auth=account_merge_google_conflict");
    const deps = makeDeps();

    await runWebappBoot(deps);

    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(deps.showAccountLinkStatus).toHaveBeenCalledWith("account_merge_google_conflict");
    expect(deps.finalizeTelegramAuth).not.toHaveBeenCalled();
    expect(deps.showLogin).not.toHaveBeenCalled();
  });

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
