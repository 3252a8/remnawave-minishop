import { describe, expect, it } from "vitest";

import { computeAccountView } from "./accountView.js";

describe("computeAccountView", () => {
  const t = (key) => `t:${key}`;

  it("summarizes linked email, Telegram profile, notification prompt and settings links", () => {
    const view = computeAccountView({
      appSettings: {
        server_status_url: " https://status.example.test ",
        support_url: " https://support.example.test ",
      },
      cfg: {
        privacyPolicyUrl: " https://privacy.example.test ",
        supportUrl: "https://fallback-support.example.test",
        userAgreementUrl: " https://agreement.example.test ",
      },
      emailAuthEnabled: true,
      emailAvatarUrl: "https://gravatar.example.test/avatar",
      t,
      user: {
        email: "user@example.test",
        first_name: "Ann",
        last_name: "Lee",
        telegram_id: 123,
        telegram_linked: true,
        telegram_notifications_need_prompt: true,
        telegram_notifications_start_link: "https://t.me/bot?start=notify",
        telegram_notifications_status: "prompt",
        telegram_photo_url: " https://telegram.example.test/avatar.jpg ",
      },
    });

    expect(view.emailLinkStatus).toBe("t:wa_settings_linked");
    expect(view.telegramNotificationsNeedPrompt).toBe(true);
    expect(view.hasUnlinkedIdentity).toBe(true);
    expect(view.telegramProfileName).toBe("Ann Lee");
    expect(view.profileEmail).toBe("user@example.test");
    expect(view.profileTelegramId).toBe("TG ID 123");
    expect(view.profileAvatarUrl).toBe("https://telegram.example.test/avatar.jpg");
    expect(view.serverStatusUrl).toBe("https://status.example.test");
    expect(view.supportUrl).toBe("https://support.example.test");
    expect(view.privacyPolicyUrl).toBe("https://privacy.example.test");
    expect(view.userAgreementUrl).toBe("https://agreement.example.test");
  });

  it("reports missing identities and falls back to cfg support links", () => {
    const view = computeAccountView({
      appSettings: {},
      cfg: { serverStatusUrl: "https://status.example.test", supportUrl: "https://support.test" },
      emailAuthEnabled: true,
      emailAvatarUrl: " https://gravatar.example.test/avatar ",
      t,
      user: {
        email: "",
        telegram_linked: false,
        telegram_notifications_status: "",
      },
    });

    expect(view.emailLinkStatus).toBe("t:wa_settings_email_not_linked");
    expect(view.telegramNotificationsStatus).toBe("unknown");
    expect(view.telegramNotificationsNeedPrompt).toBe(false);
    expect(view.hasUnlinkedIdentity).toBe(true);
    expect(view.profileEmail).toBe("t:wa_settings_email_not_linked");
    expect(view.profileTelegramId).toBe("t:wa_tg_id_not_linked");
    expect(view.profileAvatarUrl).toBe("https://gravatar.example.test/avatar");
    expect(view.serverStatusUrl).toBe("https://status.example.test");
    expect(view.supportUrl).toBe("https://support.test");
  });
});
