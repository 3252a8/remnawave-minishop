import { afterEach, describe, expect, it, vi } from "vitest";

import { createAuthStore } from "./authStore.js";
type TestOverrides = Record<string, unknown>;

function makeAuthStore(overrides: TestOverrides = {}) {
  const deps = {
    publicApi: vi.fn(),
    setToken: vi.fn(),
    loadData: vi.fn(),
    telegramSdk: {
      hasLaunchParams: vi.fn(() => false),
      createMiniAppAuthTimeout: vi.fn(),
      ensureForAction: vi.fn(),
    },
    getTg: vi.fn(() => null),
    t: (key: string) => key,
    currentLang: vi.fn(() => "ru"),
    ...overrides,
  };
  return { store: createAuthStore(deps), deps };
}

function installBrowser() {
  vi.stubGlobal("document", { title: "Mini Shop" });
  vi.stubGlobal("window", {
    location: {
      href: "https://app.example.com/",
      search: "",
    },
    history: { replaceState: vi.fn() },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("authStore", () => {
  it("stores the returned session token before loading data after Telegram auth", async () => {
    installBrowser();
    const { store, deps } = makeAuthStore({
      publicApi: vi.fn().mockResolvedValue({
        ok: true,
        token: "session-token",
        csrf_token: "csrf-token",
      }),
    });

    const result = await store.finalizeTelegramAuth("telegram-init-data", "init_data");

    expect(result).toBe(true);
    expect(deps.publicApi).toHaveBeenCalledWith(
      "/auth/token",
      { init_data: "telegram-init-data" },
      { signal: undefined }
    );
    expect(deps.setToken).toHaveBeenCalledWith("session-token", "csrf-token");
    expect(deps.loadData).toHaveBeenCalledOnce();
  });

  it("links Telegram after confirmed external email ownership", async () => {
    installBrowser();
    const linkTelegramAfterExternalAuth = vi.fn();
    const { store, deps } = makeAuthStore({
      publicApi: vi.fn().mockResolvedValue({
        ok: true,
        token: "session-token",
        csrf_token: "csrf-token",
      }),
      linkTelegramAfterExternalAuth,
    });
    store.update((state) => ({
      ...state,
      externalOauthPending: true,
      pendingExternalProvider: "yandex",
      pendingEmail: "ya***@example.test",
      emailCode: "123456",
    }));

    await store.verifyEmailCode();

    expect(deps.publicApi).toHaveBeenCalledWith("/auth/external/verify", { code: "123456" });
    expect(deps.setToken).toHaveBeenCalledWith("session-token", "csrf-token");
    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(linkTelegramAfterExternalAuth).toHaveBeenCalledOnce();
  });

  it("deduplicates simultaneous email code verification requests", async () => {
    installBrowser();
    let releaseResponse!: (value: { ok: boolean; token: string; csrf_token: string }) => void;
    const publicApi = vi.fn(
      () =>
        new Promise<{ ok: boolean; token: string; csrf_token: string }>((resolve) => {
          releaseResponse = resolve;
        })
    );
    const { store } = makeAuthStore({ publicApi });
    store.update((state) => ({
      ...state,
      pendingEmail: "user@example.test",
      emailCode: "123456",
    }));

    const first = store.verifyEmailCode();
    const duplicate = store.verifyEmailCode();

    expect(publicApi).toHaveBeenCalledOnce();
    releaseResponse({ ok: true, token: "session-token", csrf_token: "csrf-token" });
    await Promise.all([first, duplicate]);
    expect(publicApi).toHaveBeenCalledOnce();
  });
});
