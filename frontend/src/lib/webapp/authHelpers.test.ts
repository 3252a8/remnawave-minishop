import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildExternalOAuthStartUrl,
  buildTelegramOAuthStartUrl,
  emailError,
  readReferralParam,
  readRegistrationInviteParam,
  shouldShowInviteOnlyHint,
} from "./authHelpers.js";
import { GIFT_STORAGE_KEY, REFERRAL_STORAGE_KEY } from "./session.js";

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
  it("carries a gift through registration and OAuth without replacing referral storage", () => {
    const token = "G".repeat(43);
    const { storage } = installBrowser(`?gift=${token}&ref=FRIEND`);

    expect(readRegistrationInviteParam()).toBe(`gift_${token}`);
    expect(readReferralParam()).toBe("FRIEND");
    expect(storage.get(REFERRAL_STORAGE_KEY)).toBe("FRIEND");
    expect(shouldShowInviteOnlyHint({ registrationInviteOnlyEnabled: true })).toBe(false);
    expect(new URL(buildTelegramOAuthStartUrl()).searchParams.get("referral_code")).toBe(
      `gift_${token}`
    );
    expect(buildExternalOAuthStartUrl("google", "login", "ru")).toBe(
      `/auth/google/start?purpose=login&lang=ru&ref=gift_${token}`
    );
    expect(buildExternalOAuthStartUrl("google", "link", "ru")).toBe(
      "/auth/google/start?purpose=link&lang=ru"
    );
  });

  it("restores a pending gift after OAuth and accepts Telegram gift launches", () => {
    const token = "T".repeat(43);
    const { storage } = installBrowser();
    expect(readRegistrationInviteParam({ initDataUnsafe: { start_param: `gift_${token}` } })).toBe(
      `gift_${token}`
    );
    storage.set(GIFT_STORAGE_KEY, token);
    expect(readRegistrationInviteParam()).toBe(`gift_${token}`);
    expect(storage.has(REFERRAL_STORAGE_KEY)).toBe(false);
  });

  it("keeps the invite hint for malformed gift tokens", () => {
    installBrowser("?gift=invalid");
    expect(readRegistrationInviteParam()).toBe("");
    expect(shouldShowInviteOnlyHint({ registrationInviteOnlyEnabled: true })).toBe(true);
  });

  it("does not let an older stored gift replace a referral invitation", () => {
    const { storage } = installBrowser("?ref=FRIEND");
    storage.set(GIFT_STORAGE_KEY, "G".repeat(43));
    expect(readRegistrationInviteParam()).toBe("FRIEND");
  });

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

  it("carries a partner web link into Google registration", () => {
    const code = "TestPartner_123";
    installBrowser(`?partner=${code}`);

    expect(buildExternalOAuthStartUrl("google", "login", "ru")).toBe(
      `/auth/google/start?purpose=login&lang=ru&ref=p_${code}`
    );
    expect(buildExternalOAuthStartUrl("google", "link", "ru")).toBe(
      "/auth/google/start?purpose=link&lang=ru"
    );
  });

  it("reads referral params from supported query names", () => {
    for (const [search, expected] of [
      ["?ref=ABC123", "ABC123"],
      ["?start=START123", "START123"],
      ["?start_param=MINI123", "MINI123"],
      ["?partner=PARTNER123", "p_PARTNER123"],
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

  it("preserves attribution when an action arrives through Telegram", () => {
    for (const action of [
      "promo_SAVE10",
      "plan_standard",
      "gift_token",
      "ticket_7",
      "plans",
      "admin_user_5",
    ]) {
      const { storage } = installBrowser("?ref=ref_FRIEND");
      expect(readReferralParam({ initDataUnsafe: { start_param: action } })).toBe("ref_FRIEND");
      expect(storage.get(REFERRAL_STORAGE_KEY)).toBe("ref_FRIEND");
      window.location.search = "";
      expect(readReferralParam()).toBe("ref_FRIEND");
    }
  });

  it("discards action values left in referral storage by older clients", () => {
    const { storage } = installBrowser("");
    storage.set(REFERRAL_STORAGE_KEY, "promo_SAVE10");
    expect(readReferralParam()).toBe("");
    expect(storage.has(REFERRAL_STORAGE_KEY)).toBe(false);
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
