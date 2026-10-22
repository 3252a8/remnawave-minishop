import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const locales = {
  ru: JSON.parse(readFileSync("../locales/ru.json", "utf8")),
  en: JSON.parse(readFileSync("../locales/en.json", "utf8")),
};

for (const language of ["ru", "en"] as const) {
  for (const width of [390, 1440]) {
    for (const [status, key] of [
      ["success", "wa_settings_linked"],
      ["invalid_state", "wa_auth_telegram_not_confirmed"],
      ["not_configured", "wa_auth_telegram_not_configured"],
    ]) {
      test(`Telegram link return ${status} remains visible in ${language} at ${width}px`, async ({
        page,
      }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.route("**/settings/security?**", async (route) => {
          if (route.request().resourceType() !== "document") return route.continue();
          const response = await route.fetch();
          const config = {
            authProviders: ["email", "telegram"],
            defaultLanguage: language,
            emailAuthEnabled: true,
            telegramOAuthClientId: 42,
          };
          const body = (await response.text()).replace(
            "</head>",
            `<script id="webapp-config" type="application/json">${JSON.stringify(config)}</script></head>`
          );
          await route.fulfill({ response, body });
        });
        await page.route("**/api/**", async (route) => {
          const path = new URL(route.request().url()).pathname;
          let response: Record<string, unknown> = { ok: true };
          if (path === "/api/auth/session")
            response = { ok: true, authenticated: true, csrf_token: "fixture-csrf" };
          if (path.startsWith("/api/i18n")) response = { ok: true, i18n: locales };
          if (path === "/api/me")
            response = {
              ok: true,
              user: {
                id: -100,
                language_code: language,
                is_admin: false,
                email: "linked@example.test",
                email_verified: true,
                telegram_linked: status === "success",
                telegram_id: status === "success" ? 42 : null,
              },
              settings: {},
              subscription: { active: false },
              plans: [],
              payment_methods: [],
              referral: {},
            };
          if (path === "/api/extensions/runtime")
            response = { ok: true, generation: 1, plugins: [] };
          if (path === "/api/gifts") response = { ok: true, enabled: false, gifts: [] };
          await route.fulfill({ json: response });
        });

        await page.goto(`/settings/security?telegram_auth=${status}&theme_preview=dark`);

        await expect(page.getByText(locales[language][key], { exact: true }).last()).toBeVisible();
        await expect(page.getByText("linked@example.test", { exact: true })).toBeVisible();
        await expect(page).toHaveURL(/\/settings\/security(?:\?|$)/);
        expect(new URL(page.url()).searchParams.has("telegram_auth")).toBe(false);
      });
    }
  }
}
