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

  it("offers explicit merge after a proven Telegram identity belongs to another account", async () => {
    const { store, deps } = makeAccountStore({
      api: vi.fn().mockRejectedValue({ error: "account_merge_required" }),
    });

    await store.linkTelegramAccount(() => "verified-mini-app-init-data");

    expect(deps.api).toHaveBeenCalledWith("/account/telegram/link", {
      method: "POST",
      body: JSON.stringify({ init_data: "verified-mini-app-init-data" }),
    });
    expect(store.telegramMergeOpen).toBe(true);
    expect(deps.showToast).not.toHaveBeenCalled();
  });

  it("refreshes the retained email account after explicit merge", async () => {
    const { store, deps } = makeAccountStore();

    await store.completeTelegramMerge({ token: "session", csrf_token: "csrf" });

    expect(deps.setToken).toHaveBeenCalledWith("session", "csrf");
    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true, preserveView: true });
  });

  it("opens explicit merge after a verified email belongs to another account", async () => {
    const { store, deps } = makeAccountStore({
      api: vi.fn().mockRejectedValue({ error: "account_merge_required" }),
    });
    store.openLinkEmailDialog("another@example.test");
    store.linkEmailPending = "another@example.test";
    store.linkEmailCode = "123456";

    await store.verifyLinkEmailCode();

    expect(deps.api).toHaveBeenCalledWith("/account/email/verify", {
      method: "POST",
      body: JSON.stringify({ email: "another@example.test", code: "123456" }),
    });
    expect(store.linkEmailOpen).toBe(false);
    expect(store.telegramMergeOpen).toBe(true);
    expect(deps.setToken).not.toHaveBeenCalled();
    expect(deps.loadData).not.toHaveBeenCalled();
    expect(deps.showToast).not.toHaveBeenCalled();
  });

  it.each([
    "account_merge_privileged_source",
    "account_merge_telegram_conflict",
    "provider_conflict",
  ])("keeps a rejected email link readable and retryable for %s", async (error) => {
    const { store, deps } = makeAccountStore({
      api: vi.fn().mockRejectedValue({ error, message: "Internal server detail" }),
    });
    store.openLinkEmailDialog("another@example.test");
    store.linkEmailPending = "another@example.test";
    store.linkEmailCode = "123456";

    await store.verifyLinkEmailCode();

    expect(store.linkEmailStatus).toBe(
      error === "provider_conflict" ? "wa_account_merge_provider_conflict" : `wa_${error}`
    );
    expect(store.linkEmailIsError).toBe(true);
    expect(store.linkEmailOpen).toBe(true);
    expect(store.linkEmailBusy).toBe(false);
    expect(store.telegramMergeOpen).toBe(false);
    expect(deps.setToken).not.toHaveBeenCalled();
    expect(deps.loadData).not.toHaveBeenCalled();
  });

  it("links email to the current administrator and normalizes a pasted code", async () => {
    const { store, deps } = makeAccountStore({
      api: vi.fn().mockResolvedValue({ ok: true, csrf_token: "new-csrf" }),
      getCurrentUser: vi.fn(() => ({ user_id: 1, is_admin: true })),
    });
    store.openLinkEmailDialog("admin@example.test");
    store.linkEmailPending = "admin@example.test";
    store.linkEmailCode = "12 34-56";

    await store.verifyLinkEmailCode();

    expect(deps.api).toHaveBeenCalledWith("/account/email/verify", {
      method: "POST",
      body: JSON.stringify({ email: "admin@example.test", code: "123456" }),
    });
    expect(deps.setToken).toHaveBeenCalledWith("", "new-csrf");
    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(store.linkEmailOpen).toBe(false);
    expect(store.telegramMergeOpen).toBe(false);
  });

  it.each(["init-data", "settings-demo", "trial-demo"])(
    "localizes a protected Telegram source in %s without changing the current administrator",
    async (flow) => {
      const { store, deps } = makeAccountStore({
        api: vi.fn().mockRejectedValue({
          error: "account_merge_privileged_source",
          message: "A privileged account cannot be merged automatically.",
        }),
        isDemoAuthLogin: vi.fn(() => flow !== "init-data"),
        getCurrentUser: vi.fn(() => ({ user_id: 1, is_admin: true })),
      });

      if (flow === "init-data") await store.linkTelegramAccount(() => "verified-init-data");
      else if (flow === "settings-demo") await store.linkTelegramFromSettings();
      else await store.linkTelegramAndActivateTrial();

      expect(deps.showToast).toHaveBeenCalledWith("wa_account_merge_privileged_source");
      expect(store.linkTelegramBusy).toBe(false);
      expect(store.telegramMergeOpen).toBe(false);
      expect(deps.setToken).not.toHaveBeenCalled();
      expect(deps.loadData).not.toHaveBeenCalled();
      expect(deps.activateTrial).not.toHaveBeenCalled();
    }
  );
});
