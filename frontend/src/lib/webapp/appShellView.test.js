import { describe, expect, it } from "vitest";

import { computeAppShellView } from "./appShellView.js";

function t(key) {
  const messages = {
    wa_auth_checking_telegram: "Checking Telegram",
    wa_login_telegram_button: "Telegram",
    wa_login_telegram_unavailable_button: "Telegram unavailable",
    wa_settings_email_not_linked: "No email",
    wa_settings_linked: "Linked",
    wa_tg_id_not_linked: "TG missing",
  };
  return messages[key] || key;
}

describe("computeAppShellView", () => {
  it("composes app, billing, theme, account, language, and telegram login views", () => {
    const view = computeAppShellView({
      authBusy: false,
      authStatus: "",
      cfg: {
        language: "en",
        languages: [{ code: "en", label: "English", flag: "EN" }],
        primaryColor: "#123456",
        telegramLoginBotId: 77,
        themesCatalog: {
          default_theme: "light",
          themes: [{ key: "light", tokens: { color_scheme: "light" } }],
        },
        title: "Tunnel Shop",
      },
      data: {
        payment_methods: [{ id: "card" }],
        plans: [
          { months: 1, price: 100, tariff_key: "basic", tariff_name: "Basic" },
          { months: 3, price: 250, tariff_key: "pro", tariff_name: "Pro" },
        ],
        referral: { welcome_bonus_days: 7 },
        settings: {
          email_auth_enabled: true,
          my_devices_enabled: true,
          subscription_guides_enabled: true,
          support_tickets_enabled: true,
        },
        subscription: { active: true, tariff_key: "basic" },
        user: {
          email: "user@example.com",
          is_admin: true,
          language_code: "en",
          telegram_id: 123,
          telegram_linked: true,
        },
      },
      emailAvatarUrl: "https://cdn.example/avatar.png",
      fallbackBrandTitle: "Subscription",
      guestLanguage: "ru",
      hasTelegramLaunchParams: () => true,
      i18nMessages: { en: {} },
      isDemoAuthMock: () => false,
      languageName: (language) => `Language:${language}`,
      mockData: {},
      mockEnabled: false,
      normalizeLangCode: (language) => String(language || "").toLowerCase(),
      readTelegramMiniAppInitDataFromLocation: () => "init-data",
      screen: "home",
      selectedTariffKey: "basic",
      telegramLoginBusy: false,
      telegramSdkStatus: "ready",
      tg: null,
      themePreviewDraft: null,
      themePreviewKey: "",
      topupUnlockPercent: 80,
      t,
    });

    expect(view.appDataView.brandTitle).toBe("Tunnel Shop");
    expect(view.appDataView.devicesEnabled).toBe(true);
    expect(view.billingView.tariffMode).toBe(true);
    expect(view.billingView.selectedTariff?.key).toBe("basic");
    expect(view.themeView.toastTheme).toBe("light");
    expect(view.isAdmin).toBe(true);
    expect(view.currentLang).toBe("en");
    expect(view.languageView.currentLanguageOption?.label).toBe("English");
    expect(view.userLanguage).toBe("Language:en");
    expect(view.accountView.emailLinkStatus).toBe("Linked");
    expect(view.telegramMiniAppAuthAvailable).toBe(true);
    expect(view.telegramMiniAppContext).toBe(true);
    expect(view.telegramOAuthClientId).toBe(77);
    expect(view.telegramLoginView.telegramLoginUnavailable).toBe(false);
  });
});
