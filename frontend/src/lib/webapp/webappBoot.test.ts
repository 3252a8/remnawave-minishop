import { afterEach, describe, expect, it, vi } from "vitest";

import { runWebappBoot } from "./webappBoot.js";
import { createTelegramSdk } from "./telegramSdk.js";
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
    onTelegramMergeRequired: vi.fn(),
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
  it("loads Telegram before restoring a cookie session on a clean return URL", async () => {
    installBrowser();
    Object.assign(window, {
      sessionStorage: {
        getItem: () => JSON.stringify({ tgWebAppVersion: "8.0", tgWebAppPlatform: "ios" }),
      },
    });
    window.location.hash = "";
    const sdk = createTelegramSdk();
    const deps = makeDeps({
      hasTelegramLaunchParams: () => sdk.hasLaunchParams(),
      refreshSession: vi.fn(async () => ({ authenticated: true })),
    });
    await runWebappBoot(deps);
    expect(deps.loadTelegramSdk).toHaveBeenCalledOnce();
    expect(deps.prepareTelegramMiniApp.mock.invocationCallOrder[0]).toBeLessThan(
      deps.refreshSession.mock.invocationCallOrder[0]
    );
    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(window.history.replaceState).not.toHaveBeenCalled();
  });

  it("preserves the session on a non-transient profile failure", async () => {
    installBrowser();
    const deps = makeDeps({
      getToken: () => "saved-session",
      loadData: vi.fn(async () => {
        throw Object.assign(new Error("bad_response"), { status: 400 });
      }),
    });
    await runWebappBoot(deps);
    expect(deps.clearToken).not.toHaveBeenCalled();
    expect(deps.showLogin).not.toHaveBeenCalled();
    expect(deps.setMode).toHaveBeenLastCalledWith("bootError");
  });

  it("recovers automatically when the API becomes available after the frontend", async () => {
    vi.useFakeTimers();
    installBrowser();
    const loadData = vi
      .fn()
      .mockRejectedValueOnce(Object.assign(new Error("service_unavailable"), { status: 502 }))
      .mockResolvedValue(undefined);
    const deps = makeDeps({
      refreshSession: vi.fn(async () => ({ authenticated: true })),
      loadData,
    });
    const boot = runWebappBoot(deps);
    await vi.advanceTimersByTimeAsync(1_000);
    await boot;
    expect(loadData).toHaveBeenCalledTimes(2);
    expect(deps.setMode).not.toHaveBeenCalledWith("bootError");
    expect(deps.clearToken).not.toHaveBeenCalled();
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
    expect(deps.showAccountLinkStatus).toHaveBeenCalledWith("wa_account_merge_yandex_conflict");
    expect(deps.finalizeTelegramAuth).not.toHaveBeenCalled();
    expect(deps.showLogin).not.toHaveBeenCalled();
  });

  it("explains a conflicting second identity of the same provider", async () => {
    installBrowser("?external_auth=discord:provider_conflict");
    const deps = makeDeps();
    await runWebappBoot(deps);
    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(deps.showAccountLinkStatus).toHaveBeenCalledWith("wa_account_merge_provider_conflict");
    expect(deps.showLogin).not.toHaveBeenCalled();
    expect(deps.clearToken).not.toHaveBeenCalled();
  });

  it("keeps the authenticated account after a Telegram OAuth merge conflict", async () => {
    installBrowser("?telegram_auth=account_merge_google_conflict");
    const deps = makeDeps();

    await runWebappBoot(deps);

    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(deps.showAccountLinkStatus).toHaveBeenCalledWith("wa_account_merge_google_conflict");
    expect(deps.finalizeTelegramAuth).not.toHaveBeenCalled();
    expect(deps.showLogin).not.toHaveBeenCalled();
  });

  it("opens explicit merge confirmation after Telegram OAuth finds another account", async () => {
    installBrowser("?telegram_auth=account_merge_required");
    const deps = makeDeps();

    await runWebappBoot(deps);

    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(deps.onTelegramMergeRequired).toHaveBeenCalledOnce();
    expect(deps.showAccountLinkStatus).not.toHaveBeenCalled();
  });

  it("maps invite-required Telegram OAuth status to the dedicated auth copy", async () => {
    installBrowser("?telegram_auth=invite_required");
    const deps = makeDeps();

    await runWebappBoot(deps);

    expect(deps.setAuthStatus).toHaveBeenCalledWith("wa_auth_invite_required", true);
    expect(deps.showLogin).toHaveBeenCalledOnce();
    expect(window.history.replaceState).toHaveBeenCalledOnce();
  });

  it.each(["google", "yandex", "discord", "future-provider"])(
    "opens merge confirmation for %s without changing the current account",
    async (provider) => {
      for (const status of ["account_merge_required", "account_merge_ready"]) {
        installBrowser(`?external_auth=${provider}:${status}`);
        const deps = makeDeps();
        await runWebappBoot(deps);
        expect(deps.loadData).toHaveBeenCalledOnce();
        expect(deps.onTelegramMergeRequired).toHaveBeenCalledOnce();
        expect(deps.clearToken).not.toHaveBeenCalled();
        expect(deps.showLogin).not.toHaveBeenCalled();
        expect(deps.finalizeTelegramAuth).not.toHaveBeenCalled();
        expect(deps.linkTelegramAfterExternalAuth).not.toHaveBeenCalled();
        expect(deps.showAccountLinkStatus).not.toHaveBeenCalled();
      }
    }
  );

  it("reopens confirmation after Telegram proves ownership of the current account", async () => {
    installBrowser("?telegram_auth=account_merge_ready");
    const deps = makeDeps();
    await runWebappBoot(deps);
    expect(deps.onTelegramMergeRequired).toHaveBeenCalledOnce();
    expect(deps.clearToken).not.toHaveBeenCalled();
  });

  it.each(["?telegram_auth=account_merge_ready", "?external_auth=discord:account_merge_required"])(
    "opens the merge dialog in the demo for %s",
    async (query) => {
      installBrowser(query);
      const deps = makeDeps({ MOCK: true });
      await runWebappBoot(deps);
      expect(deps.loadData).toHaveBeenCalledOnce();
      expect(deps.onTelegramMergeRequired).toHaveBeenCalledOnce();
    }
  );

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
