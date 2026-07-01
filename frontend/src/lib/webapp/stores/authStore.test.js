import { afterEach, describe, expect, it, vi } from "vitest";

import { createAuthStore } from "./authStore.ts";

function makeAuthStore(overrides = {}) {
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
    t: (key) => key,
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
});
