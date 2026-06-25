import { describe, expect, it } from "vitest";

import { computeTelegramLoginView } from "./telegramLoginView.js";

describe("computeTelegramLoginView", () => {
  const t = (key) => `t:${key}`;

  it("marks Telegram login unavailable when no auth surface is configured", () => {
    const view = computeTelegramLoginView({
      authBusy: false,
      authStatus: "",
      demoAuthLogin: false,
      telegramLoginBusy: false,
      telegramMiniAppAuthAvailable: false,
      telegramOAuthClientId: 0,
      telegramSdkStatus: "idle",
      t,
    });

    expect(view).toEqual({
      telegramLoginChecking: false,
      telegramLoginLabel: "t:wa_login_telegram_unavailable_button",
      telegramLoginUnavailable: true,
      telegramLoginUnavailableMessage: "t:wa_auth_telegram_not_configured",
    });
  });

  it("uses the SDK unavailable message when Telegram script loading failed", () => {
    const view = computeTelegramLoginView({
      authBusy: false,
      authStatus: "",
      demoAuthLogin: false,
      telegramLoginBusy: false,
      telegramMiniAppAuthAvailable: false,
      telegramOAuthClientId: 0,
      telegramSdkStatus: "unavailable",
      t,
    });

    expect(view.telegramLoginUnavailable).toBe(true);
    expect(view.telegramLoginUnavailableMessage).toBe("t:wa_auth_telegram_unavailable");
  });

  it("keeps demo login available and reports checking state", () => {
    const view = computeTelegramLoginView({
      authBusy: true,
      authStatus: "t:wa_auth_checking_telegram",
      demoAuthLogin: true,
      telegramLoginBusy: false,
      telegramMiniAppAuthAvailable: false,
      telegramOAuthClientId: 0,
      telegramSdkStatus: "idle",
      t,
    });

    expect(view.telegramLoginUnavailable).toBe(false);
    expect(view.telegramLoginChecking).toBe(true);
    expect(view.telegramLoginLabel).toBe("t:wa_auth_checking_telegram");
    expect(view.telegramLoginUnavailableMessage).toBe("");
  });
});
