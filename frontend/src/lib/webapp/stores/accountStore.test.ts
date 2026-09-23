import { describe, expect, it, vi } from "vitest";

import { createAccountStore } from "./accountStore.js";
type TestOverrides = Record<string, unknown>;

function makeAccountStore(overrides: TestOverrides = {}) {
  const deps = {
    api: vi.fn(),
    publicApi: vi.fn(),
    setToken: vi.fn(),
    loadData: vi.fn(),
    t: (key: string) => key,
    showToast: vi.fn(),
    clearToken: vi.fn(),
    markManualLogout: vi.fn(),
    showLogin: vi.fn(),
    telegramSdk: {
      hasLaunchParams: vi.fn(() => false),
      ensureForAction: vi.fn(),
    },
    getTg: vi.fn(() => null),
    getCurrentUser: vi.fn(() => ({ user_id: 1 })),
    getTelegramMiniAppInitData: vi.fn(() => ""),
    isDemoAuthLogin: vi.fn(() => false),
    getDemoTelegramAuthPayload: vi.fn(() => ({})),
    telegramOAuthClientId: 0,
    currentLang: vi.fn(() => "ru"),
    normalizeLangCode: vi.fn((value) =>
      String(value || "")
        .trim()
        .toLowerCase()
    ),
    ensureLanguage: vi.fn(async () => undefined),
    rememberLanguage: vi.fn(),
    updateLocalData: vi.fn(),
    activateTrial: vi.fn(),
    claimReferralWelcomeBonus: vi.fn(),
    ...overrides,
  };
  return { store: createAccountStore(deps), deps };
}

describe("accountStore", () => {
  it("opens and closes the email linking dialog with normalized draft state", () => {
    const { store } = makeAccountStore();

    store.openLinkEmailDialog("User@Example.COM");
    expect(store).toMatchObject({
      linkEmailOpen: true,
      linkEmailValue: "User@Example.COM",
      linkEmailCode: "",
      linkEmailStatus: "",
      linkEmailIsError: false,
    });

    store.closeLinkEmailDialog();
    expect(store).toMatchObject({
      linkEmailOpen: false,
      linkEmailValue: "User@Example.COM",
      linkEmailCode: "",
      linkEmailPending: "",
    });
  });

  it("rejects invalid email before calling the API", async () => {
    const { store, deps } = makeAccountStore();

    store.openLinkEmailDialog("not-email");
    await store.requestLinkEmailCode();

    expect(deps.api).not.toHaveBeenCalled();
    expect(store.linkEmailFieldError).toBe("wa_auth_invalid_email");
  });

  it("updates account language and refreshes local data", async () => {
    const { store, deps } = makeAccountStore({
      currentLang: vi.fn(() => "en"),
      api: vi.fn().mockResolvedValue({ ok: true, language: "ru" }),
    });

    await store.updateAccountLanguage(" RU ", { preserveScroll: true });

    expect(deps.api).toHaveBeenCalledWith("/account/language", {
      method: "POST",
      body: JSON.stringify({ language: "ru" }),
    });
    expect(deps.updateLocalData).toHaveBeenCalledWith("ru");
    expect(deps.ensureLanguage).toHaveBeenCalledWith("ru");
    expect(deps.rememberLanguage).toHaveBeenCalledWith("ru");
    expect(deps.loadData).toHaveBeenCalledWith({
      fresh: true,
      preserveView: true,
      preserveScroll: true,
    });
    expect(store.languageBusy).toBe(false);
  });

  it("does not change the account language when its dictionary cannot load", async () => {
    const { store, deps } = makeAccountStore({
      currentLang: vi.fn(() => "ru"),
      ensureLanguage: vi.fn(async () => Promise.reject(new Error("offline"))),
    });

    await store.updateAccountLanguage("en");

    expect(deps.api).not.toHaveBeenCalled();
    expect(deps.rememberLanguage).not.toHaveBeenCalled();
    expect(deps.showToast).toHaveBeenCalledOnce();
    expect(store.languageBusy).toBe(false);
  });

  it("logs out non-Telegram sessions through the public API", async () => {
    const { store, deps } = makeAccountStore();

    await store.logout();

    expect(deps.markManualLogout).toHaveBeenCalled();
    expect(deps.clearToken).toHaveBeenCalled();
    expect(deps.publicApi).toHaveBeenCalledWith("/auth/logout", { keepalive: true });
    expect(deps.showLogin).toHaveBeenCalled();
  });
});
