import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildExternalOAuthStartUrl,
  buildTelegramOAuthStartUrl,
  emailError,
  readReferralParam,
  shouldShowInviteOnlyHint,
} from "./authHelpers.js";
import { REFERRAL_STORAGE_KEY } from "./session.js";

function installBrowser(search = "", pathname = "/") {
  const storage = new Map();
  const localStorage = {
    getItem: vi.fn((key: string) => storage.get(key) || null),
    setItem: vi.fn((key, value) => storage.set(key, String(value))),
    removeItem: vi.fn((key: string) => storage.delete(key)),
  };
  vi.stubGlobal("localStorage", localStorage);
  vi.stubGlobal("window", {
    location: {
      href: `https://app.example.com/${search}`,
      origin: "https://app.example.com",
      pathname,
      search,
    },
    history: { replaceState: vi.fn() },
  });
  return { localStorage, storage };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("auth referral helpers", () => {
  it("keeps private tariff access through Telegram OAuth", () => {
    const accessCode = "ab".repeat(16);
    installBrowser("", `/checkout/${accessCode}`);

    expect(buildTelegramOAuthStartUrl()).toBe(
      `https://app.example.com/auth/telegram/start?purpose=login&tariff_access=${accessCode}`
    );
  });

  it("builds external OAuth URLs with the application language", () => {
    expect(buildExternalOAuthStartUrl("yandex", "login", "ru", "ABC 123")).toBe(
      "/auth/yandex/start?purpose=login&lang=ru&ref=ABC+123"
    );
    expect(buildExternalOAuthStartUrl("google", "link", "en")).toBe(
      "/auth/google/start?purpose=link&lang=en"
    );
    expect(buildExternalOAuthStartUrl("discord", "login", "en")).toBe(
      "/auth/discord/start?purpose=login&lang=en"
    );
    expect(buildExternalOAuthStartUrl("google", "login", "en", "", "AB".repeat(16))).toBe(
      `/auth/google/start?purpose=login&lang=en&tariff_access=${"ab".repeat(16)}`
    );
  });

  it("reads referral params from supported query names", () => {
    for (const [search, expected] of [
      ["?ref=ABC123", "ABC123"],
      ["?start=START123", "START123"],
      ["?start_param=MINI123", "MINI123"],
    ]) {
      vi.unstubAllGlobals();
      const { storage } = installBrowser(search);

      expect(readReferralParam()).toBe(expected);
      expect(storage.get(REFERRAL_STORAGE_KEY)).toBe(expected);
    }
  });

  it("prefers Telegram start_param over query referral", () => {
    const { storage } = installBrowser("?ref=QUERY123");

    expect(readReferralParam({ initDataUnsafe: { start_param: "TG123" } })).toBe("TG123");
    expect(storage.get(REFERRAL_STORAGE_KEY)).toBe("TG123");
  });

  it("does not treat a Telegram plan checkout payload as a referral", () => {
    const { storage } = installBrowser("");

    expect(
      readReferralParam({
        initDataUnsafe: { start_param: "plan_standard__months_3__traffic_200" },
      })
    ).toBe("");
    expect(storage.has(REFERRAL_STORAGE_KEY)).toBe(false);
  });

  it("shows the invite-only hint only when no referral is available", () => {
    const { localStorage } = installBrowser("");

    expect(shouldShowInviteOnlyHint({ registrationInviteOnlyEnabled: true })).toBe(true);

    localStorage.setItem(REFERRAL_STORAGE_KEY, "ABC123");

    expect(shouldShowInviteOnlyHint({ registrationInviteOnlyEnabled: true })).toBe(false);
    expect(shouldShowInviteOnlyHint({ registrationInviteOnlyEnabled: false })).toBe(false);
  });

  it("maps invite-only auth errors to the dedicated copy", () => {
    const t = (key: string) => `t:${key}`;

    expect(emailError({ error: "registration_invite_required" }, "fallback", t)).toBe(
      "t:wa_auth_invite_required"
    );
  });
});
