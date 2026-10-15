import { afterEach, describe, expect, it, vi } from "vitest";

import { createAuthStore } from "./authStore.js";
import { rememberInstallAuthDestination } from "../installAuthDestination";
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
  it.each(["password", "telegram"])(
    "restores install selection before loading the account after %s sign-in",
    async (method) => {
      installBrowser();
      const values = new Map<string, string>();
      Object.assign(window, {
        sessionStorage: {
          getItem: (key: string) => values.get(key) || null,
          setItem: (key: string, value: string) => values.set(key, value),
          removeItem: (key: string) => values.delete(key),
        },
      });
      Object.assign(window.location, {
        pathname: "/install",
        search: "?platform=ios&app=client-v2",
      });
      rememberInstallAuthDestination("login");
      Object.assign(window.location, { pathname: "/login/password", search: "" });
      const { store, deps } = makeAuthStore({
        publicApi: vi.fn().mockResolvedValue({ ok: true, token: "token", csrf_token: "csrf" }),
      });
      if (method === "password") {
        store.update((state) => ({
          ...state,
          email: "customer@example.test",
          emailPassword: "password",
        }));
        await store.loginWithEmailPassword();
      } else await store.finalizeTelegramAuth("telegram-init-data", "init_data");
      const restore = vi.mocked(window.history.replaceState);
      expect(restore).toHaveBeenCalledWith(null, "", "/install?platform=ios&app=client-v2");
      expect(restore.mock.invocationCallOrder[0]).toBeLessThan(
        deps.loadData.mock.invocationCallOrder[0]
      );
      expect(values.size).toBe(0);
    }
  );
  it("submits a pending gift as the Telegram registration invite", async () => {
    installBrowser();
    const token = "G".repeat(43);
    window.location.search = `?gift=${token}`;
    const { store, deps } = makeAuthStore({
      publicApi: vi.fn().mockResolvedValue({
        ok: true,
        token: "session-token",
        csrf_token: "csrf-token",
      }),
    });
    expect(await store.finalizeTelegramAuth("telegram-init-data", "init_data")).toBe(true);
    expect(deps.publicApi).toHaveBeenCalledWith(
      "/auth/token",
      { init_data: "telegram-init-data", referral_code: `gift_${token}` },
      { signal: undefined }
    );
  });

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

  it.each([false, true])(
    "normalizes pasted code separators before verifying external ownership (%s)",
    async (externalOauthPending) => {
      installBrowser();
      const { store, deps } = makeAuthStore({
        publicApi: vi.fn().mockResolvedValue({
          ok: true,
          token: "session-token",
          csrf_token: "csrf-token",
        }),
      });
      store.update((state) => ({
        ...state,
        externalOauthPending,
        pendingEmail: "user@example.test",
        emailCode: "12 34-56",
      }));

      await store.verifyEmailCode();

      expect(deps.publicApi).toHaveBeenCalledWith(
        externalOauthPending ? "/auth/external/verify" : "/auth/email/verify",
        externalOauthPending ? { code: "123456" } : { email: "user@example.test", code: "123456" }
      );
      expect(deps.setToken).toHaveBeenCalledWith("session-token", "csrf-token");
      expect(deps.loadData).toHaveBeenCalledOnce();
      expect(store.authBusy).toBe(false);
    }
  );
});
